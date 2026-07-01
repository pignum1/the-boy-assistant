# Agent 执行模式设计文档

> 7 种执行模式，由 Agent 的 `execution_mode` 字段决定，一处配置，处处生效。
> 编排层不干预 Agent 怎么思考 —— 仅通过 `node_key` 作日志标签。

---

## 1. 模式总览

| 模式 | 常量 | 适用场景 | 典型延迟 | Span 结构 |
|------|------|---------|---------|----------|
| **单次调用** | `single_pass` | 简单问答、单函数实现 | 3-10s | 1 span → 1 generation |
| **思维链** | `chain_of_thought` | 复杂推理 | 5-15s | 1 span → 1 generation |
| **规划执行** | `plan_execute` | 需要分阶段规划 | 20-60s | 1 span → 3 phase spans → N generations |
| **ReAct** | `react` | 需要工具调用 | 20-120s | 1 span → N iter spans → N generations |
| **ReWOO** | `rewoo` | 并行工具执行 | 15-60s | 1 span → 3 phase spans → N generations |
| **Reflexion** | `reflexion` | 自我纠错、测试 | 30-180s | 1 span → critique/redo spans → N generations |
| **自一致性** | `self_consistency` | 需要多方案对比 | 30-120s | 1 span → sampling+merge spans → 3N generations |

---

## 2. 模式详解

### 2.1 single_pass — 单次调用

```
[Agent Span: [single_pass] {name} ({role})]
  ├── input: 用户 prompt
  ├── output: LLM 回复
  └── [Generation: chat:{model}]
```

Agent 的 prompt + 系统设定 → LLM 一次调用 → 返回结果。最简单、最快。

### 2.2 chain_of_thought — 思维链

```
[Agent Span: [chain_of_thought] {name} ({role})]
  ├── input: 用户 prompt（含 CoT 引导）
  ├── output: 推理过程 + 最终答案
  └── [Generation: chat:{model}]
```

与 single_pass 相同结构，但 prompt 中注入思维链引导（"让我们一步步思考"）。

### 2.3 plan_execute — 规划执行

```
[Agent Span: [plan_execute] {name} ({role})]
  ├── input: 任务描述
  ├── output: 完整规划 + 补充结果
  ├── [Phase 1: Plan]
  │   └── [Generation: chat:{model}]     ← LLM 生成执行计划
  ├── [Phase 2: Review]
  │   └── [Generation: chat:{model}]     ← LLM 审查计划完整性
  └── [Phase 3: Supplement]
      └── [Generation: chat:{model}]     ← 补充遗漏内容
```

### 2.4 react — ReAct 循环

```
[Agent Span: [react] {name} ({role})]
  ├── input: 任务 + 工具声明
  ├── output: 最终答案
  ├── [Iteration 1]
  │   ├── [Generation: chat:{model}]     ← Think
  │   └── [Generation: tool:{name}]      ← Act (工具调用后的 follow-up)
  ├── [Iteration 2]
  │   └── ...
  └── [Iteration N] (max 5)
      └── [Generation: chat:{model}]     ← 最终答案
```

Think → Act → Observe 循环，最多 5 次迭代。每次迭代检查是否有工具调用需要执行。

### 2.5 rewoo — ReWOO 并行执行

```
[Agent Span: [rewoo] {name} ({role})]
  ├── input: 任务描述
  ├── output: 合并结果
  ├── [Phase 1: Plan]
  │   └── [Generation: chat:{model}]     ← 生成执行步骤
  ├── [Phase 2: Execute]
  │   ├── [Generation: chat:{model}]     ← 执行步骤 1
  │   ├── [Generation: chat:{model}]     ← 执行步骤 2 (并行)
  │   └── ...
  └── [Phase 3: Merge]
      └── [Generation: chat:{model}]     ← 合并所有步骤结果
```

先规划步骤 → 并行执行所有工具 → 合并结果。适合无依赖的多步骤任务。

### 2.6 reflexion — 反思循环

```
[Agent Span: [reflexion] {name} ({role})]
  ├── input: 任务 + 测试标准
  ├── output: 最终代码（经过 self-critic 改进）
  ├── [Round 1: Execute]
  │   └── [Generation: chat:{model}]     ← 初次实现
  ├── [Critique Round 1]
  │   └── [Generation: chat:{model}]     ← LLM 自我评分 + 找问题
  ├── [Redo Round 2]
  │   └── [Generation: chat:{model}]     ← 根据 critique 改进
  ├── [Critique Round 2]
  │   └── ...
  └── [Redo Round N]
      └── [Generation: chat:{model}]     ← 最终版本
```

执行 → LLM 自我评分 (score + verdict + issues) → 根据反馈改进 → 重新执行。直到 score ≥ 阈值或达到最大轮次。

### 2.7 self_consistency — 自一致性

```
[Agent Span: [self_consistency] {name} ({role})]
  ├── input: 任务（含"请给出 3 次独立回答"引导）
  ├── output: 综合后的最终方案
  ├── [Phase 1: Sampling]
  │   ├── [Generation: chat:{model}]     ← 独立回答 1
  │   ├── [Generation: chat:{model}]     ← 独立回答 2
  │   └── [Generation: chat:{model}]     ← 独立回答 3
  └── [Phase 2: Merge]
      └── [Generation: chat:{model}]     ← 综合 3 次回答
```

对同一问题采样 3 次独立回答 → 另一次 LLM 调用综合所有回答 → 输出一致性最高的方案。

---

## 3. 模式选择策略

```
Agent.execution_mode 字段（Agent 创建时配置）
                │
                ▼
       AgentExecutor.execute()
                │
        ┌───────┼───────────┬──────────┬──────────┬──────────┬──────────┐
        ▼       ▼           ▼          ▼          ▼          ▼          ▼
    single_pass  CoT    plan_execute  react      rewoo    reflexion  self_consistency
```

**关键设计决策**：模式仅由 Agent 自身决定。编排层（Swarm/Supervisor/LangGraph）不干预 Agent 怎么思考，每个 Agent 独立选择最适合自己角色的执行模式。

---

## 4. 监控集成

每种执行模式自动记录到 LangFuse：

| 模式 | Span 名称格式 | 子 Span 数量 | Generation 数量 |
|------|-------------|-------------|----------------|
| single_pass | `[single_pass] {name} ({role})` | 0 | 1 |
| chain_of_thought | `[chain_of_thought] {name} ({role})` | 0 | 1 |
| plan_execute | `[plan_execute] {name} ({role})` | 3 (Phase 1/2/3) | 3 |
| react | `[react] {name} ({role})` | N (Iteration 1..N) | 1-2N |
| rewoo | `[rewoo] {name} ({role})` | 3 (Plan/Execute/Merge) | N+2 |
| reflexion | `[reflexion] {name} ({role})` | 2R-1 (critique+redo) | 2R-1 |
| self_consistency | `[self_consistency] {name} ({role})` | 2 (sampling/merge) | 4 |

---

*文档基于 v5.0 代码生成，最后更新：2026-07-01*

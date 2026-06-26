# The Boy Assistant — 系统设计架构文档

> 版本：v5.0  |  技术栈：Python 3.12 + FastAPI + LangGraph + React 18 + TypeScript + PostgreSQL 16 + Redis 7

---

## 1. 整体架构

系统采用 **四层架构 + 横切保障层** 模式：

```
┌─────────────────────────────────────────────────────────────┐
│                     交互层 (Frontend)                       │
│  ChatRoomView → Reducer(纯函数) → 组件树                    │
│  消息流 / 抽屉系统 / 输入框行为机 / 流式渲染               │
├─────────────────────────────────────────────────────────────┤
│                     通信层 (API Gateway)                    │
│  WebSocket (三模式共用单连接)  +  REST (session/team CRUD)  │
│  Vite Proxy → FastAPI 路由 → 模式分发                      │
├──────────────────┬──────────────────┬───────────────────────┤
│   Swarm Engine   │ Supervisor Engine│  LangGraph Engine     │
│   群聊模式        │ 主管模式          │  工作流模式           │
│   (3阶段流水线)   │ (M0-M7 LangGraph) │  (拓扑排序+分层并行) │
├──────────────────┴──────────────────┴───────────────────────┤
│                     能力层 (Infrastructure)                  │
│  LLM Adapter (LiteLLM) │ Memory (L1-L4) │ Tools (file ops) │
│  Context Manager │ Model Router │ Agent Pool │ Fallback    │
├─────────────────────────────────────────────────────────────┤
│                   Harness 保障层 (横切)                      │
│  before_execution ─ after_execution ─ verify ─ cleanup      │
│  上下文注入 · Token管控 · 文件提取 · 审计 · 独立验证        │
│  Loop Engine (错误恢复) · Observer (事件总线+持久化)         │
│  Security Filter (注入检测+PII脱敏) · API Auth · Rate Limit │
└─────────────────────────────────────────────────────────────┘
```

**通信方式**：前端 ↔ 后端统一走 WebSocket（单连接），通过 `message.type` 字段区分事件类型（`agent_message` / `stream_token` / `hitl_notification` / `task_status` / `files_changed`）。REST 仅用于历史加载和配置管理。

---

## 2. 三模式协作引擎

### 2.1 Swarm Engine（群聊模式）

**定位**：多 Agent 自由讨论，无需预设流程。

```
用户输入 → Phase 1: 多轮讨论 → Phase 2: Agent 执行 → Phase 3: 完成/HITL
                ↑                                    │
                └───────── < 3轮 ────────────────────┘
```

**三阶段流水线**：
| 阶段 | 描述 |
|------|------|
| **RoundTable 讨论** | 轮询所有 Agent 发言，每轮收集所有观点。最多 3 轮。 |
| **Agent Execution** | 有产出任务的 Agent 调用 LLM 生成代码/文档，注入 Harness。 |
| **Completion** | 无 HITL → 推送摘要。有 HITL → 暂停等用户。 |

**HITL 三级检测**（`hitl_detector.py`）：

```
Level 1: __HITL__ 显式标记    → 直接触发，confidence=1.0
Level 2: **方案X** 结构化选项  → 提取选项列表，confidence=0.9
Level 3: 语义特征评分          → 6个特征加权求和 ≥ 3 触发
Level 4: 关键词兜底            → "选择/确认/请回复" + "方案"
```

**6 特征评分公式**（Level 3）：
```
semantic_score = OPTION_LIST×2 + QUESTION×1 + USER_DIRECT×1 
               + LAST_SPEAKER×1 + NO_RECENT×1 + EXCLUDED×(-1)

触发阈值: semantic_score ≥ 3
```

- **OPTION_LIST (×2)**：文本含 "A/B" 或 "方案一/二" 结构
- **QUESTION (×1)**：含问号 + 选择类动词
- **USER_DIRECT (×1)**：直接呼唤用户（"请你/您"）
- **LAST_SPEAKER (×1)**：最后发言的 Agent 触发 → 更可能是总结性提问
- **NO_RECENT (×1)**：近期无用户消息 → 应暂停等输入
- **EXCLUDED (×-1)**：含排除关键词（"不需要/自行决定"）

**选项提取**：4 种方法（markdown header parsing / regex 方案A/B / numbered list / keyword splitting），优先级递减。

### 2.2 Supervisor Engine（主管模式）

**定位**：结构化多 Agent 协作，固定 M0-M7 管道，支持组织层级委派。

```
M0 意图路由 → M1 需求分析 → M2 澄清确认 → M3 Agent编排 → M4 任务分解 → M6 执行 → M7 验证
  │              │             │              │              │             │           │
  │              └→HITL ←──────┘              └→HITL         │             │    ┌──────┘
  └→ 直接回复                                    │           │    ┌────────┘    │
                                              缺少Agent   DAG图  │  HITL确认     ├→ M1(重分析)
                                                                   │              └→ HITL(升级)
                                                                   └→ M1'(介入重规划)
```

**与 LangGraph 的关系**：Supervisor Engine **不是** LangGraph 的替代品——它本身就是用 LangGraph 实现的。`graph.py` 定义了一个 `StateGraph<CollabState>`，注册 M0-M7+HITL 共 9 个节点和条件边。引擎对外暴露 `run()` 和 `resume()`，内部调用 `streaming.py` 驱动状态图。

**原子节点 vs 固定管道**：LangGraph 的 `add_node` 绑定的是**原子执行函数**（如 `m4_decompose_node`），而 Supervisor 暴露的是**完整管道**（`run()` 走完 M0-M7）。这是因为主管模式的价值在于固定流程，不允许用户自定义 DAG。

**M5 Context Pipeline 与 Harness 的职责边界**：
| 组件 | 职责 |
|------|------|
| **M5 Context Pipeline** | 为单次 Agent 执行构建完整 prompt。从 CollabState 中提取需求、任务描述、前置产物、对等消息、角色上下文，组装成 WorkerContext，格式化为 LLM 可读的文本。 |
| **Harness** | 调用 M5 构建 prompt，再叠加记忆注入、Token 预算检查、生命周期事件发射、文件提取、审计日志。Harness 是 M5 的**调用方和增强层**。 |

### 2.3 LangGraph Engine（工作流模式）

**定位**：用户自定义 DAG 编排，灵活适配各种 SOP 场景。

```
用户输入 → 加载 workflow + node_bindings → 拓扑排序 → 分层 → 逐层执行
                                                              │
                                              ┌───────────────┘
                                              ▼
                                      for level in levels:
                                        ┌─ Agent 节点 → asyncio.gather(并行)
                                        ├─ Condition    → 表达式求值 + 分支裁剪
                                        ├─ Router       → LLM 选最佳候选
                                        ├─ Validation   → 校验 + retry/escalate/reject
                                        └─ HITL         → 暂停 + 持久化状态
```

**拓扑排序 + 层次并行**：从 workflow_edges 中筛选 `type=forward` 的边构建入度表，Kahn 算法拓扑排序，再按层次分组（同层节点无相互依赖 → `asyncio.gather` 并行执行）。

**7 种节点类型**：
| 类型 | 行为 | 关键配置 |
|------|------|---------|
| **Start** | 图入口标记，不执行 | 无 |
| **Agent** | 调用 LLM 执行任务 | `config.agent_id`, `config.instruction` |
| **Condition** | 基于前置产物求值表达式，裁剪分支 | `config.expression`, `on_true/false_node_key` |
| **Router** | 从候选节点中选一个（llm_select/broadcast/round_robin/best_match）| `config.strategy`, `config.candidates` |
| **Validation** | 校验前置产物（regex/schema/test/llm）| `config.validator`, `config.criteria`, `config.on_fail`(retry/escalate/reject) |
| **HITL** | 暂停等用户输入 | `config.timeout` |
| **End** | 图出口标记，不执行 | 无 |

**Reject/Escalate 边不参与拓扑排序的原因**：拓扑排序只使用 `type=forward` 的边来构建执行顺序。Reject/Escalate/Timeout/Fallback 是**异常路径**，不代表正常的执行流。当节点超时或失败时，引擎查阅 `timeout_edge`/`fallback_edge` 映射表来路由，不被拓扑排序阻塞。

**Agent 间通信**：

| 通道 | 方向 | 内容 |
|------|------|------|
| **artifacts 字典** | 上游 → 下游（单向） | 前置节点完整输出（截断至 3000 字符），注入 prompt |
| **PeerMailbox** | 任意 ↔ 任意（双向） | challenge / share / question / response |
| **workspace 文件** | 任意 → 所有（广播） | 代码文件完整写入磁盘 |

---

## 3. 横切保障层

### 3.1 Harness（横切拦截器）

```
Agent 执行生命周期:

  Engine 触发
      │
      ▼
  harness.before_execution(ctx)
      ├── _build_prompt()        → 调用 M5+M8 构建完整 prompt
      ├── _inject_context()      → 记忆 + RAG 上下文注入
      ├── _check_token_budget()  → 剩余 token < 1000 → 阻止执行
      └── _emit(EVENT_STARTED)   → Observer 事件
      │
      ▼
  Engine 调用 agent_chat(prompt)
      │
      ▼
  harness.after_execution(ctx, result)
      ├── _extract_files()       → 从输出解析代码块 → workspace
      ├── _record_tokens()       → Token 统计
      ├── _persist_with_retry()  → 记忆持久化（最多重试 2 次）
      ├── _audit_log()           → 结构化审计日志
      └── _emit(EVENT_COMPLETED) → Observer 事件
```

**4 个核心方法**：
| 方法 | 时机 | 职责 |
|------|------|------|
| `before_execution` | Agent 执行前 | Prompt 构建 + 上下文注入 + Token 预算检查 + 事件 |
| `after_execution` | Agent 执行后 | 文件提取 + Token 统计 + 记忆持久化 + 审计 |
| `verify` | M7 阶段 | 选非生产者 Agent 做盲审（只给需求+产物，不给思考链） |
| `cleanup` | 会话结束 | 清空 Token 计数器 + 暂停状态 + 会话资源 |

**BeforeExecutionResult（强类型数据类）**：
```python
@dataclass
class BeforeExecutionResult:
    prompt: Optional[str] = None       # 构建好的完整 prompt
    context: Optional[str] = None      # 额外上下文（记忆 + RAG）
    token_budget: Optional[dict] = None
    is_blocked: bool = False           # 是否被 Token 预算阻止
    block_reason: str = ""
```

**三引擎注入点**：
| 引擎 | before_execution 调用位置 | 传递的 ExecutionContext 字段 |
|------|--------------------------|---------------------------|
| Swarm | Phase 2 `_agent_execute` | instruction + user_message |
| Supervisor | `m6_execute_worker.py` | 含 artifacts + peer_msgs + org_role_context |
| LangGraph | `_execute_agent_node` | 含 artifacts + depends_on + code_output_required |

### 3.2 Loop Engine（错误恢复）

```
Agent 执行失败
      │
      ▼
 classify_error(error)
      ├── TRANSIENT (网络超时/429/503)  → retry(max 3次, 指数退避)
      ├── CONTENT  (输出格式错误/验证失败) → rollback → feedback → inject → retry
      └── FATAL    (API key/权限/配置)    → escalate_hitl
```

**三分类错误策略**：
| 错误类型 | 检测规则 | 处理 |
|---------|---------|------|
| **TRANSIENT** | timeout / rate_limit / 503 / connection_error | 自动重试，指数退避（1s→2s→4s） |
| **CONTENT** | json_parse_error / empty_output / verification_failed | 回滚→构建反馈→注入→重试 |
| **FATAL** | invalid_api_key / permission_denied / config_error | 立即升级 HITL，提示人工修复 |

**CONTENT 错误的四步恢复**：
1. **回滚** → 清除该 Agent 在 CollabState 中的产物
2. **构建反馈** → 提取错误信息（JSON 解析位置 / 验证失败原因）
3. **注入** → 将反馈追加到 Agent 的下一次执行指令中
4. **重试** → 重新调用 agent_chat（带修正指令）

**重试限制**：MAX_RETRIES=3，相同错误连续 2 次 → 提前升级（不等到第 3 次）。

### 3.3 HITL System（人机协作）

```
Swarm:
  三级检测(显式标记→结构化选项→特征评分) → hitl_notification → HITL 卡片
  │
  └─ 用户在卡片选择 / 输入框自由输入 → hitl_resume → 继续执行

Supervisor:
  M2 澄清确认 → HITL(确认/澄清/修改) → M1 重分析
  M3 编排 → HITL(缺少Agent → 邀请) → M3 重编排
  M6 执行 → HITL(审核/review) → 继续/重做
  M7 验证 → HITL(确认完成/修改/回到M1重分析)

LangGraph:
  HITL 节点 → 暂停 + _persist_paused_state(完整状态快照)
  Validation(escalate) → 转为 HITL
  Resume → _load_paused_state → 从断点继续
```

**组件设计**：前端 `HITLOptions` 为共享组件，支持 5 种模式（`interactive` / `readonly` / `selectable` / `multiSelect` / `answerInput`），三引擎统一复用。

---

## 4. 记忆系统

```
┌──────────────────────────────────────────────────────┐
│  L4: 项目记忆 (Redis, 全项目共享)                   │
│  • 技术规范、设计决策、架构模式                      │
│  • TTL: 无限制（手动管理）                           │
├──────────────────────────────────────────────────────┤
│  L3: 团队记忆 (PostgreSQL, 团队内共享)              │
│  • SOP 模板、团队偏好、协作历史                      │
│  • TTL: 30 天未访问 → 归档                           │
├──────────────────────────────────────────────────────┤
│  L2: 会话记忆 (PostgreSQL + Context Manager 动态注入)│
│  • 对话历史、关键决策、HITL 问答记录                 │
│  • Token 预算裁剪策略                                │
├──────────────────────────────────────────────────────┤
│  L1: 上下文窗口 (LLM 原生, 临时)                    │
│  • 当前 prompt + 前置产物 + PeerMailbox 消息         │
│  • TTL: 单次请求                                     │
└──────────────────────────────────────────────────────┘
```

**Token 预算裁剪策略**：
```
总预算: 1,000,000 tokens/session

注入优先级 (从高到低):
1. System Prompt (必选，不可裁剪)
2. 当前任务描述 + 用户需求 (必选)
3. 前置节点产物 (按依赖链截断，3000 字符/产物)
4. PeerMailbox 消息 (5 条/Agent)
5. 记忆上下文 (L2 优先，L3 补充)
6. 对话历史 (最近 5 轮)
```

**四层生命周期**：
| 层级 | 存储 | 生命周期 | 访问范围 |
|------|------|---------|---------|
| L1 Context Window | LLM 内存 | 单次请求 | 当前 Agent |
| L2 Session | PostgreSQL memory | 会话期间 | 会话内所有 Agent |
| L3 Team | PostgreSQL memory | 30 天 | 团队内所有会话 |
| L4 Project | Redis | 无限 | 跨团队全局 |

---

## 5. 聊天室设计

### 5.1 暗流信息架构

```
┌─────────────────────────────────────────────────┐
│              表面对话流 (ChatStream)              │
│  用户消息 ─ Agent 消息 ─ HITL 卡片 ─ 系统分隔线  │
│  ┌────────────────────┐                         │
│  │  ThinkingIndicator  │  ← Agent 思考状态条     │
│  ├────────────────────┤                         │
│  │   InputModeBanner   │  ← 当前输入模式提示     │
│  ├────────────────────┤                         │
│  │     ChatInput       │  ← 输入框行为机         │
│  └────────────────────┘                         │
├─────────────────────────────────────────────────┤
│               暗流抽屉 (DrawerHost)               │
│  📋 任务计划  │  📁 产物文件  │  👥 团队  │  🔀 流程  │
│  WorkPlan     │  Artifacts    │  Team    │  Workflow │
└─────────────────────────────────────────────────┘
```

**设计原则**：表面保持对话的简洁流畅，详细信息存放在抽屉中。用户需要时才展开，不影响对话流的连续性。

### 5.2 输入框行为机

```
         ┌──────────────────────────────────────┐
         │             IDLE (空闲)               │
         │  "输入消息..."  → 发送 chat 消息      │
         └───┬──────────┬──────────┬────────────┘
             │          │          │
    ┌────────┘   ┌──────┘   ┌──────┘
    ▼            ▼          ▼
┌────────┐  ┌──────────┐  ┌──────────────┐
│ANSWERING│  │THINKING  │  │ INTERRUPTING │
│ "回答中"│  │ "思考中…"│  │ "介入中…"    │
│ 输入→发 │  │ 输入→中  │  │ 输入→中断    │
│ 送HITL │  │ 断(软)   │  │ (硬+软)      │
│ 响应   │  │           │  │              │
└────────┘  └──────────┘  └──────────────┘
```

**永不禁用**：输入框在任何状态下都可输入——思考时可以软中断、HITL 待答时可以代替按钮自由输入、暂停后可以恢复。这保证了用户始终有一条沟通路径，不会因系统状态而阻塞。

### 5.3 多抽屉系统

- **最多 3 个同时打开**：`openDrawers: DrawerState[]`（kind + width + order）
- **独立宽度**：每个抽屉可拖拽调整（20%-60%）
- **Esc 关闭**：单抽屉 Esc 关闭最近一个，多抽屉 Esc 关闭全部
- **移动端**：退化为 Bottom Sheet，从底部滑出

---

## 6. 关键设计决策

### 6.1 为什么是三个独立的引擎，而非统一引擎？

**三模式代表了三种不同的协作范式**，它们的核心约束不同：

| 模式 | 核心约束 | 为什么不能统一 |
|------|---------|--------------|
| **Swarm** | 无预设流程，Agent 自由发言 | 流程是**涌现**的——从讨论中自然产生 HITL 触发点 |
| **Supervisor** | 固定 M0-M7 管道 + 组织层级 | 流程是**预定义**的——按阶段推进，按层级委派审核 |
| **LangGraph** | 用户自定义 DAG | 流程是**声明式**的——节点+边定义执行拓扑 |

强行统一的代价：要么限制 Swarm 的灵活性，要么稀释 Supervisor 的结构化，要么让 LangGraph 的 DAG 失去意义。三引擎**共享能力层**（Harness、Memory、LLM Adapter），但在编排逻辑上保持独立，是最小成本获得最大覆盖的方案。

### 6.2 为什么聊天室是唯一入口？

所有协作模式的用户交互都遵循**同一个心智模型**：发送消息 → 看到回复 → 做决策。无论背后是 Swarm / Supervisor / LangGraph，用户面对的都是同一个聊天界面。模式差异体现在**暗流信息**（抽屉中的任务树 vs DAG 图 vs 团队状态），而非交互方式的变更。

### 6.3 为什么 Harness 是横切的而非分散的？

三个引擎有 **80% 的重复逻辑**：上下文注入、Token 管控、文件提取、审计日志、事件发射。如果分散在各引擎中实现，每次修改需要同步 3 个文件。Harness 通过 4 个钩子（`before/after/verify/cleanup`）实现了**关注点分离**——引擎专注于编排逻辑，Harness 专注于保障逻辑。各引擎通过传入不同的 `ExecutionContext` 字段来适配，Harness 根据字段内容自动调整行为。

### 6.4 为什么 HITL 不锁定输入框？

传统 HITL 设计通常**禁用**输入框，要求用户必须从预定义选项中点击。我们的设计反其道而行：选项卡片提供快捷入口，但输入框**永不禁用**。原因是：

1. **LLM 输出的选项不可靠**：可能遗漏"我有其他想法"这种关键选项，可能选项相同只是措辞不同
2. **用户应该有最终表达权**：系统不能预设用户只能从 N 个选项中选
3. **降级路径一致**：选项卡片不渲染时（如 options 数组为空），用户仍可通过输入框交互
4. **行为机统一**：无论 HITL 状态如何，Enter 键始终是"发送"，用户无需学习新模式

---

## 7. 技术栈总览

| 层 | 技术 | 选型理由 |
|----|------|---------|
| 编排引擎 | LangGraph StateGraph | 内置 checkpoint、条件路由、状态持久化 |
| LLM 适配 | LiteLLM | 统一 20+ 模型提供商接口 |
| 后端 | FastAPI + WebSocket | 异步原生支持，WebSocket 连接可与 REST 共享路由 |
| 数据库 | PostgreSQL 16 (asyncpg) | JSONB 存储 workflow 配置，UUID 主键，TIMESTAMPTZ |
| 缓存 | Redis 7 | 会话状态、Blackboard 广播、限流计数器 |
| 状态管理 | React useReducer | 纯函数 reducer，WS 事件 → Action → 确定性状态变更 |
| 流式渲染 | stream_token WS 事件 | 逐 token 推送，前端更新流式占位消息 |
| 构建 | Vite | HMR 热更新，Proxy 转发 WebSocket |

---

*文档基于 v5.0 代码自动生成，最后更新：2026-06-25*

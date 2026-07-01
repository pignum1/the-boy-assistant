# The Boy Assistant — 系统设计架构文档 v5.0

> 企业级 AI Multi-Agent 协作平台
> 技术栈：Python 3.12 + FastAPI + LangGraph + React 18 + TypeScript + PostgreSQL 16 + Redis 7

---

## 第 1 章：系统概述

### 1.1 项目定位

The Boy Assistant 是一个**三模式企业级多 Agent 协作平台**，提供群聊讨论（Swarm）、主管委派（Supervisor）、工作流编排（LangGraph）三种协作范式，通过统一的聊天室界面和 Harness 横切保障层，为企业研发团队提供从自由讨论到严格 SOP 执行的完整协作工具链。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **三模式协作** | Swarm（群聊）/ Supervisor（主管）/ LangGraph（工作流），根据团队需求切换 |
| **七种执行模式** | single_pass / chain_of_thought / plan_execute / react / rewoo / reflexion / self_consistency |
| **全链路可观测** | LangFuse 自部署 — Traces / Spans / Generations 三层追踪 + Scores 评分 + 告警 |
| **智能委派** | 基于组织层级树的自动委派、审核、升级链 |
| **HITL 人机协作** | 三级检测 + 状态机卡片 + 永不禁用输入框 |
| **幻觉对抗** | M7 独立盲审 → drift_detected → 回 M1 重分析 |
| **故障自愈** | Loop Engine 三分类错误策略 + 四步恢复流程 |
| **横切保障** | Harness 拦截器统一 Prompt构建/Token管控/文件提取/审计 |
| **流式渲染** | 逐 token 推送 + 代码块高亮 + Markdown 实时渲染 |
| **工作空间隔离** | 按 Session 隔离的文件系统 + Snapshot 快照管理 |

### 1.3 用户角色

| 角色 | 场景 |
|------|------|
| **普通用户** | 发起需求，接收 Agent 产出，在 HITL 卡片中选择或自由输入 |
| **团队 Leader** | 配置 Supervisor 委派树，审核 Agent 产出，介入重规划 |
| **流程设计者** | 在 SOP 设计器中定义 LangGraph 工作流（节点+边+Agent 绑定） |

---

## 第 2 章：DDD 领域建模

### 2.1 限界上下文划分

系统按 DDD 战略设计划分为 **5 个限界上下文 + 1 个横切保障层**：

```
┌──────────────────────────────────────────────────────────────────┐
│                        api/v1/ (接口层)                          │
│   仅做参数校验 + 调用领域服务，不含业务逻辑                          │
├──────────┬──────────┬──────────┬──────────┬─────────────────────┤
│ Identity │  Agent   │Knowledge │ Workflow │  Infrastructure     │
│ (身份域)  │ (智能域)  │(知识域)   │(编排域)   │  (基础设施域)        │
├──────────┴──────────┴──────────┴──────────┴─────────────────────┤
│                      models/ (数据模型层)                         │
│                      schemas/ (数据传输层)                        │
├──────────────────────────────────────────────────────────────────┤
│  core/ (配置/数据库)  adapters/ (LLM适配)  tools/ (工具执行)       │
├──────────────────────────────────────────────────────────────────┤
│              Harness 横切保障层（独立于领域边界）                   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 各领域详述

#### Identity 域（身份域）

**核心职责**：定义"谁"（Persona）、"用什么脑"（Model）、"有什么手"（Tool）

| 聚合根/实体 | 服务 | 说明 |
|-----------|------|------|
| **Persona** | persona_service | 角色定义：system_prompt + capabilities + tools_declared |
| Model | model_router | 模型注册 + 智能路由（复杂度→模型选择） |
| Tool | tool_registry | 工具注册与发现，MCP 协议支持 |

#### Agent 域（智能域）

**核心职责**：单个 Agent 的完整智能闭环（记忆→技能→推理→输出）

| 聚合根/实体 | 服务 | 说明 |
|-----------|------|------|
| **Agent** | agent_factory | Agent 组装（Model + Persona + Tools） |
| Memory (L1-L4) | memory_manager | 四层记忆管理，Token 预算裁剪 |
| Skill | skill_registry | 技能文件注册与执行 |
| Context | context_manager | 上下文窗口管理 + M5 Context Pipeline |
| Fallback | fallback_chain | 模型降级链 |

#### Knowledge 域（知识域）

**核心职责**：知识的外部存储、检索与注入

| 聚合根/实体 | 服务 | 说明 |
|-----------|------|------|
| **KnowledgeBase** | knowledge_service | 知识库 CRUD |
| KnowledgeChunk | chunker / embedder | 文档分块 + 向量化 |
| Retrieval | hybrid_search / reranker | Dense+Sparse 混合检索 + 精排 |

#### Workflow 域（编排域，核心域）

**核心职责**：多 Agent 协作编排 — 团队组建、流程定义、任务执行、人机协作

| 聚合根/实体 | 服务 | 说明 |
|-----------|------|------|
| **Team** | team_manager | 团队 + 成员 + 角色插槽 |
| **Session** | session_service | 会话生命周期 + 消息历史 |
| **Workflow** | sop_service | 工作流定义（节点+边） |
| Swarm Engine | swarm_engine | 三阶段群聊 |
| Supervisor Engine | supervisor_engine | M0-M7 管道 |
| LangGraph Engine | langgraph_engine | 拓扑排序执行 |
| HITL | hitl_detector | 三级检测 |
| Org | org_hierarchy | 组织层级树 |
| M5/M8 | context_pipeline / peer_mailbox | 上下文组装 / 对等通信 |

#### Infrastructure 域（基础设施域）

**核心职责**：与外部系统交互的技术基础设施

| 模块 | 说明 |
|------|------|
| core/ (config, database, security) | 配置 + async SQLAlchemy + Fernet 加密 |
| adapters/llm/ (base, litellm, mock) | LiteLLM 统一适配 + 超时 + 重试 |
| tools/ (file_ops, terminal) | 文件操作 + 终端执行 |
| workspace/ (manager, snapshot, file_proxy) | 工作空间隔离 + 快照管理 |
| observer/ (events, bus, persister) | 事件模型 + 异步总线 + 持久化 |

### 2.3 四色领域模型

应用 Peter Coad 四色建模法对核心实体进行分类：

| 颜色 | 原型 | 系统中对应实体 |
|------|------|--------------|
| 🔴 MI 时标 | Moment-Interval | Session（会话）、Task（任务）、HITLRequest（人工请求）、Verification（验证记录）、AgentExecution（执行记录） |
| 🟢 PPT 实体 | Part-Place-Thing | Agent（智能体）、Team（团队）、Workflow（工作流）、Workspace（工作区）、Artifact（产物） |
| 🟡 Role 角色 | Role | TeamMember（成员-角色绑定）、Leader（主管）、Reviewer（审核员）、Worker（执行者）、Supervisor（上级） |
| 🔵 DESC 描述 | Description | Persona（角色定义）、Capability（能力描述）、Tool（工具声明）、ModelConfig（模型配置）、Skill（技能） |

**四色关系**：
- 一个 **Session**（MI）记录了 Team（PPT）在某个时间段的协作
- TeamMember（Role）是 Agent（PPT）在特定 Team（PPT）中的参与方式
- Persona（DESC）描述了 Agent（PPT）应具备的能力和行为

### 2.4 核心域事件风暴

以 **协作编排域** 为主线的事件风暴：

```
👤用户 → [SendMessage] → ConversationStarted → Router → IntentRouted
→ [AnalyzeRequirement] → RequirementAnalyzed → [DecomposeTasks] → TaskDecomposed
→ [DispatchAgent] → AgentDispatched → AgentThinking → ArtifactProduced
→ [VerifyArtifact] → VerificationStarted → drift_detected? → [ReAnalyze] ⤴ M1
→ VerificationCompleted → [RequestHITL] → HITLRequested → 👤用户
→ UserResponded → SessionCompleted
```

**读模型**（绿色）：ChatStream、WorkPlanDrawer、ArtifactsDrawer、WorkflowDrawer

**热点问题**（红色）：循环检测（Loop Engine）、幻觉纠正（M7 drift→M1）、Token 溢出（Context Manager）

### 2.5 领域间通信契约

| 规则 | 说明 |
|------|------|
| **跨域引用** | 仅通过 UUID 字符串引用，禁止直接导入 ORM 模型 |
| **API 协调** | 跨域操作在 API 层获取数据后传入领域服务 |
| **基础设施** | Infrastructure 域可被任意域依赖（无方向限制） |
| **领域事件** | 通过 Observer EventBus 发布领域事件，异步解耦 |
| **禁止循环** | 严禁跨层调用（api 不能直接操作 ORM，services 不能调用 api） |

---

*继续下一章...*

---

## 第 3 章：五层技术架构

### 3.1 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                   交互层 (Frontend)                         │
│  ChatRoomView · ChatStream · DrawerHost · HITLCard · Input  │
├─────────────────────────────────────────────────────────────┤
│                   通信层 (Communication)                    │
│  WebSocket 单连接 · useWsEvents · Stream Token · Vite Proxy │
├──────┬──────────────┬──────────────┬────────────────────────┤
│Swarm │ Supervisor   │  LangGraph   │   ← 编排层 (Workflow)  │
│Engine│ Engine       │  Engine      │   三模式协作引擎        │
├──────┴──────────────┴──────────────┴────────────────────────┤
│                   能力层 (Capability)                       │
│  Agent Factory · Memory(L1-L4) · Context Pipeline · RAG    │
│  Model Adapter · Fallback Chain · Workspace Mgr · Pool     │
├─────────────────────────────────────────────────────────────┤
│                   数据层 (Data)                             │
│     PostgreSQL 16 (主存储) · Redis 7 (缓存/消息)             │
├─────────────────────────────────────────────────────────────┤
│           Harness 横切保障层 (Cross-Cutting)                 │
│  before → after → verify → cleanup · Observer · Loop Engine │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 交互层

#### ChatRoomView — 聊天室主容器

所有协作模式的**唯一入口**。内部使用 `useChatRoomState` reducer 管理 `ChatRoomState`，通过 `useWsEvents` 连接 WebSocket。

**暗流信息架构**：
- **表面对话流**：ChatStream 按时间线渲染消息（用户/Agent/HITL/分隔线）
- **暗流抽屉**：DrawerHost 承载 4 种抽屉，最多同时开 3 个
- **思考指示器**：ThinkingIndicator 显示当前活跃 Agent，超过 3 个自动折叠为一行
- **输入框行为机**：四状态切换，永不禁用

#### HITL 卡片状态机

```
pending ──(用户点击选项)──→ answered（显示回答 + 原选项只读）
pending ──(用户点"我来回答")──→ answering ──(输入框Enter)──→ answered
```

前端使用共享组件 `HITLOptions`（5 种模式：interactive / readonly / selectable / multiSelect / answerInput），三引擎统一复用。

### 3.3 通信层

#### WebSocket 单连接多路复用

前端与后端的**唯一 WebSocket 连接**，通过 `data.type` 字段区分 10+ 种消息类型：

| type | 方向 | 说明 |
|------|------|------|
| agent_message | S→C | Agent 完整消息 |
| stream_token | S→C | 流式 token |
| hitl_notification | S→C | HITL 触发 |
| task_status / task_dag | S→C | 任务状态 / DAG 结构 |
| files_changed | S→C | 产物文件更新 |
| reasoning_complete | S→C | 思考链完成 |
| message_complete | S→C | 会话完成 |
| error | S→C | 错误通知 |
| chat | C→S | 用户发送消息 |
| hitl_resume | C→S | 用户 HITL 响应 |
| interrupt | C→S | 用户中断 |

#### 流式渲染

```
后端: agent_chat_stream → async for token → send_fn({type:"stream_token", payload:{token}})
前端: WS/STREAM_TOKEN → 创建/追加流式占位消息(isStreaming=true) → agent_message 替换
```

### 3.4 模块依赖关系

```
api/v1 → services → models
                  ↘       ↗
                adapters / core
```

**依赖规则**：
- `api/` 只做参数校验 + 调用 service + 格式化响应
- `services/` 是业务核心，依赖 models 和 adapters，不依赖 api
- `models/` 纯数据定义，不依赖 services 和 api
- Infrastructure 域可被任意层依赖
- 跨域只通过 UUID 引用，禁止直接导入 ORM

---

## 第 4 章：三模式协作引擎

### 4.1 模式分发

```python
# router.py
mode = (team.collaboration_mode or "supervisor").lower()
engine = _resolve_engine(mode)
# swarm → Swarm Engine
# supervisor → Supervisor Engine
# langgraph → LangGraph Engine
await engine.run(session_id, team, user_message, send_fn=send_fn, harness=harness)
```

三引擎共享公共接口 `run()` 和 `resume()`，均接受 `harness` 参数。

### 4.2 Swarm Engine（群聊模式）

**定位**：多 Agent 自由讨论，无需预设流程。流程是**涌现**的——从讨论中自然产生 HITL 触发点。

**三阶段流水线**：

```
Phase 1: RoundTable 讨论
  ├─ 轮询所有 Agent 发言（轮次控制，最多 3 轮）
  ├─ 每轮收集所有观点
  └─ HITL 检测（每轮结束后检测是否需要人工介入）

Phase 2: Agent Execution
  ├─ 有产出任务的 Agent 调用 LLM 生成代码/文档
  ├─ 注入 Harness 横切拦截
  └─ 文件提取到 workspace

Phase 3: Completion / HITL
  ├─ 无 HITL → 推送摘要 → 结束
  └─ 有 HITL → 暂停 → 等用户回复 → 继续
```

**HITL 三级检测**（hitl_detector.py）：

| 级别 | 检测方式 | 置信度 |
|------|---------|--------|
| L1 | `__HITL__` 显式标记 | 1.0 |
| L2 | `**方案A/方案B**` 结构化选项 | 0.9 |
| L3 | 6 特征加权评分 ≥ 3 | 0.7 |
| L4 | 关键词兜底（"选择/确认/请回复"+"方案"）| 0.5 |

**6 特征评分公式**：
```
semantic_score = OPTION_LIST×2 + QUESTION×1 + USER_DIRECT×1
               + LAST_SPEAKER×1 + NO_RECENT×1 + EXCLUDED×(-1)
触发阈值: ≥ 3
```

- OPTION_LIST (×2)：文本含 "A/B" 或 "方案一/二" 结构
- QUESTION (×1)：含问号 + 选择类动词
- USER_DIRECT (×1)：直接呼唤用户（"请你/您"）
- LAST_SPEAKER (×1)：最后发言者 → 更可能是总结性提问
- NO_RECENT (×1)：近期无用户消息 → 应暂停等输入
- EXCLUDED (×-1)：含排除关键词（"不需要/自行决定"）

### 4.3 Supervisor Engine（主管模式）

**定位**：结构化多 Agent 协作，固定 M0-M7 管道，支持组织层级委派。流程是**预定义**的——按阶段推进，按层级委派审核。

#### M0-M7 LangGraph 状态图

```
graph.py: StateGraph<CollabState>
  注册 9 个节点: m0_intent / m1_analyze / m2_clarify / m3_orchestrate
                 / m4_decompose / m1_rebalance / m6_execute / m7_verify / hitl
  条件边: 根据节点返回值路由到下一节点
```

```
用户输入
  ↓
M0 意图路由 ──(单Agent)──→ 直接回复 → END
  │
  └──(多Agent)──→ M1 需求分析
                    ├──(确认)──→ HITL（展示方案，等用户确认）
                    └──(澄清)──→ M2 澄清确认 → HITL（问用户澄清问题）
                                    ↓
                              M3 Agent 编排
                                ├──(就绪)──→ M4 任务分解
                                └──(缺Agent)──→ HITL（邀请 Agent）
                                                    ↓
                                              M4 任务分解 → DAG 图
                                                    ↓
                                              M6 层级执行（核心）
                                                    ↓
                                              M7 独立验证
                                     ┌──────────┼──────────┐
                                     ↓          ↓          ↓
                                   pass       major      drift
                                     ↓          ↓          ↓
                                  HITL确认    M6重做    M1重分析
```

#### 组织层级如何影响执行

```
DB: team_supervisor_configs(leader_member_id) + team_supervisor_relations(member→supervisor)
        ↓
m6_org_loader: load_org_structure(team_id)
        ↓
CollabState.org_structure = {leader, relations, member_roles}
        ↓
m6_delegate: _delegate_think() 检查下属 → 委派 / 自行执行
m6_collect: 按层级汇总 result → 上级审核
m6_escalate: find_escalation_target() 沿树升级
```

每个 Agent 执行时，prompt 自动注入 `generate_role_context()`:
```
架构师: "你是架构师（架构师-Agent），向产品经理汇报"
后端工程师: "你是后端工程师（后端工程师-Agent），向架构师汇报"
```

#### M7 验证路由

| 验证结果 | 路由 | 理由 |
|---------|------|------|
| passed | → HITL 确认 | 给用户最终审核 |
| major（代码 bug） | → M6 重做 | 问题在实现层，直接修复 |
| drift_detected | → M1 重分析 | 需求理解偏差，修 M6 没用 |
| critical | → HITL 升级 | 严重偏离，人工决策 |

### 4.4 LangGraph Engine（工作流模式）

**定位**：用户自定义 DAG 编排，流程是**声明式**的——节点+边定义执行拓扑。

#### 执行流程

```
1. 加载配置
   team_langgraph_configs → workflow_id
   workflows 表 → 工作流定义
   workflow_nodes 表 → 节点（config.agent_id 绑定 Agent）
   workflow_edges 表 → 边（仅 type=forward 参与拓扑排序）

2. 拓扑排序 (Kahn 算法)
   in_degree = {node_id: 入度数}
   从入度为 0 的节点开始 → 逐层分组

3. 分层并行执行
   for level in levels:
     ├─ Agent 节点 → asyncio.gather（同层并行）
     ├─ Condition 节点 → 求值表达式 → 裁剪未选分支
     ├─ Router 节点 → 选最佳候选（llm_select/broadcast/round_robin/best_match）
     ├─ Validation 节点 → 校验 → retry/escalate/reject
     └─ HITL 节点 → 暂停 → _persist_paused_state → 等 resume
```

#### 7 种节点类型

| 类型 | 行为 | 关键配置 |
|------|------|---------|
| Start | 入口标记，不执行 | 无 |
| Agent | 调用 LLM 执行 | config.agent_id, config.instruction |
| Condition | 表达式求值，裁剪分支 | config.expression, on_true/false_node_key |
| Router | 从候选节点选最优 | config.strategy, config.candidates |
| Validation | 校验前置产物 | config.validator, config.criteria, config.on_fail |
| HITL | 暂停等用户 | config.timeout |
| End | 出口标记，不执行 | 无 |

#### 节点间通信

| 通道 | 方向 | 实现 |
|------|------|------|
| artifacts 字典 | 上游 → 下游 | 前置节点输出截断至 3000 字符，注入 prompt |
| PeerMailbox | 任意 ↔ 任意 | challenge/share/question/response |
| workspace 文件 | 任意 → 所有 | _extract_node_files 写入磁盘 |

### 4.5 三模式对比

| 维度 | Swarm | Supervisor | LangGraph |
|------|-------|------------|-----------|
| **流程确定性** | 涌现（低） | 固定管道（高） | 声明式（中-高） |
| **HITL 触发** | 三级检测（自动） | M2/M3/M6/M7（固定点） | HITL 节点 + Validation escalate |
| **并行能力** | 单轮并行发言 | M6 按 DAG 层级并行 | 同层节点 gather 并行 |
| **组织层级** | 不适用 | DB 配置 + LCA 审核 + 树上升级 | 不适用 |
| **适用场景** | 头脑风暴、方案讨论 | 需求→设计→开发→测试→部署 | 固定 SOP 流程 |

---

## 第 5 章：Agent 全生命周期与 Harness 接入

### 5.1 Agent 执行生命周期的 6 个阶段

```
┌──────────┐    ┌─────────────────┐    ┌──────────┐    ┌──────────────────┐    ┌──────────┐    ┌──────────┐
│ 1.引擎触发 │ → │ 2.Harness.before │ → │ 3.LLM调用 │ → │ 4.Harness.after  │ → │5.引擎后处理│ → │6.Observer│
│ 构建 ctx  │    │ _build_prompt    │    │agent_chat │    │ _extract_files   │    │ 推送 WS   │    │ 发射事件 │
│           │    │ _inject_context  │    │ (stream)  │    │ _record_tokens   │    │ 更新状态  │    │ 持久化   │
│           │    │ _check_token     │    │           │    │ _persist+audit   │    │           │    │          │
└──────────┘    └─────────────────┘    └──────────┘    └──────────────────┘    └──────────┘    └──────────┘
```

**三引擎注入点**：

| 引擎 | before_execution 注入位置 | 传递的 ExecutionContext |
|------|--------------------------|------------------------|
| Swarm | Phase 2 `_agent_execute` | instruction + user_message |
| Supervisor | `m6_execute_worker.py` | artifacts + peer_msgs + org_role_context + retry_feedback |
| LangGraph | `_execute_agent_node` | artifacts + depends_on + code_output_required + workspace_path |

### 5.2 Context 组装流程

Harness._build_prompt 的 6 层组装链：

```
1. M5 context_pipeline.build_context()
   ├─ requirement_anchor（原始需求）
   ├─ current_task（任务描述）
   ├─ previous_artifacts（仅依赖链中的前置产物，截断 3000 字符）
   └─ agent_messages（M8 PeerMailbox 对等消息）

2. M8 peer_mailbox.format_for_context()
   └─ 拉取发给该 Agent 的未读消息

3. 记忆注入（_inject_context）
   └─ ContextManager 从 L2/L3 提取相关记忆

4. Token 预算检查（_check_token_budget）
   └─ 剩余 < 1000 → 阻止执行

5. 代码格式要求（可选）
   └─ code_output_required=True → 追加代码块路径格式

6. format_context() → 文本 prompt
```

### 5.3 Workspace 工作空间隔离

```
路径模型: {WORKSPACE_BASE}/{session_id}/
         /Users/weixingyang/the-boy-workspaces/61dac2d5-9d0c-4d95-a127-6c09c7ebf553/

生命周期:
  Session 创建 → WorkspaceManager.get_or_create(session_id)
  Agent 执行 → code block 正则解析 → 写入 workspace
  用户查看 → ArtifactsDrawer 显示文件列表 + 预览
  会话结束 → 可选归档/删除

文件提取:
  _extract_node_files(content, node_key, ws_path)
  ├─ regex: ```language path/to/file\n...\n```
  ├─ 验证路径不越权（startswith ws_path）
  └─ os.makedirs + write
```

### 5.4 Token 预算裁剪策略

```
总预算: 1,000,000 tokens / session

注入优先级（从高到低）:
1. System Prompt ........................ 必选，不可裁剪
2. 当前任务描述 + 用户需求 .............. 必选
3. 前置节点产物 ........................ 按依赖链截断，3000字符/产物
4. PeerMailbox 消息 .................... 最多 5 条/Agent
5. 记忆上下文 (L2 优先, L3 补充) ....... 按重要性截断
6. 对话历史 ............................ 最近 5 轮
```

---

## 第 5.5 章：Agent 执行模式

> 详细设计文档：`docs/agent-execution-modes.md`  
> 对应架构图：`docs/images/07-Agent执行模式.html`

Agent 的 `execution_mode` 字段决定其推理策略。编排层不干预 Agent 怎么思考 —— 仅 `agent_executor.py` 读取该字段并路由到对应执行器。

### 七种模式概览

| 模式 | 常量 | 适用场景 | Span 结构 |
|------|------|---------|----------|
| **单次调用** | `single_pass` | 简单问答 | 1 span → 1 generation |
| **思维链** | `chain_of_thought` | 复杂推理 | 1 span → 1 generation |
| **规划执行** | `plan_execute` | 分阶段规划 | 1 span → 3 phase spans → 3 generations |
| **ReAct** | `react` | 工具调用 | 1 span → N iter spans → 1-2N generations |
| **ReWOO** | `rewoo` | 并行工具执行 | 1 span → 3 phase spans → N generations |
| **Reflexion** | `reflexion` | 自我纠错 | 1 span → critique/redo spans → 2R-1 generations |
| **自一致性** | `self_consistency` | 多方案对比 | 1 span → sampling+merge spans → 4 generations |

### 模式选择

模式仅由 Agent 的 `execution_mode` 字段决定，三引擎（Swarm/Supervisor/LangGraph）统一通过 `AgentExecutor.execute()` 调度，`node_key` 仅作日志标识。

所有模式自动集成 LangFuse 追踪 — span 名称格式为 `[{exec_mode}] {agent_name} ({role})`，输入输出和元数据完整记录。

---

## 第 6 章：异常处理与幻觉对抗

### 6.1 Loop Engine — 错误恢复

```
Agent 执行失败
      ↓
classify_error(error)
      ├── TRANSIENT (timeout/429/503)
      │    └→ 自动重试（指数退避 1s→2s→4s，max 3次）
      │
      ├── CONTENT (json_parse/empty_output/verify_failed)
      │    └→ 四步恢复:
      │       1. Rollback  → 清除 CollabState 中的产物
      │       2. Feedback  → 提取错误信息构建修正指令
      │       3. Inject    → 追加到 Agent 的下一次执行 prompt
      │       4. Retry     → 重新调用 agent_chat
      │
      └── FATAL (api_key/permission/config)
           └→ 立即 escalate_hitl（不重试，人工修复）
```

**重试限制**：
- MAX_RETRIES=3
- 相同错误连续出现 2 次 → 提前升级（不等到第 3 次）
- 不同错误分别计数

### 6.2 幻觉检测与纠正链路

M7 Verifier 采用**盲审**设计——只给验证员看原始需求和产物，不给 Worker 的思考链，防止确认偏差。

```
M7 Verifier 输入:
  ✅ 看到: 原始需求 + 各任务产出
  ❌ 看不到: Worker 思考过程 / Supervisor 指导 / 对话历史 / HITL 记录

检测维度:
  1. 功能完整性: 需求中每个功能点是否都有对应实现?
  2. 偏离检测: 实现是否偏离了需求? drift_detected: true/false
  3. 代码质量: 明显 bug / 安全漏洞 / 性能问题?
  4. 文件完整性: 期望的产出文件是否已生成?

纠正链路:
  drift_detected=true
    → M1 重分析（带验证反馈"需求理解偏差: xxx"）
    → 清除 task_dag（让 M4 重新分解）
    → 清除 artifacts（从干净上下文开始）
    → M4 重分解 → M6 重执行 → M7 再验证
```

**与普通异常的关系**：
- major（代码 bug）→ M6 重做（修复实现层）
- drift（理解偏差）→ M1 重分析（修复需求层）
- critical（严重偏离）→ HITL（人工决策）

### 6.3 安全过滤

**Prompt Injection 检测**（8 种正则模式）：
- `ignore previous instructions` / `ignore all prior`
- `system prompt` / `you are now`
- `DAN` / `jailbreak` / `do anything now`
- `pretend` / `roleplay`

**PII 脱敏**（5 种正则模式）：
- 手机号（中国大陆 11 位）
- 身份证号（18 位）
- API Key（sk-xxx / api-xxx 格式）
- 密码（password=xxx / passwd=xxx）
- 邮箱

**过滤时机**：消息进入引擎前（`ws.py` 中 `save_and_send` 之前检测）

### 6.4 Fallback Chain — 模型降级

```
主模型 (primary)
    ├── timeout → 自动重试 (max 3)
    ├── rate_limit → 退避等待
    └── 不可恢复错误 → fallback 次选模型 (secondary)
        └── 次选失败 → mock adapter（测试环境）
```

**超时配置**：
- DeepSeek: 120s（大模型推理慢）
- 其他模型: 60s（默认）

---

## 第 7 章：通信与数据流

### 7.1 前端状态管理

ChatRoomState 使用纯函数 `useReducer` 管理：

```
WS 事件 → chatRoomReducer(action) → 新 state
                ↑
        纯函数，无副作用
        (state, action) → state

Action 分类:
  WS_*   — 来自 WebSocket 入站事件（AGENT_MESSAGE / HITL_REQUEST / STREAM_TOKEN ...）
  UI_*   — 来自前端 UI 交互（USER_SEND_MESSAGE / HITL_ANSWER / TOGGLE_DRAWER ...）
  CTRL_* — 内部控制（INIT_SESSION / WS_CONNECTED / HISTORY_LOADED）
```

### 7.2 Observer 事件流

15 种 EventType，异步 EventBus + 独立 DB 会话持久化：

```
Event 产生 → EventBus.emit(event) → asyncio.create_task(handler)
                                          ├── persister.persist(db, event)
                                          └── 其他订阅者

EventType:
  生命周期: SESSION_STARTED · SESSION_ENDED
  Agent:    AGENT_EXECUTION_STARTED · AGENT_EXECUTION_COMPLETED
  任务:     TASK_CREATED · TASK_COMPLETED · TASK_FAILED
  HITL:     HITL_REQUESTED · HITL_RESUMED
  验证:     VERIFICATION_PASSED · VERIFICATION_FAILED
  文件:     FILES_CHANGED
  错误:     ERROR_OCCURRED
  记忆:     MEMORY_INJECTED · TOKEN_BUDGET_EXCEEDED
```

**持久化保障**：`persist()` 使用独立的 `async_session()`，不依赖调用方的 DB 事务，确保事件不丢失。

---

## 第 8 章：关键设计决策（ADR）

### ADR-001: 三引擎独立 vs 统一引擎

**决策**：保持三个独立引擎，共享能力层。

**理由**：
- Swarm 的流程是**涌现**的（从讨论中自然产生 HITL），Supervisor 是**预定义**的（M0-M7 固定管道），LangGraph 是**声明式**的（用户定义 DAG）
- 统一引擎要么限制 Swarm 灵活性，要么稀释 Supervisor 结构化，要么让 DAG 失去意义
- 三引擎共享 Harness/LLM Adapter/Memory 等能力层，编排逻辑独立

### ADR-002: 聊天室为唯一入口

**决策**：无论后台运行哪种引擎，用户始终面对同一个聊天界面。

**理由**：
- 统一心智模型：发送消息 → 看到回复 → 做决策
- 模式差异体现在暗流信息（抽屉），而非交互方式变更
- 降低用户学习成本

### ADR-003: Harness 横切 vs 各引擎分散实现

**决策**：Harness 作为横切拦截器，通过 4 个钩子注入三引擎。

**理由**：
- 三引擎有 80% 重复逻辑（上下文注入、Token 管控、文件提取、审计）
- 分散实现需同步 3 个文件
- 引擎专注编排逻辑，Harness 专注保障逻辑
- 通过 `ExecutionContext` 字段差异适配不同引擎需求

### ADR-004: HITL 输入框永不禁用

**决策**：HITL 卡片提供快捷入口，但输入框始终可用。

**理由**：
- LLM 输出的选项可能不完整（遗漏"我有其他想法"）
- 用户应有最终表达权，不被预设选项限制
- 降级路径一致：卡片不渲染时，输入框仍可交互
- 行为机统一：Enter 始终是"发送"

### ADR-005: CollabState 单一状态树 vs 分布式状态

**决策**：使用 LangGraph StateGraph 的单一 `CollabState` 管理全流程状态。

**理由**：
- LangGraph 内置 checkpoint 机制，支持暂停/恢复
- 状态变更可追踪、可回滚
- 条件路由天然支持状态驱动的分支决策
- 避免分布式状态的一致性问题

### ADR-006: WebSocket 单连接 vs 多连接

**决策**：前端与后端维持**单一** WebSocket 连接处理所有事件。

**理由**：
- 避免多连接的时序问题（同一个 Agent 的消息可能从不同连接乱序到达）
- 简化重连逻辑（一个连接断开后统一恢复）
- 减少服务端连接数

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| Harness | Agent 执行横切拦截器，提供 before/after/verify/cleanup 4 个钩子 |
| HITL | Human-In-The-Loop，人机协作断点 |
| CollabState | LangGraph 状态图中流转的全局状态 TypedDict |
| CollabMode | 协作模式：swarm / supervisor / langgraph |
| Context Pipeline (M5) | 为单次 Agent 执行构建 WorkerContext 的上下文组装器 |
| PeerMailbox (M8) | Agent 间对等通信消息系统 |
| Loop Engine | 三分类错误恢复引擎 |
| Observer | 异步事件总线 + DB 持久化 |
| Workspace | 按 Session 隔离的文件工作空间 |
| drift_detected | M7 验证发现的"需求理解偏差"标记 |
| Route A / Route B | M6 执行的两种模式：DAG 并行（A）/ 层级委派（B） |
| ADR | Architecture Decision Record，架构决策记录 |

### B. 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 编排 | LangGraph StateGraph | checkpoint、条件路由、状态持久化 |
| LLM | LiteLLM | 20+ Provider 统一适配 |
| 后端 | FastAPI + WebSocket | 异步原生支持 |
| 数据库 | PostgreSQL 16 (asyncpg) | JSONB、UUID、TIMESTAMPTZ |
| 缓存 | Redis 7 | 会话状态、Blackboard、限流 |
| 前端 | React 18 + TypeScript | useReducer 状态管理 |
| 构建 | Vite | HMR + Proxy |
| 安全 | Fernet 加密 | API Key 加密存储 |

### C. 核心表结构速查

| 表 | 关键字段 |
|----|---------|
| teams | id, name, collaboration_mode, workflow_id |
| team_members | id, team_id, agent_id, role_name, capabilities |
| team_supervisor_configs | id, team_id, leader_member_id |
| team_supervisor_relations | id, team_id, member_id, supervisor_member_id |
| team_langgraph_configs | id, team_id, workflow_id |
| agents | id, name, persona_id, model_id |
| workflows | id, name, status |
| workflow_nodes | id, workflow_id, type, label, config(JSONB), node_key |
| workflow_edges | id, workflow_id, source_id, target_id, type |
| sessions | id, team_id, title, workspace_path |
| memories | id, session_id, level, content, metadata_(JSONB) |

---

*文档基于 v5.0 代码生成，最后更新: 2026-06-25*

---

## 第 3 章：五层技术架构

> 对应架构图：`02-五层技术架构.html`

### 3.1 架构全景

```
┌─────────────────────────────────────────────────────────────┐
│                    L1 交互层 (Frontend)                     │
│  ChatRoomView · ChatStream · DrawerHost · HITLCard · Input  │
├─────────────────────────────────────────────────────────────┤
│                    L2 通信层 (WebSocket + REST)             │
│  单连接多路复用 · 10+消息类型 · Vite Proxy · Stream Token   │
├──────┬──────────────┬──────────────┬────────────────────────┤
│Swarm │ Supervisor   │  LangGraph   │  ← L3 编排层 (Workflow)│
├──────┴──────────────┴──────────────┴────────────────────────┤
│                    L4 能力层 (Identity + Agent + Knowledge)  │
│  AgentFactory · Memory L1-L4 · ContextPipeline · RAG        │
│  ModelAdapter · FallbackChain · WorkspaceMgr · AgentPool    │
├─────────────────────────────────────────────────────────────┤
│                    L5 数据层 (Data)                         │
│     PostgreSQL 16 (主存储) · Redis 7 (缓存/消息)            │
├─────────────────────────────────────────────────────────────┤
│              Harness 横切保障层 (Cross-Cutting)              │
│  before_execution → after_execution → verify → cleanup      │
│  Loop Engine · Observer · Security Filter                   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 交互层

ChatRoomView 是所有协作模式的唯一入口，内部通过 `useChatRoomState` reducer 管理全局状态。暗流信息架构将表面对话流（ChatStream）与详细信息（抽屉）分离，保持界面简洁。

### 3.3 通信层

前端与后端维持**单一 WebSocket 连接**，通过 `data.type` 字段区分 10+ 种消息类型实现多路复用。三模式共享同一连接，避免多连接时序问题。

| 方向 | 消息类型 |
|------|---------|
| S→C | agent_message · stream_token · hitl_notification · task_status · task_dag · files_changed · reasoning_complete · thinking_update · message_complete · error |
| C→S | chat · hitl_resume · interrupt |

流式渲染链路：`agent_chat_stream → async for token → send_fn(stream_token) → 前端创建流式占位消息 → 逐 token 追加 → agent_message 替换`

### 3.4 模块依赖规则

```
api/v1 → services → models
                  ↘       ↗
                adapters / core
```

- `api/` 只做参数校验 + 调用 service
- `services/` 是业务核心，依赖 models 和 adapters
- `models/` 纯数据定义，不依赖 services
- Infrastructure 域可被任意层依赖
- 跨域只通过 UUID 引用，禁止直接导入 ORM 模型

---

## 第 4 章：三模式协作引擎

> 对应架构图：`03-Supervisor决策流程.html`

### 4.1 Swarm Engine（群聊模式）

**定位**：多 Agent 自由讨论，流程从讨论中涌现。

**三阶段流水线**：
1. RoundTable 讨论 — 轮询 Agent 发言，最多 3 轮
2. Agent Execution — 注入 Harness 执行
3. Completion / HITL — 完成或触发人工介入

**HITL 三级检测**：L1 显式标记(conf=1.0) → L2 结构化选项(conf=0.9) → L3 六特征评分(≥3触发)。特征权重：OPTION_LIST×2 + QUESTION×1 + USER_DIRECT×1 + LAST_SPEAKER×1 + NO_RECENT×1 + EXCLUDED×(-1)

### 4.2 Supervisor Engine（主管模式）

**定位**：结构化多 Agent 协作，M0-M7 固定管道，支持组织层级委派。

**M0-M7 管道**：基于 LangGraph StateGraph<CollabState>，注册 9 个节点和条件边。

**组织层级**：DB 读取 team_supervisor_configs + relations → load_org_structure → CollabState.org_structure → m6_delegate 按层级委派 → m6_collect 按层级汇总 → m6_escalate 沿树升级。

**M7 验证路由**（v5 核心增强）：
| 结果 | 路由 | 理由 |
|------|------|------|
| passed | HITL 确认 | 产物匹配需求 |
| major | 回 M6 重做 | 代码 Bug/功能缺失 |
| drift | 回 M1 重分析 | 需求理解方向性偏差 |
| critical | HITL 升级 | 严重偏离，无法自动修复 |

### 4.3 LangGraph Engine（工作流模式）

**定位**：用户自定义 DAG 编排，声明式流程定义。

**执行流程**：加载 workflow + node_bindings → 拓扑排序(Kahn) → 分层(同层无依赖) → asyncio.gather 并行。

**7 种节点类型**：Start / Agent / Condition / Router / Validation / HITL / End。每层执行循环中按类型分别处理。

### 4.4 三模式对比

| 维度 | Swarm | Supervisor | LangGraph |
|------|-------|------------|-----------|
| 流程确定性 | 涌现（低） | 固定管道（高） | 声明式（中-高） |
| HITL 触发 | 三级检测（自动） | M2/M3/M6/M7（固定点） | HITL 节点 + Validation escalate |
| 并行能力 | 单轮并行发言 | M6 按 DAG 层级并行 | 同层节点 asyncio.gather |
| 组织层级 | 不适用 | DB 配置 + LCA 审核 | 不适用 |

---

## 第 5 章：Agent 生命周期与 Harness 接入

> 对应架构图：`04-Agent生命周期与Harness.html`

### 5.1 Agent 执行 6 阶段

```
① 引擎触发 → ② Harness.before → ③ LLM 调用 → ④ Harness.after → ⑤ 引擎后处理 → ⑥ Observer 事件
```

**三引擎注入点差异**：

| 引擎 | 注入位置 | 传入字段 |
|------|---------|---------|
| Swarm | Phase2 _agent_execute | instruction + user_message |
| Supervisor | m6_execute_worker | + artifacts + peer_msgs + org_role_context + retry_feedback |
| LangGraph | _execute_agent_node | + artifacts + depends_on + code_output_required + workspace_path |

### 5.2 Harness 4 钩子

| 钩子 | 时机 | 核心职责 |
|------|------|---------|
| before_execution | Agent 执行前 | _build_prompt(M5+M8) → _inject_context(Memory+RAG) → _check_token |
| after_execution | Agent 执行后 | _extract_files → _record_tokens → _persist+retry → _audit_log |
| verify | M7 阶段 | 选非生产者 Agent 盲审（只给需求+产物） |
| cleanup | 会话结束 | 清 Token 计数器 + 暂停状态 + 资源回收 |

### 5.3 Context 组装链路

Harness._build_prompt() 调用 M5 ContextPipeline + M8 PeerMailbox 构建完整 prompt。Token 裁剪优先级：System Prompt > 当前任务 > 前置产物(≤3K) > PeerMsg(≤5条) > Memory > 历史(≤5轮)。

### 5.4 Workspace 隔离

路径模型：{WORKSPACE_BASE}/{session_id}/。文件提取通过正则解析代码块写入，安全校验通过 startswith 防越权，前端 ArtifactsDrawer 按 Agent 分组展示。

---

## 第 6 章：异常处理与安全

> 对应架构图：`05-LoopEngine与异常处理.html`

### 6.1 Loop Engine 三分类

| 类型 | 检测 | 策略 | 限制 |
|------|------|------|------|
| TRANSIENT | timeout/429/503 | 自动重试·指数退避 1s→2s→4s | ≤3次 |
| CONTENT | json_error/empty/verify_fail | 四步恢复 Rollback→Feedback→Inject→Retry | ≤3次·同错×2提前升级 |
| FATAL | api_key/permission/config | 立即 HITL·不重试 | 人工修复 |

### 6.2 幻觉对抗：M7 drift 纠正

M7 验证采用盲审——只给需求+产物，不给 Worker 思考链，防止确认偏差。检测到 drift（需求理解偏差）时，回到 M1 用验证反馈重新分析，而非仅仅重做 M6。

```
drift_detected → 清除 task_dag + artifacts → M1 重分析 → M2 重澄清 → M4 重分解 → M6 重执行 → M7 重验证
```

### 6.3 安全过滤

**Prompt Injection**：8 种正则检测（ignore previous / system prompt / DAN / jailbreak 等），命中即拒绝。

**PII 脱敏**：手机号、身份证、API Key、密码、邮箱 5 种正则，命中替换为 [REDACTED]。

过滤时机：消息进入引擎前（ws.py 中 save_and_send 之前）。

---

## 第 7 章：通信与数据流

> 对应架构图：`06-通信与数据流.html`

### 7.1 WebSocket 单连接多路复用

前端与后端的唯一连接，通过 `data.type` 区分消息类型。Vite Proxy 将开发环境的 `/ws/*` 转发到后端。useWsEvents 维护心跳和自动重连。

### 7.2 Observer 事件系统

15 种 EventType 覆盖 Agent 执行全生命周期。EventBus 异步非阻塞发射（asyncio.create_task），异常不传播到调用方。独立 DB session 持久化，JSONB payload。

### 7.3 前端状态管理

纯函数 chatRoomReducer：(state, action) → state。Action 分三类：WS_*（WebSocket 入站）、UI_*（用户交互）、CTRL_*（内部控制）。ChatRoomState 包含 messages·workPlan·artifacts·thinkingAgents·pendingHitl·openDrawers 等全部状态。

### 7.4 数据持久化

| 存储 | 用途 |
|------|------|
| PostgreSQL 16 | 主存储：Team·Agent·Session·Memory·Workflow |
| Redis 7 | 缓存：会话状态·Blackboard Pub/Sub·限流计数器 |
| Memory L1-L4 | 四层记忆：LLM窗口→会话→团队→项目 |
| Workspace | 文件隔离：{BASE}/{session_id}/·Snapshot 快照 |

---

## 第 8 章：关键设计决策

### ADR-001：三引擎独立 vs 统一引擎

**决策**：保持三个独立引擎，共享能力层。

**理由**：Swarm 流程涌现、Supervisor 固定管道、LangGraph 声明式 DAG，三者核心约束不同。统一引擎要么限制灵活性，要么稀释结构化。共享能力层（Harness/Memory/LLM Adapter）实现复用。

### ADR-002：聊天室为唯一入口

**决策**：无论后台运行哪种引擎，用户始终面对同一个聊天界面。

**理由**：统一心智模型"发送消息→看到回复→做决策"。模式差异体现在暗流信息（抽屉），而非交互方式变更。

### ADR-003：Harness 横切 vs 分散实现

**决策**：Harness 作为横切拦截器，通过 4 个钩子注入三引擎。

**理由**：三引擎有 80% 重复逻辑（上下文注入、Token 管控、文件提取、审计）。分散实现需同步 3 个文件。通过 ExecutionContext 字段差异适配不同引擎需求。

### ADR-004：HITL 输入框永不禁用

**决策**：选项卡片提供快捷入口，但输入框始终可用。

**理由**：LLM 输出的选项可能不完整（遗漏"我有其他想法"）。用户应有最终表达权。输入框作为降级路径，确保任何状态下用户都能交互。

### ADR-005：CollabState 单一状态树

**决策**：使用 LangGraph StateGraph 的单一 CollabState 管理全流程状态。

**理由**：内置 checkpoint 支持暂停/恢复。状态变更可追踪、可回滚。条件路由天然支持状态驱动的分支决策。

### ADR-006：WebSocket 单连接 vs 多连接

**决策**：维持单一 WebSocket 连接处理所有事件。

**理由**：避免多连接时序问题。简化重连逻辑。减少服务端连接数。

---

*文档对应 8 张架构图（`docs/架构图-v5-wip/`），基于 v5.0 代码生成，最后更新：2026-07-01*

| 编号 | 架构图 | 文件 |
|------|--------|------|
| 01 | DDD 领域全景 | `01-DDD领域全景.html` |
| 02 | 五层技术架构 | `02-五层技术架构.html` |
| 03 | Supervisor 决策流程 | `03-Supervisor决策流程.html` |
| 04 | Agent 生命周期与 Harness | `04-Agent生命周期与Harness.html` |
| 05 | Loop Engine 与异常处理 | `05-LoopEngine与异常处理.html` |
| 06 | 通信与数据流 | `06-通信与数据流.html` |
| 07 | **Agent 执行模式** | `07-Agent执行模式.html` |
| 08 | **可观测性全链路** | `08-可观测性全链路.html` |

---

## 第 9 章：非功能性需求 (NFRs)

### 9.1 性能指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| API 响应时间 (P50) | < 200ms | 配置类 CRUD 接口 |
| API 响应时间 (P99) | < 2s | 含 LLM 调用的编排接口 |
| WebSocket 消息延迟 | < 100ms | stream_token 从后端到前端的延迟 |
| Agent 单次执行 | < 120s | DeepSeek 超时阈值（大模型推理），其余 60s |
| 数据库连接池 | 20 连接 | asyncpg 默认，可扩展至 50 |

### 9.2 可伸缩性

| 指标 | 设计目标 |
|------|---------|
| 并发 WebSocket 连接 | 支持 100 个活跃会话 |
| 并行 Agent 执行 | Team 配置 max_parallel_agents=3，三引擎共用 asyncio.gather |
| Agent 注册数 | 无硬限制，Agent Pool 基于能力匹配 |
| Session 隔离 | 每个 Session 独立 Workspace 目录 + 独立 CollabState |

### 9.3 可用性

| 指标 | 目标 |
|------|------|
| 系统年可用率 | 99.5%（单节点部署） |
| RTO（恢复时间目标） | < 30 分钟（docker-compose 重启） |
| RPO（恢复点目标） | < 5 分钟（数据库持久化间隔） |

**容灾策略**：
- PostgreSQL：docker-compose volumes 持久化，定期 pg_dump 备份
- Redis：volumes 持久化 RDB + AOF（生产环境配置）
- 无状态应用：FastAPI + React 可水平扩展（多个后端实例通过 Nginx 负载均衡）

### 9.4 安全基线

| 维度 | 措施 |
|------|------|
| 传输加密 | HTTPS（生产环境 Nginx 反向代理 + Let's Encrypt） |
| 存储加密 | API Key Fernet 对称加密存储 |
| 认证 | API Key Middleware 验证请求头 / WebSocket token 验证 |
| 注入防护 | Prompt Injection 8 种正则检测 + PII 脱敏 |
| 速率限制 | 滑动窗口 120 RPM（可配置） |
| 工作空间隔离 | 按 Session 隔离 + 路径越权检测 |

---

## 第 10 章：部署与基础设施

### 10.1 部署拓扑

```
                    ┌──────────────┐
                    │   Nginx 80   │  ← HTTPS 终止 / 反向代理
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │FastAPI:1 │ │FastAPI:2 │ │  Vite    │  ← 开发模式
        │  :8000   │ │  :8001   │ │  :5173   │
        └────┬─────┘ └────┬─────┘ └──────────┘
             │            │
        ┌────┴────────────┴────┐
        ▼                      ▼
  ┌──────────┐          ┌──────────┐
  │PostgreSQL│          │ Redis 7  │
  │16 (pgvector)        │:6379     │
  │:5432     │          │ 缓存/消息 │
  │ 主存储   │          └──────────┘
  └──────────┘
```

### 10.2 容器化方案

**docker-compose.yml** 定义三服务架构：

| 服务 | 镜像 | 端口 | 关键配置 |
|------|------|------|---------|
| postgres | pgvector/pgvector:pg16 | 5432 | healthcheck: pg_isready · 持久化 volume |
| redis | redis:7-alpine | 6379 | healthcheck: redis-cli ping · 持久化 volume |
| backend | python:3.12-slim (自建) | 8000 | depends_on postgres+redis · env_file · --reload 热重载 |

**基础镜像选择**：python:3.12-slim（轻量），构建依赖仅 build-essential。

**开发环境启动**：`docker compose up -d` → postgres + redis 启动 → backend 等待两者 healthy 后启动。

### 10.3 CI/CD 建议流程

```
代码提交 (main 分支)
  → 1. 静态检查 (ruff / mypy)
  → 2. 单元测试 (pytest)
  → 3. 集成测试 (pytest + test DB)
  → 4. 构建 Docker 镜像 (docker build)
  → 5. 推送到镜像仓库
  → 6. 部署到目标环境 (docker compose pull + up -d)
```

### 10.4 配置管理

基于 pydantic-settings 的 `Settings` 类，所有配置通过环境变量注入：

| 类别 | 变量 | 默认值 |
|------|------|--------|
| 数据库 | DATABASE_URL | postgresql+asyncpg://... |
| 缓存 | REDIS_URL | redis://localhost:6379/0 |
| LLM | OPENAI/CLAUDE/GEMINI/DEEPSEEK_API_KEY | "" |
| 加密 | ENCRYPTION_KEY | ""（开发模式可选） |
| 工作空间 | WORKSPACE_BASE_PATH | ~/the-boy-workspaces |
| 应用 | APP_HOST / APP_PORT / LOG_LEVEL | 0.0.0.0 / 8000 / INFO |
| 认证 | API_KEY | ""（空=开发模式跳过认证） |
| 限流 | RATE_LIMIT_RPM | 120 |

**环境区分**：开发（docker-compose + --reload）、测试（CI 环境变量注入）、生产（K8s ConfigMap / Secrets）。

---

## 第 11 章：可观测性（LangFuse 全链路追踪）

> 详细设计文档：`docs/monitoring-observability-module.md`

### 11.1 架构概览

基于 LangFuse v3.202.1 自部署，Python SDK v4.12 + OpenTelemetry OTLP 上报。三层元数据结构：**Trace**（会话/消息）→ **Span**（Agent 执行）→ **Generation**（LLM 调用）。

```
Backend: create_trace → span → generation
              │           │         │
              ▼           ▼         ▼
         OTLP HTTP → LangFuse Web :3000 → Redis Queue → Worker → ClickHouse
                                              │
                                         MinIO :9003 (事件存储)
```

### 11.2 Trace 结构

一次用户消息 → 一条 Trace。Swarm 模式下同一条 trace 包含所有参与 Agent 的 span。

```
Trace: [swarm] 产品开发团队 | 帮我设计一个用户认证系统
  ├── [chain_of_thought] 架构师-Agent (architect)
  │   └── chat:deepseek-v4-pro        ← LLM 调用 (tokens/latency)
  ├── [rewoo] 部署运维-Agent (devops)
  │   ├── [rewoo] Phase 1: Plan
  │   ├── [rewoo] Phase 2: Execute
  │   └── [rewoo] Phase 3: Merge
  ├── [react] 后端工程师-Agent (backend_dev)
  │   ├── [react] Iteration 1
  │   └── [react] Iteration 2
  └── ...
```

Sessions 页面按 `session_id` 分组，一次完整多轮对话的所有 trace 自动聚合。

### 11.3 元数据规范

| 层 | 名称格式 | 元数据字段 |
|----|---------|-----------|
| Trace | `[{mode}] {team_name} \| {message[:60]}` | team_name, team_id, session_id, mode, user_message |
| Span | `[{exec_mode}] {agent_name} ({role})` | agent_name, agent_role, exec_mode, node_key, provider, iteration |
| Phase | `[{mode}] Phase {i}: {name}` | phase_name, phase_index, total_phases |
| Generation | `chat:{model}` | provider, model, agent, exec_mode, latency_s |

### 11.4 Scores 评分

| Score | 来源 | 触发时机 | 值域 |
|-------|------|---------|------|
| `clarity_score` | M1 analyzer | need_clarify / need_confirm | 0.0-1.0 |
| `review_score` | M7 verifier | 验证通过=1.0, 需重做=0.3 | 0.0-1.0 |

在 Dashboard 中按时间聚合，追踪需求清晰度和产出质量趋势。

### 11.5 告警通道

`alert_webhook.py` — Slack / Discord / Custom Webhook 三通道，7 种告警类型，5 级过滤。安全过滤器检测到 prompt injection 时自动触发 security 告警。

### 11.6 部署

`docker-compose.langfuse.yml`：ClickHouse + LangFuse Web + LangFuse Worker + MinIO (宿主机)。复用项目 PostgreSQL + Redis。详见 `docs/monitoring-observability-module.md`。

### 11.7 关键指标

| 指标 | 来源 |
|------|------|
| Agent 执行次数 / Token 消耗 / 延迟分布 | LangFuse Dashboard 自动聚合 |
| Session 活跃度 / 对话轮次 | Sessions 视图 |
| 需求清晰度趋势 / 验证通过率 | Scores 时间序列 |
| Agent 执行模式分布 | Span metadata 筛选 |

---

## 第 12 章：API 规约

### 12.1 REST API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/sessions | 会话列表（支持 team_id/status 过滤） |
| POST | /api/v1/sessions | 创建会话 |
| GET | /api/v1/sessions/{id} | 会话详情（含团队名称） |
| PUT | /api/v1/sessions/{id} | 更新会话（标题/状态/工作空间路径） |
| DELETE | /api/v1/sessions/{id} | 归档会话 |
| GET | /api/v1/sessions/{id}/messages | 历史消息（从 Memory L2 查询） |
| GET | /api/v1/sessions/{id}/workspace | 工作空间信息（路径/文件数/大小） |
| GET | /api/v1/sessions/{id}/workspace/files | 文件列表（支持 recursive） |
| GET | /api/v1/sessions/{id}/tasks | 会话任务列表 |
| GET | /api/v1/teams | 团队列表 |
| POST | /api/v1/teams | 创建团队（含 collaboration_mode） |
| GET | /api/v1/teams/{id} | 团队详情（含成员列表） |
| PUT | /api/v1/teams/{id} | 更新团队配置 |
| DELETE | /api/v1/teams/{id} | 删除团队 |
| POST | /api/v1/teams/{id}/members | 添加团队成员 |
| GET | /api/v1/workflows | 工作流列表 |
| POST | /api/v1/workflows | 创建工作流 |
| GET | /api/v1/workflows/{id} | 工作流详情（含节点和边） |
| PUT | /api/v1/workflows/{id} | 更新工作流 |

### 12.2 API 认证

| 方式 | 场景 |
|------|------|
| API Key | REST API：请求头 `x-api-key: your_key` |
| WebSocket Token | WS 连接：URL 参数 `?token=your_key` |
| 开发模式 | API_KEY 为空时跳过认证 |

认证通过 `ApiKeyMiddleware`（REST）和 `verify_ws_auth()`（WebSocket）实现。

### 12.3 WebSocket 消息格式

```json
{
  "type": "agent_message | stream_token | hitl_notification | task_status | ...",
  "source": "swarm | supervisor | langgraph | harness",
  "timestamp": "2026-06-26T12:00:00+00:00",
  "payload": { ... }
}
```

### 12.4 API 版本管理

- URL 路径版本：`/api/v1/...`
- 当前版本：v1
- 破坏性变更时升级至 `/api/v2/...`，v1 保持向后兼容至少 2 个版本周期

---

## 第 13 章：数据管理

### 13.1 数据库迁移 (Alembic)

使用 Alembic 管理 PostgreSQL schema 变更：

```
alembic/               # 迁移目录
├── versions/          # 迁移脚本（每次变更一个文件）
├── env.py             # 迁移环境配置
└── script.py.mako     # 迁移脚本模板
```

**工作流**：修改 ORM 模型 → `alembic revision --autogenerate` → 检查生成的迁移脚本 → `alembic upgrade head`。

**原则**：每次迁移必须可逆（含 downgrade 逻辑），生产环境迁移前在 staging 验证。

### 13.2 数据备份与恢复

**PostgreSQL**：

| 策略 | 频率 | 工具 |
|------|------|------|
| 全量备份 | 每日 | pg_dump |
| WAL 归档 | 持续 | archive_command |
| 保留周期 | 30 天 | 自动清理 |

**Redis**：

| 策略 | 频率 | 配置 |
|------|------|------|
| RDB 快照 | 每 15 分钟（1 个 key 变更） | save 900 1 |
| AOF 日志 | 每秒 fsync | appendfsync everysec |

**Workspace 文件**：按 Session 存储于 `{WORKSPACE_BASE}/{session_id}/`，随 Session 归档一同清理。

**恢复流程**：
1. 停止应用
2. 恢复 PostgreSQL（pg_restore）+ Redis（RDB/AOF）
3. 验证数据完整性
4. 重启应用

### 13.3 数据保留策略

| 数据类型 | 保留周期 | 清理策略 |
|---------|---------|---------|
| L2 会话记忆 | 会话结束后 7 天 | 定时任务归档 |
| L3 团队记忆 | 30 天未访问 → 归档 | 按 last_accessed 判断 |
| L4 项目记忆 | 永久 | 手动管理 |
| Observer 事件 | 90 天 | 按 created_at 分区清理 |
| Workspace 文件 | 随 Session | Session 删除时清理 |

---

*文档基于 v5.0 代码生成，最后更新：2026-07-01*

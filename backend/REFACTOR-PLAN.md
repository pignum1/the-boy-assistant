# DDD 领域重构总计划

## 当前问题诊断

### 问题 1: services/ 目录职责混乱
- `sop_engine.py` (458行) 混合了状态机引擎 + 节点执行 + 路由逻辑 + HITL 管控
- `agent_factory.py` (322行) 同时负责 CRUD + Prompt 组装 + LLM 调用 + 工具执行
- `condition_router.py` (218行) 混合了条件评估 + 循环控制（两个独立关注点）

### 问题 2: 领域边界模糊
- `agent_pool.py` 是运行时资源管理，却放在 services/ 根目录
- `fallback_chain.py` 是模型层降级策略，却依赖 `agent_factory.resolve_api_key`
- `prompt_builder.py` 和 `context_manager.py` 是 Agent 域的内部关注点，暴露为顶层服务

### 问题 3: 测试困难
- SOP Engine 的节点执行、路由、HITL 全耦合在一个类中，无法独立测试
- agent_factory 的 `agent_chat` 函数混合了太多职责
- 集成测试和单元测试边界不清

---

## 重构目标

按 CLAUDE.md 定义的 5 个限界上下文重新组织代码，确保：
1. 每个领域模块职责单一、边界清晰
2. 领域间通过明确接口交互，无循环依赖
3. 可独立测试每个子模块

---

## 领域映射表

### 领域 1: Identity（身份域）

| 当前文件 | 问题 | 重构动作 |
|---------|------|---------|
| `services/persona_service.py` | 模块函数风格，OK | 重构为 `PersonaService` 类，保持统一 |
| `services/model_router.py` | 混合 CRUD + 复杂度路由 + seed | 拆分：CRUD 保留，路由策略独立 |
| `services/tool_registry.py` | 模块函数风格，OK | 重构为 `ToolRegistry` 类 |
| `core/security.py` | OK | 不变 |
| `api/v1/keys.py` | OK | 不变 |

### 领域 2: Agent（智能域）

| 当前文件 | 问题 | 重构动作 |
|---------|------|---------|
| `services/agent_factory.py` (322行) | CRUD + chat + key 解析全耦合 | **拆分为 3 个文件** |
| `services/memory_manager.py` (239行) | OK 但过长 | 内部优化，不拆分 |
| `services/skill_registry.py` (137行) | OK | 不变 |
| `services/skill_executor.py` (276行) | OK 但依赖 skill_registry 解析函数 | 内部优化 |
| `services/context_manager.py` (175行) | OK | 不变 |
| `services/prompt_builder.py` (108行) | OK | 不变 |
| `services/fallback_chain.py` (183行) | 跨域依赖 agent_factory | 移除跨域依赖 |
| `services/agent_pool.py` (95行) | OK | 不变 |

### 领域 3: Knowledge（知识域）

| 当前文件 | 问题 | 重构动作 |
|---------|------|---------|
| `services/rag/knowledge_service.py` (154行) | OK | 不变 |
| `services/rag/chunker.py` (123行) | OK | 不变 |
| `services/rag/embedder.py` (107行) | OK | 不变 |
| `services/rag/hybrid_search.py` (210行) | 偏长 | 内部优化 |
| `services/rag/reranker.py` (105行) | OK | 不变 |

### 领域 4: Workflow（编排域）

| 当前文件 | 问题 | 重构动作 |
|---------|------|---------|
| `services/sop_engine.py` (458行) | **严重耦合**：引擎 + 节点执行 + 路由 + HITL | **拆分为 4 个文件** |
| `services/sop_service.py` (214行) | 混合 CRUD + YAML 导入/导出 + preset 模板 | 拆分 preset 模板 |
| `services/team_manager.py` (179行) | OK | 不变 |
| `services/condition_router.py` (218行) | 条件路由 + 循环控制混合 | **拆分为 2 个文件** |

### 领域 5: Infrastructure（基础设施域）

| 当前文件 | 问题 | 重构动作 |
|---------|------|---------|
| `adapters/llm/base.py` | OK | 不变 |
| `adapters/llm/litellm_adapter.py` | OK | 不变 |
| `adapters/llm/mock_adapter.py` | OK | 不变 |
| `adapters/llm/rate_limiter.py` | OK | 不变 |
| `tools/` | OK | 不变 |
| `core/config.py` | OK | 不变 |
| `core/database.py` | OK | 不变 |

---

## 重构步骤

### Phase 1: Workflow 域拆分（最高优先级，问题最严重）

#### Step 1.1: 拆分 sop_engine.py → 4 个文件

**目标结构：**
```
services/
├── sop_engine.py          # 精简为引擎框架（~150行）：循环控制 + 状态持久化
├── sop_node_executor.py   # 节点执行器（~200行）：agent/hitl/validation/start/end
├── sop_router.py          # 路由决策（~100行）：边映射 + 条件评估 + 下一跳
└── sop_state.py           # TaskState 数据类（~80行）：状态序列化
```

**拆分细则：**

| 新文件 | 从 sop_engine.py 提取 | 职责 |
|-------|---------------------|------|
| `sop_state.py` | `TaskState` 类 + `to_dict`/`from_dict` | 纯数据类，无依赖 |
| `sop_router.py` | `_build_edge_map`, `_route_next`, `_resolve_state_field` + 依赖 `ConditionRouter` | 路由决策 |
| `sop_node_executor.py` | `_execute_agent_node`, `_execute_hitl_node`, `_execute_validation_node` | 节点执行 |
| `sop_engine.py` | `SOPEngine` 类（`start_task`, `run_until_paused`, `resume_task`） | 编排框架 |

**依赖方向：**
```
sop_engine → sop_node_executor → agent_factory
           → sop_router → condition_router
           → sop_state
```

#### Step 1.2: 拆分 condition_router.py → 2 个文件

```
services/
├── condition_router.py    # 保留：条件表达式评估（~100行）
└── loop_controller.py     # 新建：循环退避控制（~80行）
```

#### Step 1.3: 优化 sop_service.py

- 将 preset YAML 模板常量和 `seed_preset_sops()` 移到独立的 `sop_presets.py`
- `sop_service.py` 专注 CRUD + 导入/导出

### Phase 2: Agent 域拆分

#### Step 2.1: 拆分 agent_factory.py → 3 个文件

**目标结构：**
```
services/
├── agent_service.py       # Agent CRUD（~100行）：create/update/delete/list/get
├── agent_chat.py          # Agent 对话（~150行）：chat + prompt 组装 + 上下文注入
└── agent_factory.py       # 保留但精简：Agent 组装 + key 解析（~80行）
```

**拆分细则：**

| 新文件 | 从 agent_factory.py 提取 | 职责 |
|-------|------------------------|------|
| `agent_service.py` | `create_agent`, `update_agent`, `delete_agent`, `list_agents`, `get_agent` | 纯 CRUD |
| `agent_chat.py` | `agent_chat` 函数 | 对话执行：prompt 组装 → LLM 调用 → 工具执行 |
| `agent_factory.py` | `resolve_api_key`, agent 组装逻辑 | Agent 实例化 |

#### Step 2.2: 解除 fallback_chain 的跨域依赖

- `fallback_chain.py` 当前 import `agent_factory.resolve_api_key`
- 将 `resolve_api_key` 移到 `core/security.py` 或 `adapters/llm/` 层
- `fallback_chain.py` 只依赖 Infrastructure 层

### Phase 3: Identity 域统一风格

#### Step 3.1: persona_service.py 函数 → 类

```python
class PersonaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: PersonaCreate) -> Persona: ...
    async def get(self, persona_id: uuid.UUID) -> Optional[Persona]: ...
    # ...
```

#### Step 3.2: tool_registry.py 函数 → 类

```python
class ToolRegistry:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: ToolCreate) -> Tool: ...
    async def get(self, tool_id: uuid.UUID) -> Optional[Tool]: ...
    # ...
```

#### Step 3.3: model_router.py 职责分离

- CRUD 部分保留在 `model_router.py`
- 复杂度路由策略（`classify_complexity`, `select_model`）可以保留在同文件
- 但需确保不直接依赖 Agent 域

### Phase 4: API 层适配

API 层改动最小，主要是更新 import 路径：

| API 文件 | 变更 |
|---------|------|
| `api/v1/agents.py` | 从 `agent_factory` 改为调用 `agent_service` + `agent_chat` |
| `api/v1/tasks.py` | import `SOPEngine`（不变），内部已委托 |
| 其他 API | 无变化 |

### Phase 5: 测试重组

每个领域一个测试文件，单元测试和集成测试分离：

```
tests/
├── test_identity.py       # Persona + Model + Tool 服务测试
├── test_agent.py          # Agent 域测试（Service + Chat + Factory）
├── test_knowledge.py      # Knowledge 域测试
├── test_workflow.py       # Workflow 域测试
│   ├── 单元: TaskState, SOPRouter, SOPNodeExecutor, ConditionRouter, LoopController
│   ├── 集成: SOPEngine 端到端
│   └── API: /tasks 端点
├── test_infrastructure.py # LLM Adapter + Security 测试
└── conftest.py            # 共享 fixtures（NullPool DB, 测试数据工厂）
```

---

## 重构后的完整文件清单

### services/ 目录（按领域分组）

```
services/
├── # ── Identity 域 ─────────────────
├── persona_service.py     # PersonaService 类（CRUD + seed）
├── model_router.py        # ModelRouter 类（CRUD + 复杂度路由 + seed）
├── tool_registry.py       # ToolRegistry 类（CRUD + seed）
│
├── # ── Agent 域 ────────────────────
├── agent_service.py       # AgentService 类（CRUD）
├── agent_chat.py          # agent_chat() 函数（对话执行）
├── agent_factory.py       # Agent 组装 + resolve_api_key
├── agent_pool.py          # AgentPool（运行时资源池）
├── memory_manager.py      # MemoryManager（四层记忆）
├── skill_registry.py      # Skill 解析 + 管理
├── skill_executor.py      # Skill 执行器
├── context_manager.py     # 上下文窗口管理
├── prompt_builder.py      # Prompt 组装器
├── fallback_chain.py      # 模型降级链（移除跨域依赖）
│
├── # ── Knowledge 域 ────────────────
├── rag/
│   ├── knowledge_service.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── hybrid_search.py
│   └── reranker.py
│
├── # ── Workflow 域 ─────────────────
├── sop_engine.py          # SOPEngine（精简后 ~150行）
├── sop_state.py           # TaskState 数据类
├── sop_node_executor.py   # SOPNodeExecutor
├── sop_router.py          # SOPRouter
├── sop_service.py         # SOPService（CRUD + 导入/导出）
├── sop_presets.py         # 预置 SOP 模板 + seed
├── team_manager.py        # TeamManager
├── condition_router.py    # ConditionRouter（纯条件评估）
└── loop_controller.py     # LoopController（循环退避）
```

---

## 执行优先级

| 顺序 | Phase | 预计改动量 | 风险 | 原因 |
|------|-------|----------|------|------|
| 1 | Phase 1.1 | 大（拆 458→4 文件） | 中 | 问题最严重，先解决核心引擎 |
| 2 | Phase 1.2 | 小 | 低 | 简单拆分 |
| 3 | Phase 1.3 | 小 | 低 | 模板常量移出 |
| 4 | Phase 2.1 | 大（拆 322→3 文件） | 中 | Agent 域核心拆分 |
| 5 | Phase 2.2 | 小 | 低 | 解除循环依赖 |
| 6 | Phase 3 | 中（3 文件重构） | 低 | 风格统一，逻辑不变 |
| 7 | Phase 4 | 小 | 低 | 仅更新 import |
| 8 | Phase 5 | 中 | 低 | 测试重组 |

---

## 关键原则

1. **行为不变**：重构不改变任何外部 API 行为和业务逻辑
2. **渐进式**：每步完成后运行测试确认无回归
3. **依赖方向严格**：`api → services → models`，禁止反向依赖
4. **每个文件 < 250 行**：超过则考虑拆分
5. **同领域统一风格**：Identity 域全部用类，Agent 域混合风格统一

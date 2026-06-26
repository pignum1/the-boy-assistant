# The Boy Assistant — 项目开发规范

## 项目概述

企业级 AI Multi-Agent 协作平台。FastAPI + SQLAlchemy async + PostgreSQL + Redis + LiteLLM。
当前开发阶段：L4 编排层（Week 6），已完成 L1-L5 基础能力。

## DDD 领域模型划分

项目按以下 5 个限界上下文（Bounded Context）组织代码：

```
┌──────────────────────────────────────────────────────────────────┐
│                        api/v1/ (接口层)                          │
│   仅做参数校验 + 调用领域服务，不含业务逻辑                          │
├──────────┬──────────┬──────────┬──────────┬─────────────────────┤
│ identity │  agent   │knowledge │ workflow  │  infrastructure     │
│ (身份域)  │ (智能域)  │(知识域)   │(编排域)   │  (基础设施域)        │
├──────────┴──────────┴──────────┴──────────┴─────────────────────┤
│                      models/ (数据模型层)                         │
│                      schemas/ (数据传输层)                        │
├──────────────────────────────────────────────────────────────────┤
│  core/ (配置/数据库)  adapters/ (LLM适配)  tools/ (工具执行)       │
└──────────────────────────────────────────────────────────────────┘
```

### 领域 1: Identity（身份域）

| 模型 | 服务 | API | 说明 |
|------|------|-----|------|
| Persona | persona_service.py | personas.py | 角色定义（系统提示词+工具声明） |
| Model | model_router.py | model_router.py | 模型注册+智能路由 |
| Tool | tool_registry.py | tools.py | 工具注册与发现 |
| — | security.py | keys.py | API Key 加密管理 |

**核心职责**：定义"谁"（Persona）、"用什么脑"（Model）、"有什么手"（Tool）

### 领域 2: Agent（智能域）

| 模型 | 服务 | API | 说明 |
|------|------|-----|------|
| Agent | agent_factory.py | agents.py | Agent 生命周期管理 |
| Memory | memory_manager.py | memories.py | 短期/长期记忆 |
| Skill | skill_registry.py, skill_executor.py | skills.py | 技能注册与执行 |
| — | context_manager.py | — | 上下文窗口管理 |
| — | prompt_builder.py | — | Prompt 组装 |
| — | fallback_chain.py | — | 模型降级链 |

**核心职责**：单个 Agent 的完整智能闭环（记忆→技能→推理→输出）

### 领域 3: Knowledge（知识域）

| 模型 | 服务 | API | 说明 |
|------|------|-----|------|
| KnowledgeBase | rag/knowledge_service.py | knowledge.py | 知识库管理 |
| KnowledgeChunk | rag/chunker.py, rag/embedder.py | — | 文档分块与向量化 |
| — | rag/hybrid_search.py | — | 混合检索 |
| — | rag/reranker.py | — | 重排序 |

**核心职责**：知识的外部存储、检索与注入

### 领域 4: Workflow（编排域）

| 模型 | 服务 | API | 说明 |
|------|------|-----|------|
| Team | team_manager.py | teams.py | 团队+成员+角色插槽 |
| TeamMember | team_manager.py | teams.py | 角色- Agent 绑定 |
| SOP | sop_service.py | sops.py | 工作流定义（节点+边） |
| Task | sop_engine.py | tasks.py | 工作流运行实例 |
| — | condition_router.py | — | 条件表达式评估+路由 |
| — | agent_pool.py | — | Agent 池管理 |

**核心职责**：多 Agent 协作编排（团队组建、流程定义、任务执行、人机协作）

### 领域 5: Infrastructure（基础设施域）

| 层 | 文件 | 说明 |
|----|------|------|
| core/ | config.py, database.py | 配置与数据库连接 |
| adapters/llm/ | base.py, litellm_adapter.py, mock_adapter.py, rate_limiter.py | LLM 统一适配 |
| tools/ | base.py, file_ops.py, terminal.py, tool_executor.py | 工具执行引擎 |

**核心职责**：与外部系统交互的技术基础设施

## 代码组织规范

### 目录结构

```
app/
├── core/                    # 基础设施：配置、数据库、安全
├── adapters/llm/            # 基础设施：LLM 适配层
├── models/                  # 数据模型：纯 ORM 定义，无业务逻辑
├── schemas/                 # 数据传输：Pydantic schemas（Request/Response）
├── services/                # 领域服务：核心业务逻辑
│   └── rag/                 #   知识域子模块
├── api/v1/                  # 接口层：HTTP 端点，薄层调用 services
└── tools/                   # 基础设施：工具执行引擎
```

### 分层职责与依赖方向

```
api/v1 → services → models
                ↘       ↗
              adapters / core
```

**严格规则**：
- `api/` 只做参数校验、调用 service、格式化响应，不含业务逻辑
- `services/` 是业务核心，依赖 models 和 adapters，不依赖 api
- `models/` 是纯数据定义，不依赖 services 和 api
- `schemas/` 是纯数据传输对象，不依赖 services
- 禁止循环依赖，禁止跨层调用（api 不能直接操作 ORM）

**DDD 领域边界规则（重要）**：
1. **禁止跨领域直接导入模型**：Workflow 领域不能导入 Team、Agent 等其他领域的模型
2. **通过 ID 引用其他领域实体**：使用 `UUID` 而非模型引用
3. **跨领域操作在 API 层协调**：需要其他领域数据时，在 API 层获取后传入
4. **依赖抽象接口**：使用依赖注入，不依赖具体实现类
5. **基础设施层可被任何领域依赖**：LLM Adapter、Database 等属于基础设施

**错误示例**：
```python
# ❌ 违反 DDD：Workflow 领域直接导入其他领域模型
from app.models.team import Team  # 禁止
from app.models.agent import Agent  # 禁止

class WorkflowGenerator:
    async def generate(self, team_id: UUID):
        team = await self.db.get(Team, team_id)  # 禁止
```

**正确示例**：
```python
# ✅ 遵循 DDD：通过 ID 引用，数据由调用方传入
class WorkflowGenerator:
    async def generate(
        self,
        requirement: str,
        available_agents: list[dict],  # 由调用方提供
    ):
        # 只使用传入的数据，不查询其他领域
```

**API 层协调跨领域操作**：
```python
# ✅ 在 API 层协调跨领域操作
@router.post("/generate")
async def generate_workflow(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    # 1. 在 API 层获取其他领域数据
    agents = await get_team_agents(db, team_id)

    # 2. 传入给 Workflow 领域
    generator = WorkflowGenerator()
    result = await generator.generate(
        requirement=req.requirement,
        available_agents=agents,  # 通过参数传入
    )
```

### 每个领域模块的标准结构

```
services/
  ├── {domain}_service.py    # CRUD + 业务逻辑（应用服务）
  ├── {domain}_engine.py     # 复杂引擎/状态机（领域服务，仅编排域需要）
  └── {domain}_router.py     # 路由/策略（仅需要时创建）

models/
  └── {domain}.py            # ORM 模型（一个文件可含多个关联模型）

schemas/
  └── {domain}.py            # Create/Update/Response schemas

api/v1/
  └── {domain}s.py           # REST 端点
```

## 代码风格

### 通用

- Python 3.12+，使用 `list[dict]` 而非 `List[Dict]`
- 所有 ORM 模型：UUID 主键 + `TIMESTAMPTZ` + `Mapped` 类型注解
- 异步优先：`async def` + `AsyncSession`
- 中文注释说明业务意图，英文写代码

### Service 层

- 类或函数均可，保持同一领域内风格统一
- 每个 service 方法保持单一职责
- 依赖注入通过构造函数 `__init__(self, db: AsyncSession)` 传入
- 错误通过 `raise ValueError` 抛出，由 API 层转 HTTP 状态码

### API 层

- 每个 endpoint 函数不超过 20 行
- 使用 `Depends(get_db)` 注入数据库会话
- 响应格式化统一用 `_xxx_response()` 辅助函数

### Models 层

- 纯数据定义，不含业务逻辑
- 关联关系用 `ForeignKey`，不用 ORM relationship（保持查询显式）
- JSONB 字段用于灵活扩展数据

### 测试

- 每个领域一个测试文件：`tests/test_{domain}.py`
- 单元测试（纯逻辑）和集成测试（真实 DB）分离
- 集成测试使用独立的 `NullPool` 数据库连接
- Mock 外部依赖（LLM 调用），不 Mock 内部服务

## 技术约束

- LLM 调用统一走 `adapters/llm/`，禁止直接 `import litellm`
- 数据库操作统一走 `AsyncSession`，禁止同步 ORM
- 配置统一走 `core/config.py` 的 pydantic-settings，禁止硬编码
- 所有密码/Key 走 `core/security.py` 的 Fernet 加密，禁止明文存储

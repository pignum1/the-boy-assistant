# The Boy Assistant — Backend

企业级 AI Multi-Agent 协作平台后端，支持角色定义、智能对话、知识检索、多 Agent 工作流编排与人机协作。

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| Web 框架 | FastAPI 0.115 |
| ORM | SQLAlchemy 2.0 (async) |
| 数据库 | PostgreSQL 16 + pgvector |
| 缓存 | Redis 7 |
| LLM 网关 | LiteLLM (OpenAI / Claude / GLM / Gemini) |
| 迁移 | Alembic |
| 加密 | Fernet (cryptography) |
| Python | 3.12+ |

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和数据库连接

# 2. 启动依赖服务
docker-compose up -d postgres redis

# 3. 数据库迁移
alembic upgrade head

# 4. 启动服务
uvicorn app.main:app --reload --port 8000

# 5. 验证
curl http://localhost:8000/health
```

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口 + CORS + 种子数据
│   ├── core/                      # 基础设施：配置、数据库、安全
│   │   ├── config.py              # pydantic-settings 配置中心
│   │   ├── database.py            # 异步引擎 + 会话工厂（含连接池管理）
│   │   └── security.py            # Fernet 加密 / API Key 管理
│   ├── models/                    # ORM 模型层（纯数据定义，无业务逻辑）
│   │   ├── persona.py             # 角色
│   │   ├── model.py               # 模型注册
│   │   ├── tool.py                # 工具
│   │   ├── agent.py               # Agent 实例
│   │   ├── memory.py              # 记忆
│   │   ├── skill.py               # 技能
│   │   ├── knowledge_base.py      # 知识库
│   │   ├── knowledge_chunk.py     # 知识分块
│   │   ├── team.py / team_member.py  # 团队 + 成员
│   │   ├── sop.py                 # SOP 工作流定义
│   │   └── task.py                # 任务运行实例
│   ├── schemas/                   # Pydantic DTO（Request / Response）
│   ├── services/                  # 领域服务（核心业务逻辑）
│   ├── api/v1/                    # REST 接口层（薄层，仅校验 + 调用 service）
│   ├── adapters/llm/              # LLM 统一适配层
│   │   ├── base.py                # LLMConfig / LLMResponse 数据类
│   │   ├── litellm_adapter.py     # LiteLLM 封装（含重试）
│   │   ├── mock_adapter.py        # Mock 适配器（开发测试用）
│   │   └── rate_limiter.py        # 令牌桶限流
│   └── tools/                     # 工具执行引擎
│       ├── base.py                # 工具抽象基类
│       ├── file_ops.py            # 文件读写
│       ├── terminal.py            # 终端命令执行
│       └── tool_executor.py       # 工具执行器
├── demos/                         # 演示脚本
├── migrations/                    # Alembic 迁移文件
├── tests/                         # 测试（按领域组织）
├── CLAUDE.md                      # AI 编码规范（DDD 领域定义 + 代码风格）
├── REFACTOR-PLAN.md               # DDD 重构计划
├── docker-compose.yml
├── Dockerfile
├── alembic.ini
└── requirements.txt
```

## 领域模块

项目按 DDD（领域驱动设计）划分为 5 个限界上下文：

```
┌──────────────────────────────────────────────────────────┐
│                     api/v1/ (接口层)                      │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Identity │  Agent   │Knowledge │ Workflow │Infrastructure│
│ (身份域)  │ (智能域)  │ (知识域)  │ (编排域)  │ (基础设施域)  │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│                   models/ + schemas/                      │
├──────────────────────────────────────────────────────────┤
│  core/ (配置/DB)   adapters/ (LLM)   tools/ (工具执行)    │
└──────────────────────────────────────────────────────────┘
```

### 1. Identity 身份域 — "谁" + "用什么脑" + "有什么手"

定义系统中的基础实体：角色、模型、工具。

| 服务文件 | 职责 | API |
|---------|------|-----|
| `persona_service.py` | 角色定义 CRUD + 预置角色 | `/personas` |
| `model_router.py` | 模型注册 + 复杂度路由 | `/router` |
| `tool_registry.py` | 工具注册 + 三层权限 | `/tools` |
| `security.py` | API Key 加密管理 | `/keys` |

### 2. Agent 智能域 — 单个 Agent 的完整智能闭环

管理 Agent 生命周期，包括记忆、技能、上下文、模型降级。

| 服务文件 | 职责 | API |
|---------|------|-----|
| `agent_service.py` | Agent CRUD | `/agents` |
| `agent_chat.py` | 对话执行（Prompt → LLM → 工具 → 记忆） | `/agents/{id}/chat` |
| `agent_factory.py` | Agent 组装 + API Key 解析 | — |
| `agent_pool.py` | 运行时资源池（idle/busy/error） | — |
| `memory_manager.py` | 四层记忆（System/Team/Agent/Context） | `/memories` |
| `skill_registry.py` + `skill_executor.py` | 技能注册与执行 | `/skills` |
| `context_manager.py` | Token 预算 + 上下文窗口管理 | — |
| `prompt_builder.py` | 多层 Prompt 组装器 | — |
| `fallback_chain.py` | 模型降级链 + 熔断器 | — |

### 3. Knowledge 知识域 — 知识的外部存储与检索

支持文档上传、分块、向量化、混合检索和重排序。

| 服务文件 | 职责 | API |
|---------|------|-----|
| `rag/knowledge_service.py` | 知识库管理 | `/knowledge` |
| `rag/chunker.py` | 文档分块 | — |
| `rag/embedder.py` | 向量化 | — |
| `rag/hybrid_search.py` | 混合检索（向量 + 关键词） | — |
| `rag/reranker.py` | 重排序 | — |

### 4. Workflow 编排域 — 多 Agent 协作编排

支持团队组建、SOP 工作流定义、任务执行和人机协作。

| 服务文件 | 职责 | API |
|---------|------|-----|
| `sop_engine.py` | 工作流引擎（启动 → 运行 → 暂停 → 恢复） | — |
| `sop_state.py` | 任务运行时状态数据类 | — |
| `sop_router.py` | 条件路由决策（边映射 + 条件评估） | — |
| `sop_node_executor.py` | 节点执行器（agent/hitl/validation） | — |
| `sop_service.py` | SOP CRUD + YAML 导入/导出 | `/sops` |
| `sop_presets.py` | 预置 SOP 模板 | — |
| `team_manager.py` | 团队 CRUD + 成员角色插槽 | `/teams` |
| `condition_router.py` | 条件表达式评估引擎 | — |
| `loop_controller.py` | 循环退避控制 | — |

### 5. Infrastructure 基础设施域 — 技术基础设施

| 层 | 文件 | 职责 |
|----|------|------|
| core/ | `config.py`, `database.py`, `security.py` | 配置中心 + 异步连接池 + 加密 |
| adapters/llm/ | `base.py`, `litellm_adapter.py`, `mock_adapter.py`, `rate_limiter.py` | LLM 统一适配 + 限流 |
| tools/ | `base.py`, `file_ops.py`, `terminal.py`, `tool_executor.py` | 工具执行引擎 |

## API 概览

| 模块 | 端点 | 说明 |
|------|------|------|
| Health | `GET /health` | 健康检查 |
| Personas | `/api/v1/personas` | 角色定义 CRUD |
| Tools | `/api/v1/tools` | 工具注册 |
| Models | `/api/v1/router` | 模型路由（复杂度分类 + 模型选择） |
| Keys | `/api/v1/keys/status` | API Key 连通性测试 |
| Agents | `/api/v1/agents` | Agent CRUD + 对话 |
| Memories | `/api/v1/memories` | 记忆管理 |
| Skills | `/api/v1/skills` | 技能上传、匹配、执行 |
| Knowledge | `/api/v1/knowledge` | 知识库上传 + 检索 |
| Teams | `/api/v1/teams` | 团队 + 成员管理 |
| SOPs | `/api/v1/sops` | 工作流定义 CRUD + YAML 导入/导出 |
| Tasks | `/api/v1/tasks` | 任务启动 / 恢复 / 查询 / HITL 审批 |

## SOP 工作流

系统核心能力——基于状态机的多 Agent 工作流引擎：

```
[架构师 Agent] → [人工审批(HITL)] → [程序员 Agent] → [验证] → [完成]
      ↑              ↓ reject                           ↓ fail
      └──────────────┘                                  ↑
                       [程序员 Agent] ←──────────────────┘
```

支持特性：
- **节点类型**：agent_action / hitl / validation / start / end
- **条件路由**：`hitl_result == approve`、`validations.passed`、`not validations.passed`
- **三层审批**：任务级 auto_approve → 节点级 require_human → 条件自动审批
- **模型降级**：主模型失败自动切换备用模型（含熔断器）
- **预置模板**：完整开发流程、热修复流程

## 测试

```bash
# 运行全部测试（需要 PostgreSQL 和 Redis 运行中）
pytest tests/ -v

# 仅运行单元测试（不需要数据库）
pytest tests/test_workflow.py -v

# 运行集成测试
pytest tests/test_workflow_integration.py -v

# 运行 API 测试
TESTING=true pytest tests/test_tasks_api.py -v
```

测试文件按领域组织：

```
tests/
├── conftest.py                  # 共享 fixtures + DB 会话工厂
├── test_health.py               # 健康检查
├── test_workflow.py             # Workflow 域单元测试（42 个）
├── test_workflow_integration.py # Workflow 域集成测试（需要 DB）
└── test_tasks_api.py            # Tasks API 端点测试
```

## 分层架构

```
api/v1 → services → models
                ↘       ↗
              adapters / core
```

**严格规则**：
- `api/` 仅做参数校验 + 调用 service，不含业务逻辑
- `services/` 是业务核心，不依赖 api
- `models/` 纯数据定义，不依赖 services 和 api
- 禁止循环依赖，禁止跨层调用

## 相关文档

| 文档 | 说明 |
|------|------|
| [CLAUDE.md](./CLAUDE.md) | AI 编码规范：DDD 领域定义 + 代码风格约束 |
| [REFACTOR-PLAN.md](./REFACTOR-PLAN.md) | DDD 领域重构计划 |
| [FastAPI Docs](http://localhost:8000/docs) | Swagger UI（启动后访问） |
| [Alembic](./alembic.ini) | 数据库迁移配置 |

## Docker 部署

```bash
# 完整启动（PostgreSQL + Redis + Backend）
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 数据库迁移
docker-compose exec backend alembic upgrade head
```

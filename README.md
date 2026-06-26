# The Boy Assistant v5.0

> 企业级 AI Multi-Agent 协作平台 — 三模式引擎 · DDD 领域驱动 · Harness 横切保障

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18-61dafb)](https://react.dev/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 概述

The Boy Assistant 是一个**三模式企业级多 Agent 协作平台**，提供群聊讨论（Swarm）、主管委派（Supervisor）、工作流编排（LangGraph）三种协作范式。通过统一的聊天室界面和 Harness 横切保障层，为企业研发团队提供从自由讨论到严格 SOP 执行的完整协作工具链。

### 核心能力

| 能力 | 说明 |
|------|------|
| **三模式协作** | Swarm（群聊）/ Supervisor（主管委派）/ LangGraph（DAG 工作流），按需切换 |
| **HITL 人机协作** | 三级检测 + 状态机卡片 + 永不禁用输入框 |
| **层级委派** | 基于组织树的自动委派、审核（LCA算法）、升级链 |
| **幻觉对抗** | M7 独立盲审 → drift_detected → 回 M1 重新分析需求 |
| **故障自愈** | Loop Engine 三分类错误策略 + 四步恢复流程 |
| **横切保障** | Harness 拦截器统一 Prompt构建/Token管控/文件提取/审计 |
| **流式渲染** | 逐 token 推送 + 代码块渲染 + Markdown 实时预览 |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    L1 交互层 (Frontend)                     │
│  ChatRoomView · ChatStream · DrawerHost · HITLCard · Input  │
├─────────────────────────────────────────────────────────────┤
│                    L2 通信层 (WebSocket + REST)             │
│  单连接多路复用 · 10+消息类型 · Vite Proxy · Stream Token   │
├──────┬──────────────┬──────────────┬────────────────────────┤
│Swarm │ Supervisor   │  LangGraph   │  ← L3 编排层 (核心域)  │
│Engine│ Engine       │  Engine      │   三模式协作引擎        │
├──────┴──────────────┴──────────────┴────────────────────────┤
│                    L4 能力层 (Identity + Agent + Knowledge)  │
│  AgentFactory · Memory L1-L4 · ContextPipeline · RAG        │
│  ModelAdapter · FallbackChain · WorkspaceMgr · AgentPool    │
├─────────────────────────────────────────────────────────────┤
│                    L5 数据层 (Data)                         │
│     PostgreSQL 16 (主存储) · Redis 7 (缓存/消息)             │
├─────────────────────────────────────────────────────────────┤
│              Harness 横切保障层 (Cross-Cutting)              │
│  before → after → verify → cleanup · Loop Engine · Observer │
└─────────────────────────────────────────────────────────────┘
```

### DDD 领域划分

系统按 5 个限界上下文组织：

| 领域 | 职责 | 核心模块 |
|------|------|---------|
| **Identity** 身份域 | 谁·用什么脑·有什么手 | Persona · Model Router · Tool Registry |
| **Agent** 智能域 | 单 Agent 智能闭环 | Agent Factory · Memory L1-L4 · Context Pipeline · Skill · Fallback |
| **Knowledge** 知识域 | 知识存储与检索 | KnowledgeBase · RAG (Dense+Sparse) · Reranker |
| **Workflow** 编排域 (核心) | 多 Agent 协作 | Team · Session · 三引擎 · HITL · Org Hierarchy · M5/M8 |
| **Infrastructure** 基础设施 | 外部系统交互 | LLM Adapter · Workspace · Observer · Security |

> 详细架构文档：[docs/system-architecture-v5.md](docs/system-architecture-v5.md)

### 架构图

| 编号 | 图 | 说明 |
|------|-----|------|
### 01 · DDD 领域全景
<img src="docs/images/01-DDD领域全景.png" width="100%" />

### 02 · 五层技术架构
<img src="docs/images/02-五层技术架构.png" width="100%" />

### 03 · Supervisor 决策流程
<img src="docs/images/03-Supervisor决策流程.png" width="100%" />

### 04 · Agent 生命周期 + Harness
<img src="docs/images/04-Agent生命周期与Harness.png" width="100%" />

### 05 · Loop Engine + 异常处理
<img src="docs/images/05-LoopEngine与异常处理.png" width="100%" />

### 06 · 通信与数据流
<img src="docs/images/06-通信与数据流.png" width="100%" />

---

## 三模式引擎

### Swarm（群聊模式）

多 Agent 自由讨论，流程从讨论中**涌现**。三阶段流水线：RoundTable 讨论（≤3轮）→ Agent 执行（注入 Harness）→ 完成/HITL。

HITL 三级检测：L1 显式 `__HITL__` 标记 → L2 `**方案X**` 结构化选项 → L3 六特征加权评分（≥3 触发）。

### Supervisor（主管模式）

M0-M7 LangGraph 固定管道，支持组织层级委派：

```
M0(意图) → M1(需求分析) ⇢ M2(澄清) → HITL → M3(编排) → M4(分解) → M6(执行) → M7(验证) → ✓
```

**M7 验证四路路由**（v5 核心）：passed→HITL / major→M6 / **drift→M1**（需求偏差·完整重走）/ critical→HITL

### LangGraph（工作流模式）

用户自定义 DAG 编排，拓扑排序后分层并行执行。7 种节点类型：Start / Agent / Condition / Router / Validation / HITL / End。

---

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- PostgreSQL 16 (pgvector)
- Redis 7

### 后端启动

```bash
cd backend
cp .env.example .env          # 编辑 .env 填入 API Key
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端启动

```bash
cd frontend
npm install
npm run dev                     # Vite 开发服务器 :5173
```

### Docker 启动

```bash
cd backend
cp .env.example .env
docker compose up -d            # PostgreSQL + Redis + Backend
```

---

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 编排引擎 | LangGraph | 状态图驱动，checkpoint 暂停/恢复 |
| LLM 适配 | LiteLLM | 20+ Provider 统一接口 |
| 后端 | FastAPI + WebSocket | 异步原生支持 |
| 数据库 | PostgreSQL 16 (asyncpg) | JSONB · UUID · pgvector |
| 缓存 | Redis 7 | 会话状态 · Pub/Sub · 限流 |
| 前端 | React 18 + TypeScript | useReducer 状态管理 |
| 构建 | Vite | HMR + Proxy 转发 |

---

## 关键设计决策 (ADR)

| ADR | 决策 | 理由 |
|-----|------|------|
| ADR-001 | 三引擎独立·共享能力层 | 三种范式核心约束不同，统一会牺牲灵活性 |
| ADR-002 | 聊天室为唯一入口 | 统一心智模型，模式差异在暗流抽屉 |
| ADR-003 | Harness 横切 vs 分散实现 | 三引擎 80% 重复逻辑，横切降维护成本 |
| ADR-004 | HITL 输入框永不禁用 | LLM 选项不可靠·用户需降级路径 |
| ADR-005 | CollabState 单一状态树 | 内建 checkpoint · 可追踪回滚 |
| ADR-006 | WebSocket 单连接 | 避免多连接时序问题 |

---

## 项目结构

```
the-boy-assistant/
├── README.md
├── .env.example
├── .gitignore
│
├── backend/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── CLAUDE.md                       # 开发规范 + DDD 领域划分
│   │
│   ├── app/
│   │   ├── main.py                     # FastAPI 入口
│   │   │
│   │   ├── core/                       # 基础设施域
│   │   │   ├── config.py               # pydantic-settings 配置
│   │   │   ├── database.py             # async SQLAlchemy 引擎
│   │   │   ├── security.py             # Fernet 加密
│   │   │   ├── auth.py                 # API Key 中间件 + WS 认证
│   │   │   └── rate_limit.py           # 滑动窗口限流
│   │   │
│   │   ├── adapters/llm/               # LLM 适配层
│   │   │   ├── base.py                 # LLMConfig / LLMResponse
│   │   │   ├── litellm_adapter.py      # LiteLLM 统一适配 (20+ Provider)
│   │   │   ├── mock_adapter.py         # 测试 Mock
│   │   │   └── rate_limiter.py         # Provider 级限流
│   │   │
│   │   ├── models/                     # 数据模型层 (纯 ORM)
│   │   │   ├── agent.py, persona.py, model.py, tool.py
│   │   │   ├── team.py, team_member.py, team_mode_configs.py
│   │   │   ├── session.py, session_task.py
│   │   │   ├── workflow.py, workflow_instance.py, workflow_template.py
│   │   │   ├── memory.py, skill.py, sop.py
│   │   │   ├── task.py, user_task.py
│   │   │   └── knowledge_base.py, knowledge_chunk.py, mcp_server.py
│   │   │
│   │   ├── schemas/                    # Pydantic 数据传输对象
│   │   │   └── agent, team, session, workflow, memory, skill 等 (16)
│   │   │
│   │   ├── api/v1/                     # 接口层 (薄层)
│   │   │   ├── ws.py                   # WebSocket 三模式入口
│   │   │   ├── sessions.py             # Session + 消息历史
│   │   │   ├── teams.py                # Team + 模式 + 成员
│   │   │   ├── workflows.py            # Workflow CRUD
│   │   │   └── agents, personas, models, tools, skills, memories 等 (20)
│   │   │
│   │   ├── services/                   # 领域服务层 (核心)
│   │   │   ├── harness.py              # 🛡️ Harness 横切拦截器 (473行)
│   │   │   ├── loop_engine.py          # 🔄 Loop Engine 错误恢复 (253行)
│   │   │   ├── safety_filter.py        # 🔒 安全过滤 (71行)
│   │   │   ├── agent_chat.py           # 单 Agent 调用
│   │   │   ├── agent_chat_stream.py    # 流式 Agent 调用
│   │   │   ├── agent_factory.py        # Agent 工厂
│   │   │   ├── agent_pool.py           # Agent 资源池
│   │   │   ├── context_manager.py      # 上下文窗口管理
│   │   │   ├── memory_manager.py       # 四层记忆管理
│   │   │   ├── fallback_chain.py       # 模型降级链
│   │   │   ├── model_router.py         # 模型智能路由
│   │   │   ├── prompt_builder.py       # Prompt 组装
│   │   │   │
│   │   │   ├── collaboration/          # ⚡ 编排域 (核心域)
│   │   │   │   ├── router.py           # 模式分发 (Mode → Engine)
│   │   │   │   ├── graph.py            # M0-M8 LangGraph 状态图
│   │   │   │   ├── streaming.py        # LangGraph → WebSocket 翻译
│   │   │   │   ├── types.py            # CollabState TypedDict
│   │   │   │   ├── hitl_detector.py    # HITL 三级检测
│   │   │   │   ├── org_hierarchy.py    # 🌳 组织层级 (475行)
│   │   │   │   ├── engines/            # 三引擎
│   │   │   │   │   ├── swarm_engine.py     # 💬 群聊 (864行)
│   │   │   │   │   ├── supervisor_engine.py # 👑 主管
│   │   │   │   │   └── langgraph_engine.py  # 🔀 工作流 (1281行)
│   │   │   │   ├── m0..m8_*.py         # M0-M8 节点 (17个)
│   │   │   │   └── __tests__/          # 编排域测试 (9个)
│   │   │   │
│   │   │   ├── observer/               # 观察者模式
│   │   │   │   ├── events.py           # 15 EventType
│   │   │   │   ├── bus.py              # 异步 EventBus
│   │   │   │   ├── persister.py        # DB 持久化
│   │   │   │   └── token_tracker.py    # Token 追踪
│   │   │   │
│   │   │   ├── rag/                    # 知识域
│   │   │   │   ├── knowledge_service.py
│   │   │   │   ├── chunker.py, embedder.py
│   │   │   │   ├── hybrid_search.py
│   │   │   │   └── reranker.py
│   │   │   │
│   │   │   ├── workspace/              # 工作空间
│   │   │   │   ├── manager.py          # 生命周期 + 隔离
│   │   │   │   ├── snapshot.py         # 快照管理
│   │   │   │   └── file_proxy.py       # 文件代理
│   │   │   │
│   │   │   ├── session_service.py      # Session 管理
│   │   │   ├── team_manager.py         # Team 管理
│   │   │   ├── team_mode_service.py    # 三模式配置
│   │   │   ├── blackboard.py           # Redis Pub/Sub 黑板
│   │   │   └── sop_*, workflow_*       # SOP/Workflow 引擎
│   │   │
│   │   └── tools/                      # 工具执行引擎
│   │       ├── base.py                 # 工具基类
│   │       ├── file_ops.py             # 文件操作
│   │       ├── terminal.py             # 终端执行
│   │       └── tool_executor.py        # 工具调度
│   │
│   ├── migrations/                     # Alembic 迁移 (22个版本)
│   ├── skills/                         # AI Skills (13个)
│   ├── scripts/                        # 运维脚本
│   └── demos/                          # 演示脚本
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json, tsconfig*.json
│   │
│   └── src/
│       ├── App.tsx, main.tsx
│       ├── shared/                     # API 客户端 + 类型 + 工具
│       ├── components/                 # Layout, Sidebar, Loading
│       ├── contexts/                   # ThemeContext
│       │
│       └── features/
│           ├── chatroom/               # 💬 聊天室 (核心)
│           │   ├── ChatRoomView.tsx     # 主容器 (useReducer)
│           │   ├── ChatRoomIndex.tsx    # 模式入口
│           │   ├── store/              # chatRoomReducer + Actions
│           │   ├── hooks/              # useWsEvents, useChatRoomState
│           │   ├── types/              # ChatRoomState, TimelineItem
│           │   ├── components/
│           │   │   ├── chat/           # ChatStream, HITLCard, AgentMessageCard...
│           │   │   ├── drawers/        # DrawerHost, WorkPlan, Artifacts...
│           │   │   ├── header/         # PhaseProgressBar, DrawerToggleButtons
│           │   │   ├── input/          # ChatInput, InputModeBanner
│           │   │   └── shared/         # HITLOptions, AgentAvatar, ErrorBoundary
│           │   └── views/              # Legacy 视图 (SwarmView, SupervisorView)
│           │
│           ├── resources/              # Agent, Persona, Skill, MCP, Model 管理
│           ├── teams/                  # 团队管理
│           ├── sop-designer/           # SOP 设计器
│           ├── sop-runner/             # SOP 运行器
│           ├── workflows/              # Workflow 列表
│           ├── workflow-detail/        # Workflow 详情
│           └── tasks/                  # 任务中心
│
└── docs/
    ├── system-architecture-v5.md       # 完整架构文档 (13章)
    ├── images/                         # 6张架构图 PNG
    └── 架构图-v5-wip/                  # 架构图 HTML 源文件
```

---

## License

MIT

---

*Built with ❤️ by The Boy Assistant Team | v5.0 — 2026*

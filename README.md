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
├── backend/
│   ├── app/
│   │   ├── api/v1/           # REST + WebSocket 端点
│   │   ├── services/         # 领域服务 (DDD 限界上下文)
│   │   │   └── collaboration/ # 编排层 (三引擎 + M0-M8)
│   │   ├── models/           # ORM 数据模型
│   │   ├── core/             # 配置·数据库·安全
│   │   └── adapters/llm/     # LLM 适配层
│   ├── Dockerfile
│   └── docker-compose.yml
├── frontend/
│   └── src/features/chatroom/ # 聊天室 (统一入口)
│       ├── components/       # 消息卡片·抽屉·输入
│       ├── store/            # Reducer + Actions
│       └── hooks/            # WS连接·历史·状态
└── docs/
    ├── system-architecture-v5.md  # 完整架构文档 (13章)
    └── 架构图-v5-wip/             # 6 张交互式架构图 (HTML)
```

---

## License

MIT

---

*Built with ❤️ by The Boy Assistant Team | v5.0 — 2026*

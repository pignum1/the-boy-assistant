---
name: code-standards
description: 工程代码规范与项目结构 — 约束后端/前端工程师按统一项目骨架输出代码（分层目录、命名、错误处理、注释、依赖管理），确保多 agent 产出拼成可运行的工程，而非散落在个人目录的碎片
version: 1.0.0
---

# 工程代码规范与项目结构

你是一名严格遵守工程规范的工程师。你的产出必须能与他人产出**拼成一个可运行的项目**，
而不是各自为政的碎片。**严禁**把所有文件平铺到一个目录、或用 `code_1.py`/`code_2.txt` 这种无意义命名。

## 项目骨架（必须遵守）

所有代码写入工作空间的 **项目根目录**（不是你的个人文件夹），按角色对应的标准目录组织：

### 后端（FastAPI / Python）
```
backend/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── core/                   # 配置、数据库、安全
│   │   ├── config.py
│   │   └── database.py
│   ├── models/                 # SQLAlchemy ORM 模型（纯数据）
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── api/
│   │   └── v1/
│   │       └── routes.py       # 路由（薄层，只调 service）
│   ├── services/               # 业务逻辑
│   └── adapters/               # 外部依赖（LLM 等）
├── tests/
├── requirements.txt
└── README.md
```

### 前端（React / TypeScript）
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── components/             # 通用组件
│   ├── features/               # 业务模块（按功能划分）
│   ├── api/                    # API 调用封装
│   ├── hooks/
│   ├── types/
│   └── styles/
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 文件命名规范

- **用语义化文件名**：`todo_service.py`、`TodoList.tsx`，**绝对禁止** `code_1.py`、`output.txt`、`code_2.tsx`。
- 一个代码块 = 一个文件，文件名来自其内容（类名 / 模块名）。
- 每个代码块用 ```` ```语言 相对路径 ```` 标注，路径带目录（如 ```` ```python backend/app/services/todo_service.py ````）。

## 代码规范

### 通用
- 类型注解齐全（Python type hints / TypeScript interface）
- 函数有 docstring / JSDoc 说明意图
- 错误分层处理：service 抛业务异常，api 层转 HTTP 状态码
- 数据库查询参数化，禁止字符串拼接 SQL
- 配置走环境变量，不硬编码

### 后端（Python）
- `list[dict]` 而非 `List[Dict]`
- async 优先，`async def` + `AsyncSession`
- 日志用 `logging`，分级记录

### 前端（TypeScript）
- 函数组件 + Hooks
- 接口数据有明确的 `interface`/`type`
- API 调用集中在 `api/` 层，组件不直接 fetch

## 输出要求

1. 先用一段说明描述你负责的模块边界与交付的文件清单。
2. 然后逐个输出文件，**每个文件带正确的相对路径**。
3. 最后给出依赖与运行说明（写入 `README.md` 或对应角色的说明文件）。

**记住：你的文件路径决定了它落到项目的哪个位置。路径错了，整个项目就散架了。**

# 可观测性模块 — 基于 LangFuse 的全链路追踪

> 状态：✅ 已实现  
> 技术栈：LangFuse v3.202.1 (自部署) + Python SDK v4.12 + OpenTelemetry OTLP

---

## 1. 架构全景

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          The Boy Assistant Backend                       │
│                                                                          │
│  router.py          agent_executor.py        agent_chat.py              │
│  ┌──────────┐       ┌──────────────┐        ┌──────────┐               │
│  │create_trace()│──→│  span()      │──→     │generation()              │
│  │session_id  │   │  agent+mode   │    │  model+tokens │              │
│  └──────────┘       └──────────────┘        └──────────┘               │
│       │                   │                      │                      │
│       ▼                   ▼                      ▼                      │
│  propagate_attributes  span_meta()           gen_meta()                 │
│  (session_id)          (agent/role/mode)     (provider/model/latency)  │
│       │                   │                      │                      │
│       └───────────────────┴──────────────────────┘                      │
│                           │                                              │
│                    LangFuse SDK v4                                      │
│                    (OTLP HTTP Exporter)                                  │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │
                    OTLP /api/public/otel/v1/traces
                            │
               ┌────────────▼────────────┐
               │   LangFuse Web (:3000)  │  ← Next.js 接收 OTLP，Basic Auth
               │   v3.202.1              │
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │   Redis (BullMQ)        │  ← 队列缓冲
               └────────────┬────────────┘
                            │
               ┌────────────▼────────────┐
               │ LangFuse Worker (:3030) │  ← Node.js 消费队列
               └────────────┬────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                  ▼
   ┌──────────┐    ┌──────────────┐    ┌──────────┐
   │  MinIO   │    │  ClickHouse  │    │PostgreSQL│
   │  :9003   │    │  :8123       │    │ :5432    │
   │ 事件存储  │    │ 时序索引     │    │ 元数据    │
   └──────────┘    └──────────────┘    └──────────┘
```

---

## 2. 三层元数据结构

### Trace 级别（会话/消息）

一个用户消息 → 一条 Root Trace。由 `router.py` 的 `dispatch()` 创建。

```
Name:   [swarm] 产品开发团队 | 帮我设计一个用户认证系统
Tags:   mode:swarm, team:产品开发团队
Meta:   { team_name, team_id, session_id, mode, user_message }
```

### Span 级别（Agent 执行）

每个 Agent 的每次执行 → 一个 Span。由 `agent_executor.py` 创建。

```
Name:   [rewoo] 部署运维-Agent (devops)
Input:  prompt[:1000]
Output: { content, iterations, exec_mode, model, latency_s, status }
Meta:   { agent_name, agent_role, exec_mode, node_key, provider, iteration, session_id, team_id }
```

Phase 子 Span（plan_execute / rewoo / self_consistency / reflexion）：
```
Name:   [plan_execute] Phase 1: Plan
Meta:   { phase_name, phase_index, total_phases, agent_name, exec_mode }
```

### Generation 级别（LLM 调用）

每次 LLM API 调用 → 一个 Generation。由 `agent_chat.py` 创建。

```
Name:   chat:deepseek-v4-pro
Model:  deepseek-v4-pro
Usage:  { prompt_tokens, completion_tokens, total_tokens }
Meta:   { provider, model, agent, exec_mode, latency_s }
```

---

## 3. 核心组件

### 3.1 trace_context.py — 上下文传播

| 方法 | 用途 | 调用位置 |
|------|------|---------|
| `create_trace(name, session_id, metadata, tags)` | 创建根 trace | router.py dispatch() |
| `span(name, metadata, input_data)` | 创建子 span | agent_executor.py |
| `generation(name, model, usage, metadata)` | 创建 LLM 记录 | agent_chat.py |
| `score(name, value, comment)` | 添加评分 | M1 analyzer, M7 verifier |
| `trace_metadata` 类 | 结构化元数据构造 | 所有调用方 |

**关键设计**：
- `propagate_attributes(session_id)` 在 create_trace 中调用，确保 session_id 传播到所有子 span
- 未配置 LANGFUSE_HOST 时所有方法静默降级为 no-op
- 所有异常被 try/except 捕获，不传播到业务逻辑

### 3.2 langfuse_client.py — SDK 适配层

| 函数 | 说明 |
|------|------|
| `get_langfuse_client()` | 全局单例，@lru_cache。未配置返回 None |
| `start_as_current_observation()` | 创建并激活当前 span |
| `propagate_attributes(session_id)` | 传播 session_id |
| `create_score(trace_id, name, value)` | 创建评分 |

### 3.3 alert_webhook.py — 告警通道

| 通道 | 环境变量 | 格式 |
|------|---------|------|
| Slack | `ALERT_WEBHOOK_SLACK` | Block Kit (header + fields + context) |
| Discord | `ALERT_WEBHOOK_DISCORD` | Embed (title + color + fields) |
| Custom | `ALERT_WEBHOOK_CUSTOM` | JSON (type + level + title + details) |

7 种告警类型：escalation / fatal_error / security / hitl_timeout / model_fallback / review_failed / rate_limit。5 级过滤：debug → info → warning → error → critical。

---

## 4. Scores 评分体系

| Score | 来源 | 触发时机 | 值域 |
|-------|------|---------|------|
| `clarity_score` | M1 analyzer | need_clarify / need_confirm | 0.0-1.0 |
| `review_score` | M7 verifier | 验证通过=1.0, 需重做=0.3 | 0.0-1.0 |

---在 LangFuse Dashboard 中按时间聚合，追踪质量趋势。

## 5. 部署架构

```
docker compose -f docker-compose.langfuse.yml up -d

服务:
  clickhouse          :8123, :9000    时序索引
  langfuse-web        :3000           Next.js Dashboard + OTLP 接收
  langfuse-worker     :3030           BullMQ 消费者 → ClickHouse 写入
  minio (宿主机)       :9003           S3 兼容事件存储

复用项目已有:
  postgres (backend)  :5432           元数据存储
  redis   (backend)   :6379           队列 + 缓存
```

---

## 6. 关键设计决策

| 决策 | 说明 |
|------|------|
| **独立进程** | LangFuse 完全独立于业务后端，不共享进程/数据库连接池 |
| **静默降级** | LANGFUSE_HOST 为空时所有 trace 操作变 no-op，0 性能开销 |
| **异步上报** | OTLP HTTP Exporter 批量异步发送，不阻塞 LLM 调用 |
| **按需导入** | langfuse 包惰性导入，未安装时优雅降级 |
| **会话分组** | session_id 通过 propagate_attributes 自动传播到所有 span |
| **结构化元数据** | trace_metadata 类确保 Dashboard 中一致的可筛选维度 |

---

## 7. 验证清单

| 检查项 | 方法 |
|--------|------|
| LangFuse 已启动 | `curl http://localhost:3000/api/public/health` → `{"status":"OK"}` |
| 后端已连接 | 日志 `LangFuse connected: http://localhost:3000` |
| Trace 已生成 | Dashboard Traces 页出现新 trace |
| Session 已分组 | Dashboard Sessions 页按 session_id 显示 |
| Span 可见 | 点开 trace → 展开 span 树 → 看到 agent 层级 |
| 禁用后不影响 | `LANGFUSE_HOST=""` 重启 → 系统正常，仅无新 trace |

---

*文档基于 v5.0 实测环境编写，最后更新：2026-07-01*

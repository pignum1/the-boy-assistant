---
name: sequence-diagram
description: 生成时序图 — API 调用链、微服务交互、认证流程、数据库事务，输出 Mermaid/PlantUML/HTML
version: 1.0.0
---

# 时序图生成器

生成专业的时序图，展示系统组件之间的交互顺序。

## 支持的场景

1. **API 调用链** — 客户端 → API Gateway → Service → DB 完整链路
2. **微服务交互** — 多服务间同步/异步调用、Saga 分布式事务
3. **认证流程** — OAuth 2.0、JWT 刷新、SSO 登录
4. **数据库事务** — 两阶段提交、读写分离、缓存更新策略
5. **消息驱动** — Kafka/RabbitMQ 发布订阅、事件溯源

## 输出格式

- **Mermaid sequenceDiagram** — Markdown 文档嵌入
- **PlantUML** — 复杂条件分支
- **HTML** — 交互式时序图（可缩放、折叠）

## 工作流程

1. 接收交互场景描述
2. 识别参与者（Actor/Service/DB/External）
3. 梳理交互步骤和条件分支
4. 标注同步/异步、超时、重试逻辑
5. 生成图表代码

## 输出规范

- 参与者清晰命名（用户、服务名、数据库名）
- 标注 HTTP 方法（GET/POST/PUT/DELETE）和状态码
- 异步消息标注消息队列名称
- 错误路径用虚线箭头表示
- 添加序号便于讨论引用

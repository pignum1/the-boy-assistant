---
name: db-schema-designer
description: 数据库表结构设计 — ER 图、DDL 生成、索引策略、迁移脚本，支持 PostgreSQL/MySQL，输出 SQL + Mermaid ER 图
version: 1.0.0
---

# 数据库 Schema 设计器

设计和管理数据库表结构，生成 DDL 和 ER 图。

## 支持的数据库

- PostgreSQL（优先）
- MySQL
- SQLite

## 输出内容

1. **ER 图** — Mermaid erDiagram 格式
2. **DDL 脚本** — CREATE TABLE 语句，含注释
3. **索引策略** — 主键、唯一索引、复合索引、部分索引
4. **迁移脚本** — Alembic / Flyway 格式
5. **数据字典** — 所有表和字段的详细说明

## 设计规范

- UUID 主键（PostgreSQL 优先使用 UUID v4）
- TIMESTAMPTZ 时间戳字段
- JSONB 用于灵活扩展字段
- 枚举类型用 VARCHAR + CHECK 约束
- 所有字段添加 COMMENT
- 合理设置默认值和 NOT NULL 约束

## 工作流程

1. 接收业务需求或实体描述
2. 设计表结构（字段、类型、约束）
3. 定义索引策略
4. 生成 DDL + ER 图
5. 附带数据迁移注意事项

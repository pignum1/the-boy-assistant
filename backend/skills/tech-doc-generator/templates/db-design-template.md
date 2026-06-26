# 数据库设计文档: {MODULE_NAME}

## ER 关系图

{Mermaid erDiagram}

## 表结构

### {table_name}

**描述**: {表的用途说明}

| 字段 | 类型 | 约束 | 默认值 | 描述 |
|------|------|------|--------|------|
| id | UUID | PK | gen_random_uuid() | 主键 |
| name | VARCHAR(255) | NOT NULL | | 名称 |
| status | VARCHAR(20) | NOT NULL, CHECK | 'active' | 状态 |
| metadata | JSONB | | '{}' | 扩展字段 |
| created_at | TIMESTAMPTZ | NOT NULL | now() | 创建时间 |
| updated_at | TIMESTAMPTZ | NOT NULL | now() | 更新时间 |

**索引**:

| 名称 | 字段 | 类型 | 用途 |
|------|------|------|------|
| idx_{table}_name | name | B-tree | 按名称搜索 |
| idx_{table}_status | status | B-tree | 按状态筛选 |
| idx_{table}_created | created_at | B-tree | 排序 |

**COMMENT 示例**:
```sql
COMMENT ON TABLE {table_name} IS '{表描述}';
COMMENT ON COLUMN {table_name}.id IS '主键 UUID';
COMMENT ON COLUMN {table_name}.status IS '状态: active, inactive, deleted';
```

## Migration 注意事项

1. 新增列必须有默认值（避免全表 UPDATE）
2. 删除列先标记为 deprecated，下个版本再删除
3. 索引创建使用 CONCURRENTLY 避免锁表
4. 大表 DDL 在低峰期执行

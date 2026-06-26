-- ============================================================
-- PostgreSQL DDL Template
-- 使用 UUID PK, TIMESTAMPTZ, JSONB, CHECK 约束
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- Table: {table_name}
-- ============================================================
CREATE TABLE {table_name} (
    -- 主键
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基础字段
    name            VARCHAR(255)    NOT NULL,
    description     TEXT,
    status          VARCHAR(20)     NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'inactive', 'deleted')),

    -- 扩展字段
    metadata        JSONB           NOT NULL DEFAULT '{}',

    -- 审计字段
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- 软删除
    deleted_at      TIMESTAMPTZ
);

-- 索引
CREATE INDEX idx_{table}_name ON {table_name} (name);
CREATE INDEX idx_{table}_status ON {table_name} (status) WHERE deleted_at IS NULL;
CREATE INDEX idx_{table}_created ON {table_name} (created_at DESC);
CREATE INDEX idx_{table}_metadata ON {table_name} USING GIN (metadata);

-- 注释
COMMENT ON TABLE {table_name} IS '{表描述}';
COMMENT ON COLUMN {table_name}.id IS '主键 UUID v4';
COMMENT ON COLUMN {table_name}.status IS '状态: active/inactive/deleted';
COMMENT ON COLUMN {table_name}.metadata IS 'JSONB 扩展字段';
COMMENT ON COLUMN {table_name}.deleted_at IS '软删除时间戳, NULL 表示未删除';

-- 自动更新 updated_at 触发器
CREATE OR REPLACE FUNCTION update_{table}_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_{table}_updated_at
    BEFORE UPDATE ON {table_name}
    FOR EACH ROW
    EXECUTE FUNCTION update_{table}_updated_at();

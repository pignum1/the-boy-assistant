-- ============================================================
-- MySQL DDL Template
-- ============================================================

CREATE TABLE {table_name} (
    -- 主键
    id              CHAR(36)        NOT NULL,

    -- 基础字段
    name            VARCHAR(255)    NOT NULL,
    description     TEXT,
    status          VARCHAR(20)     NOT NULL DEFAULT 'active',

    -- 扩展字段
    metadata        JSON,

    -- 审计字段
    created_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),

    -- 软删除
    deleted_at      DATETIME(6),

    PRIMARY KEY (id),
    INDEX idx_{table}_name (name),
    INDEX idx_{table}_status (status),
    INDEX idx_{table}_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 注释
ALTER TABLE {table_name} COMMENT = '{表描述}';
ALTER TABLE {table_name} MODIFY COLUMN id CHAR(36) COMMENT '主键 UUID';
ALTER TABLE {table_name} MODIFY COLUMN status VARCHAR(20) COMMENT '状态: active/inactive/deleted';

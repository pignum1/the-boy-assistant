-- LangFuse 可观测性 — 数据库初始化
-- 在 PostgreSQL 中创建 langfuse 库，供 LangFuse Server 使用
--
-- 执行方式（Docker）:
--   docker exec -it <postgres-container> psql -U theboy -d theboy -c "CREATE DATABASE langfuse;"
--
-- 执行方式（本地）:
--   psql -U theboy -d theboy -c "CREATE DATABASE langfuse;"
--
-- 之后启动 LangFuse:
--   docker compose -f docker-compose.langfuse.yml up -d

-- 如果 langfuse 库已存在，先删除（仅开发环境）
-- DROP DATABASE IF EXISTS langfuse;

CREATE DATABASE langfuse
  WITH OWNER = theboy
       ENCODING = 'UTF8'
       LC_COLLATE = 'en_US.UTF-8'
       LC_CTYPE = 'en_US.UTF-8'
       TEMPLATE = template0;

COMMENT ON DATABASE langfuse IS 'LangFuse LLM Observability — traces, spans, generations';

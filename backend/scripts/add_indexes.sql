-- 数据库索引优化（2025-06-23）
-- 针对高频查询字段补充索引，提升查询性能
-- 执行方式: psql -U <user> -d theboy -f scripts/add_indexes.sql

-- Session: 按团队查会话、按状态过滤
CREATE INDEX IF NOT EXISTS ix_sessions_team_id ON sessions(team_id);
CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS ix_sessions_team_status ON sessions(team_id, status);

-- Memory: 按会话查历史记录（聊天室加载）
CREATE INDEX IF NOT EXISTS ix_memories_session_id ON memories(session_id);

-- TeamMember: 查团队所有成员、通过 agent 查所属团队
CREATE INDEX IF NOT EXISTS ix_team_members_team_id ON team_members(team_id);
CREATE INDEX IF NOT EXISTS ix_team_members_agent_id ON team_members(agent_id);

-- Agent: 关联查询
CREATE INDEX IF NOT EXISTS ix_agents_persona_id ON agents(persona_id);
CREATE INDEX IF NOT EXISTS ix_agents_default_model_id ON agents(default_model_id);

-- Model: 按 provider 查模型（降级链）、按 is_active 过滤
CREATE INDEX IF NOT EXISTS ix_models_provider ON models(provider);
CREATE INDEX IF NOT EXISTS ix_models_is_active ON models(is_active);

-- Tool: MCP 服务器发现工具
CREATE INDEX IF NOT EXISTS ix_tools_server_id ON tools(server_id);

-- Workflow: 按状态和模板类型过滤
CREATE INDEX IF NOT EXISTS ix_workflows_status ON workflows(status);
CREATE INDEX IF NOT EXISTS ix_workflows_template_type ON workflows(template_type);

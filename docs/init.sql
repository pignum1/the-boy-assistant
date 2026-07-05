-- ============================
-- The Boy Assistant v5.0 初始化 SQL
-- 包含：表结构 + 初始数据（Agent / Team / Workflow / Workflow 绑定）
-- ============================

-- ════════════════ 表结构 ════════════════

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

CREATE TABLE public.agents (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    default_model_id uuid NOT NULL,
    persona_id uuid NOT NULL,
    tools character varying[],
    status character varying(20) NOT NULL,
    reviewed_count integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    execution_mode character varying(20) DEFAULT 'single_pass'::character varying NOT NULL,
    execution_config jsonb
);

CREATE TABLE public.models (
    id uuid NOT NULL,
    provider character varying(50) NOT NULL,
    model_name character varying(100) NOT NULL,
    display_name character varying(100) NOT NULL,
    capabilities character varying[],
    context_window integer NOT NULL,
    rpm_limit integer NOT NULL,
    tpm_limit integer NOT NULL,
    api_key_ref character varying(500),
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.personas (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    system_prompt text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.skills (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    prompt text NOT NULL,
    category character varying(50),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.tools (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    tool_type character varying(50) NOT NULL,
    config jsonb,
    server_id uuid,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.teams (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    icon character varying(10),
    collaboration_mode character varying(20) NOT NULL,
    leader_id uuid,
    capabilities character varying[],
    default_tools character varying[],
    knowledge_sources character varying[],
    allow_agent_to_agent boolean NOT NULL,
    require_hitl_for character varying[],
    max_parallel_agents integer NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_members (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    agent_id uuid NOT NULL,
    role_name character varying(100) NOT NULL,
    role_icon character varying(10),
    capabilities character varying[],
    preferred_model uuid,
    tools character varying[],
    is_required boolean NOT NULL,
    can_delegate boolean NOT NULL,
    joined_at timestamp with time zone NOT NULL
);

CREATE TABLE public.memories (
    id uuid NOT NULL,
    level character varying(20) NOT NULL,
    team_id uuid,
    agent_id uuid,
    session_id character varying(100),
    type character varying(20) NOT NULL,
    content text NOT NULL,
    importance double precision NOT NULL,
    created_by character varying(50),
    metadata jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.sessions (
    id uuid NOT NULL,
    team_id uuid,
    title character varying(200),
    status character varying(20) NOT NULL,
    mode character varying(50) DEFAULT 'discussion'::character varying,
    workspace_path character varying(500),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    message_count integer DEFAULT 0,
    task_total integer DEFAULT 0,
    task_completed integer DEFAULT 0
);

CREATE TABLE public.session_tasks (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    task_id character varying(50) NOT NULL,
    name character varying(200),
    status character varying(20) NOT NULL,
    agent_name character varying(100),
    agent_emoji character varying(10),
    phase_name character varying(100),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.workflows (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    template_type character varying(50),
    definition jsonb NOT NULL,
    version integer NOT NULL,
    created_by uuid,
    is_template boolean NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.workflow_nodes (
    id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    node_key character varying(100) NOT NULL,
    label character varying(200) NOT NULL,
    type character varying(50) NOT NULL,
    position_x double precision NOT NULL,
    position_y double precision NOT NULL,
    config jsonb,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.workflow_edges (
    id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    source_id uuid NOT NULL,
    target_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    condition jsonb,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_langgraph_configs (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    workflow_id uuid,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_langgraph_node_bindings (
    id uuid NOT NULL,
    config_id uuid NOT NULL,
    node_key character varying(100) NOT NULL,
    agent_id uuid NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_swarm_configs (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    max_rounds integer NOT NULL,
    speak_strategy character varying(20) NOT NULL,
    termination_condition jsonb,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_supervisor_configs (
    id uuid NOT NULL,
    team_id uuid NOT NULL,
    leader_member_id uuid,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.team_supervisor_relations (
    id uuid NOT NULL,
    config_id uuid NOT NULL,
    member_id uuid NOT NULL,
    supervisor_member_id uuid,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.mcp_servers (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    transport character varying(20) NOT NULL,
    url character varying(500),
    command character varying(500),
    args character varying[],
    env jsonb,
    api_key_ref character varying(500),
    status character varying(20) NOT NULL,
    config jsonb,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.knowledge_bases (
    id uuid NOT NULL,
    name character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    team_id uuid,
    agent_id uuid,
    skill_id uuid,
    description text,
    file_name character varying(500),
    chunk_count integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.knowledge_chunks (
    id uuid NOT NULL,
    knowledge_base_id uuid NOT NULL,
    content text NOT NULL,
    chunk_index integer NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.node_executions (
    id uuid NOT NULL,
    instance_id uuid NOT NULL,
    node_id uuid,
    node_type character varying(50) NOT NULL,
    node_label character varying(100),
    status character varying(50) NOT NULL,
    input jsonb,
    output jsonb,
    error_message text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    retry_count integer NOT NULL,
    agent_id uuid,
    agent_name character varying(100),
    model_used character varying(100),
    provider_used character varying(50),
    prompt_tokens integer,
    completion_tokens integer,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.workflow_instances (
    id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    session_id uuid NOT NULL,
    status character varying(50) NOT NULL,
    current_node_id uuid,
    state jsonb,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);

CREATE TABLE public.workflow_templates (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    template_type character varying(50),
    definition jsonb NOT NULL,
    version integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.observer_events (
    id uuid NOT NULL,
    type character varying(100) NOT NULL,
    session_id character varying(100),
    agent_name character varying(100),
    payload jsonb,
    "timestamp" timestamp with time zone NOT NULL
);

CREATE TABLE public.sops (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    team_id uuid,
    definition jsonb NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE public.tasks (
    id uuid NOT NULL,
    sop_id uuid,
    session_id uuid,
    name character varying(200) NOT NULL,
    status character varying(20) NOT NULL,
    assignee_agent_id uuid,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

-- ════════════════ 索引 ════════════════

ALTER TABLE ONLY public.agents ADD CONSTRAINT agents_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.models ADD CONSTRAINT models_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.personas ADD CONSTRAINT personas_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.skills ADD CONSTRAINT skills_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.tools ADD CONSTRAINT tools_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.teams ADD CONSTRAINT teams_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_members ADD CONSTRAINT team_members_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.memories ADD CONSTRAINT memories_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sessions ADD CONSTRAINT sessions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.session_tasks ADD CONSTRAINT session_tasks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.workflows ADD CONSTRAINT workflows_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.workflow_nodes ADD CONSTRAINT workflow_nodes_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.workflow_edges ADD CONSTRAINT workflow_edges_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_langgraph_configs ADD CONSTRAINT team_langgraph_configs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_langgraph_node_bindings ADD CONSTRAINT team_langgraph_node_bindings_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_swarm_configs ADD CONSTRAINT team_swarm_configs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_supervisor_configs ADD CONSTRAINT team_supervisor_configs_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.team_supervisor_relations ADD CONSTRAINT team_supervisor_relations_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mcp_servers ADD CONSTRAINT mcp_servers_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.knowledge_bases ADD CONSTRAINT knowledge_bases_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.knowledge_chunks ADD CONSTRAINT knowledge_chunks_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.node_executions ADD CONSTRAINT node_executions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.workflow_instances ADD CONSTRAINT workflow_instances_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.workflow_templates ADD CONSTRAINT workflow_templates_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.observer_events ADD CONSTRAINT observer_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.sops ADD CONSTRAINT sops_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.tasks ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);

-- 外键
ALTER TABLE ONLY public.team_members ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.team_members ADD CONSTRAINT team_members_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.workflow_nodes ADD CONSTRAINT workflow_nodes_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.workflow_edges ADD CONSTRAINT workflow_edges_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.team_langgraph_configs ADD CONSTRAINT team_langgraph_configs_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.team_langgraph_configs ADD CONSTRAINT team_langgraph_configs_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.team_langgraph_node_bindings ADD CONSTRAINT team_langgraph_node_bindings_config_id_fkey FOREIGN KEY (config_id) REFERENCES public.team_langgraph_configs(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.team_langgraph_node_bindings ADD CONSTRAINT team_langgraph_node_bindings_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.agents(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.node_executions ADD CONSTRAINT node_executions_instance_id_fkey FOREIGN KEY (instance_id) REFERENCES public.workflow_instances(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.workflow_instances ADD CONSTRAINT workflow_instances_workflow_id_fkey FOREIGN KEY (workflow_id) REFERENCES public.workflows(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.knowledge_chunks ADD CONSTRAINT knowledge_chunks_knowledge_base_id_fkey FOREIGN KEY (knowledge_base_id) REFERENCES public.knowledge_bases(id) ON DELETE CASCADE;

-- 唯一约束
CREATE UNIQUE INDEX ix_agents_name ON public.agents USING btree (name);
CREATE UNIQUE INDEX ix_team_langgraph_configs_team_id ON public.team_langgraph_configs USING btree (team_id);
CREATE UNIQUE INDEX ix_team_swarm_configs_team_id ON public.team_swarm_configs USING btree (team_id);
CREATE UNIQUE INDEX ix_team_supervisor_configs_team_id ON public.team_supervisor_configs USING btree (team_id);

-- 常用索引
CREATE INDEX ix_sessions_team_id ON public.sessions USING btree (team_id);
CREATE INDEX ix_sessions_status ON public.sessions USING btree (status);
CREATE INDEX ix_memories_session_id ON public.memories USING btree (session_id);
CREATE INDEX ix_team_members_team_id ON public.team_members USING btree (team_id);
CREATE INDEX ix_team_members_agent_id ON public.team_members USING btree (agent_id);
CREATE INDEX ix_workflow_edges_source_id ON public.workflow_edges USING btree (source_id);
CREATE INDEX ix_workflow_edges_workflow_id ON public.workflow_edges USING btree (workflow_id);
CREATE INDEX ix_workflow_nodes_workflow_id ON public.workflow_nodes USING btree (workflow_id);
CREATE INDEX ix_workflows_status ON public.workflows USING btree (status);
CREATE INDEX idx_node_executions_instance_id ON public.node_executions USING btree (instance_id);
CREATE INDEX idx_node_executions_status ON public.node_executions USING btree (status);

-- ════════════════ 初始数据 ════════════════

-- 默认 Persona（系统自动创建）
INSERT INTO personas (id, name, description, system_prompt, created_at, updated_at) VALUES
  ('00000000-0000-0000-0000-000000000001', 'Default Agent', '默认 Agent 角色', '你是一个 AI Agent，用中文回答。', NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000002', 'Supervisor', '主管 Agent 角色', '你是团队主管，负责分析需求、拆解任务并分配给合适的团队成员。', NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000003', 'Worker', 'Worker Agent 角色', '你是团队成员，根据分配的指令完成具体工作。', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- 默认 Model
INSERT INTO models (id, provider, model_name, display_name, context_window, rpm_limit, tpm_limit, is_active, created_at, updated_at) VALUES
  ('00000000-0000-0000-0000-000000000001', 'openai', 'gpt-4o', 'GPT-4o', 128000, 500, 200000, true, NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000002', 'openai', 'gpt-4o-mini', 'GPT-4o Mini', 128000, 3000, 200000, true, NOW(), NOW()),
  ('00000000-0000-0000-0000-000000000003', 'openai', 'deepseek-v4-pro', 'DeepSeek v4 Pro', 128000, 500, 200000, true, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Agent 种子数据
INSERT INTO agents (id, name, default_model_id, persona_id, status, reviewed_count, created_at, updated_at, execution_mode) VALUES
  ('1692749d-a00a-4f8e-b8ca-057fbe46ae11', '产品经理-Agent', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'plan_execute'),
  ('b2acb11b-b867-40cf-966b-c9be77684046', '架构师-Agent',    '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'self_consistency'),
  ('58f4721c-3fd4-484e-917e-57c1f382ccdf', '后端工程师-Agent', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'react'),
  ('facc3a7c-6f4c-4d8e-82c1-79ec9d2983e3', '前端工程师-Agent', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'single_pass'),
  ('1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', '测试员-Agent',    '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'reflexion'),
  ('4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI设计师-Agent',   '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'chain_of_thought'),
  ('72b9e3fc-8a12-4a5b-9c31-d5a8f7e69140', '部署运维-Agent',  '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'rewoo')
ON CONFLICT (id) DO NOTHING;

-- Team 种子数据（三种协作模式）
INSERT INTO teams (id, name, description, icon, collaboration_mode, capabilities, default_tools, allow_agent_to_agent, require_hitl_for, max_parallel_agents, status, created_at, updated_at) VALUES
  ('f4859cb3-d9c4-431d-b89b-33c048e3ec11', '产品开发团队', 'Swarm 群聊模式 — 多 Agent 自由讨论协作', '💬', 'swarm', '{}', '{}', true, '{}', 5, 'active', NOW(), NOW()),
  ('4948c302-365f-47aa-84cb-6fceb0138952', 'Delegation验证团队', 'Supervisor 主管模式 — Leader 分解任务委派执行', '👑', 'supervisor', '{}', '{}', true, '{}', 5, 'active', NOW(), NOW()),
  ('45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '工作流验证团队', 'LangGraph 图编排模式 — 预定义 DAG 按序执行', '🔀', 'langgraph', '{}', '{}', true, '{}', 5, 'active', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- 团队成员
INSERT INTO team_members (id, team_id, agent_id, role_name, role_icon, capabilities, is_required, can_delegate, joined_at) VALUES
  -- Swarm
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', 'PM', '📋', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', 'b2acb11b-b867-40cf-966b-c9be77684046', 'Architect', '🏗️', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '58f4721c-3fd4-484e-917e-57c1f382ccdf', 'Backend', '💻', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', 'facc3a7c-6f4c-4d8e-82c1-79ec9d2983e3', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '72b9e3fc-8a12-4a5b-9c31-d5a8f7e69140', 'DevOps', '🚀', '{}', true, true, NOW()),
  -- Supervisor
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', 'PM', '📋', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', 'b2acb11b-b867-40cf-966b-c9be77684046', 'Architect', '🏗️', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '58f4721c-3fd4-484e-917e-57c1f382ccdf', 'Backend', '💻', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', 'facc3a7c-6f4c-4d8e-82c1-79ec9d2983e3', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '72b9e3fc-8a12-4a5b-9c31-d5a8f7e69140', 'DevOps', '🚀', '{}', true, true, NOW()),
  -- LangGraph
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', 'PM', '📋', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', 'b2acb11b-b867-40cf-966b-c9be77684046', 'Architect', '🏗️', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '58f4721c-3fd4-484e-917e-57c1f382ccdf', 'Backend', '💻', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', 'facc3a7c-6f4c-4d8e-82c1-79ec9d2983e3', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '72b9e3fc-8a12-4a5b-9c31-d5a8f7e69140', 'DevOps', '🚀', '{}', true, true, NOW());

-- ════════════════ LangGraph 工作流数据 ════════════════

-- Workflow（二分查找开发流程）
INSERT INTO workflows (id, name, description, definition, version, is_template, status, created_at, updated_at) VALUES
  ('fa9ffe78-d7aa-451b-b221-a7f252f47a38', '二分查找开发流程', 'Python二分查找函数的开发与测试流程', '{}', 1, false, 'active', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- Workflow 节点
INSERT INTO workflow_nodes (id, workflow_id, node_key, label, type, position_x, position_y, config, created_at) VALUES
  ('37200434-d091-4c90-a9b0-9e5437362cf1', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'start', '开始', 'start', 250, 50, '{}', NOW()),
  ('21054c17-f4f1-4686-a1ee-72898d9ea812', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'dev', '编写代码', 'task', 250, 150, '{}', NOW()),
  ('2e296607-23a7-43aa-9a82-efa98d23f8a5', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'test', '运行测试', 'task', 250, 250, '{}', NOW()),
  ('53951d3d-26cc-4479-8be3-d76b5bea9d08', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'end', '结束', 'end', 250, 350, '{}', NOW())
ON CONFLICT (id) DO NOTHING;

-- Workflow 边
INSERT INTO workflow_edges (id, workflow_id, source_id, target_id, type, created_at) VALUES
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '37200434-d091-4c90-a9b0-9e5437362cf1', '21054c17-f4f1-4686-a1ee-72898d9ea812', 'forward', NOW()),
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '21054c17-f4f1-4686-a1ee-72898d9ea812', '2e296607-23a7-43aa-9a82-efa98d23f8a5', 'forward', NOW()),
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '2e296607-23a7-43aa-9a82-efa98d23f8a5', '53951d3d-26cc-4479-8be3-d76b5bea9d08', 'forward', NOW())
ON CONFLICT DO NOTHING;

-- Team LangGraph 配置（绑定）
INSERT INTO team_langgraph_configs (id, team_id, workflow_id, created_at) VALUES
  ('710fc2a1-b6c5-4192-8b01-53787106e5ec', '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', NOW())
ON CONFLICT (team_id) DO UPDATE SET workflow_id = 'fa9ffe78-d7aa-451b-b221-a7f252f47a38';

-- Node → Agent 绑定
INSERT INTO team_langgraph_node_bindings (id, config_id, node_key, agent_id, created_at) VALUES
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'dev', '58f4721c-3fd4-484e-917e-57c1f382ccdf', NOW()),
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'test', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', NOW())
ON CONFLICT DO NOTHING;

-- ════════════════ Team Supervisor 配置 ════════════════

INSERT INTO team_supervisor_configs (id, team_id, created_at) VALUES
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', NOW())
ON CONFLICT (team_id) DO NOTHING;

-- ════════════════ Team Swarm 配置 ════════════════

INSERT INTO team_swarm_configs (id, team_id, max_rounds, speak_strategy, created_at) VALUES
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', 3, 'auto', NOW())
ON CONFLICT (team_id) DO NOTHING;

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
  ('facc3a7c-c310-4c30-88f7-325b83a8867c', '前端工程师-Agent', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'single_pass'),
  ('1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', '测试员-Agent',    '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'reflexion'),
  ('4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI设计师-Agent',   '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'chain_of_thought'),
  ('008c5ac7-b5b4-44b0-8cf7-bc78ed8fd6b5', '部署运维-Agent',  '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'active', 0, NOW(), NOW(), 'rewoo')
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
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', 'facc3a7c-c310-4c30-88f7-325b83a8867c', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), 'f4859cb3-d9c4-431d-b89b-33c048e3ec11', '008c5ac7-b5b4-44b0-8cf7-bc78ed8fd6b5', 'DevOps', '🚀', '{}', true, true, NOW()),
  -- Supervisor
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', 'PM', '📋', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', 'b2acb11b-b867-40cf-966b-c9be77684046', 'Architect', '🏗️', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '58f4721c-3fd4-484e-917e-57c1f382ccdf', 'Backend', '💻', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', 'facc3a7c-c310-4c30-88f7-325b83a8867c', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), '4948c302-365f-47aa-84cb-6fceb0138952', '008c5ac7-b5b4-44b0-8cf7-bc78ed8fd6b5', 'DevOps', '🚀', '{}', true, true, NOW()),
  -- LangGraph
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', 'PM', '📋', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', 'b2acb11b-b867-40cf-966b-c9be77684046', 'Architect', '🏗️', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '58f4721c-3fd4-484e-917e-57c1f382ccdf', 'Backend', '💻', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', 'facc3a7c-c310-4c30-88f7-325b83a8867c', 'Frontend', '🌐', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', 'QA', '🧪', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '4bbc7f1a-50a1-4699-a4a3-050f30aba050', 'UI', '🎨', '{}', true, true, NOW()),
  (gen_random_uuid(), '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '008c5ac7-b5b4-44b0-8cf7-bc78ed8fd6b5', 'DevOps', '🚀', '{}', true, true, NOW());

-- ════════════════ LangGraph 工作流数据 ════════════════

-- Workflow 1: 简单流程（保留兼容）
INSERT INTO workflows (id, name, description, definition, version, is_template, status, created_at, updated_at) VALUES
  ('fa9ffe78-d7aa-451b-b221-a7f252f47a38', '二分查找开发流程', 'Python二分查找函数的开发与测试流程', '{}', 1, false, 'active', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO workflow_nodes (id, workflow_id, node_key, label, type, position_x, position_y, config, created_at) VALUES
  ('37200434-d091-4c90-a9b0-9e5437362cf1', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'start', '开始', 'start', 250, 50, '{}', NOW()),
  ('21054c17-f4f1-4686-a1ee-72898d9ea812', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'dev', '编写代码', 'task', 250, 150, '{}', NOW()),
  ('2e296607-23a7-43aa-9a82-efa98d23f8a5', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'test', '运行测试', 'task', 250, 250, '{}', NOW()),
  ('53951d3d-26cc-4479-8be3-d76b5bea9d08', 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', 'end', '结束', 'end', 250, 350, '{}', NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO workflow_edges (id, workflow_id, source_id, target_id, type, created_at) VALUES
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '37200434-d091-4c90-a9b0-9e5437362cf1', '21054c17-f4f1-4686-a1ee-72898d9ea812', 'forward', NOW()),
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '21054c17-f4f1-4686-a1ee-72898d9ea812', '2e296607-23a7-43aa-9a82-efa98d23f8a5', 'forward', NOW()),
  (gen_random_uuid(), 'fa9ffe78-d7aa-451b-b221-a7f252f47a38', '2e296607-23a7-43aa-9a82-efa98d23f8a5', '53951d3d-26cc-4479-8be3-d76b5bea9d08', 'forward', NOW())
ON CONFLICT DO NOTHING;

-- ════════════════ Workflow 2: 软件功能开发全流程（含人工审核打回） ════════════════
-- 15节点 · 20边 · 3道人工审核关卡 · 5条打回路径（含并行打回）

INSERT INTO workflows (id, name, description, definition, version, is_template, status, created_at, updated_at) VALUES
  ('62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '软件功能开发全流程（含人工审核打回）',
   '完整软件功能开发流程，包含3道人工审核关卡和4条打回路径。需求评审→方案评审→代码评审，每道关卡可打回重做。',
   '{}', 1, false, 'active', NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description;

-- 15个节点：2个标记(start/end) + 5个agent + 3个hitl + 3个condition + 1个validation
INSERT INTO workflow_nodes (id, workflow_id, node_key, label, type, position_x, position_y, config, created_at) VALUES
  -- 开始/结束
  ('20ddfd33-2ba9-47ed-bf7c-0924ec2425bf', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'start', '🚀 开始', 'start', 250, 20, '{}', NOW()),
  ('811aa1f0-f99e-4792-92ca-791d6ba38b96', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'end', '✅ 完成', 'end', 250, 1220, '{}', NOW()),

  -- 阶段1: 需求分析 → 需求评审(HITL关卡1)
  ('894ff415-f485-4a16-89f3-004ba9a35a33', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'requirement_analysis',
   '📋 需求分析', 'agent', 250, 120,
   '{"instruction": "分析用户需求，输出结构化需求文档（功能描述、验收标准、优先级）。作为产品经理，请仔细分析并输出完整的需求文档。", "timeout": 600}', NOW()),

  ('476f2f3b-4da0-4436-bc68-b5daa8fea616', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'requirement_review',
   '👀 需求评审（人工审核）', 'hitl', 460, 210,
   '{"instruction": "【审核关卡1】请审核需求文档是否完整、合理。\n\n请回复：\n✅ 通过 — 需求清晰，可以进入方案设计\n❌ 打回 — 需求不明确，需要重新分析\n💬 有条件通过 — 指出需要补充的内容后继续", "timeout": 1200}', NOW()),

  ('21fd1bab-0293-47b1-ba4b-c5ca91aab31e', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'requirement_review_check',
   '🔀 需求评审结果', 'condition', 460, 310,
   '{"expression": "contains:✅", "on_true_node_key": "solution_design", "on_false_node_key": "requirement_analysis"}', NOW()),

  -- 阶段2: 方案设计 → 方案评审(HITL关卡2)
  ('0379a95f-cd70-4424-ae7b-684eb3ec02f8', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'solution_design',
   '🏗️ 方案设计', 'agent', 250, 320,
   '{"instruction": "基于需求文档设计技术方案。请输出：1) 架构设计 2) 模块划分 3) 接口定义 4) 数据模型 5) 技术选型理由。", "timeout": 900}', NOW()),

  ('0a6ae93d-8e47-4643-a873-9d7ed7071834', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'solution_review',
   '👀 方案评审（人工审核）', 'hitl', 460, 410,
   '{"instruction": "【审核关卡2】请审核技术方案是否合理可行。\n\n请回复：\n✅ 通过 — 方案可行，可以进入开发阶段\n❌ 打回 — 方案有问题，需要重新设计\n💬 有条件通过 — 指出注意要点后继续", "timeout": 1200}', NOW()),

  ('b1ec772c-dd90-48d5-b13f-fc98f633d505', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'solution_review_check',
   '🔀 方案评审结果', 'condition', 460, 510,
   '{"expression": "contains:✅", "on_true_node_key": "backend_dev", "on_false_node_key": "solution_design"}', NOW()),

  -- 阶段3: 并行开发(后端+前端) → 代码评审(HITL关卡3)
  ('8a8bedf0-80f2-43c2-a7bd-fe359845130a', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'backend_dev',
   '💻 后端开发', 'agent', 120, 600,
   '{"instruction": "根据技术方案实现后端代码。包括：API endpoint、Service层、数据访问层、单元测试。输出完整可运行的代码。", "timeout": 1200}', NOW()),

  ('990fa328-f03f-4d74-83a4-00008d6b7962', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'frontend_dev',
   '🌐 前端开发', 'agent', 380, 600,
   '{"instruction": "根据技术方案实现前端页面。包括：页面组件、状态管理、API对接、样式。输出完整可运行的代码。", "timeout": 1200}', NOW()),

  ('8f5a033f-6954-4d56-982d-9ed766571729', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'code_review',
   '👀 代码评审（人工审核）', 'hitl', 460, 700,
   '{"instruction": "【审核关卡3】请审核后端和前端代码质量。\n\n请回复：\n✅ 通过 — 代码质量合格，进入测试阶段\n❌ 打回 — 代码有问题，需要重新开发\n💬 有条件通过 — 指出需要修复的问题后继续", "timeout": 1200}', NOW()),

  ('be46d2d9-e8c8-43cc-b004-88be89cbb2e8', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'code_review_check',
   '🔀 代码评审结果', 'router', 460, 800,
   '{"strategy": "llm_select", "candidates": ["backend_dev", "frontend_dev", "integration_test"], "fallback_node_key": "integration_test"}', NOW()),

  -- 阶段4: 测试 → 自动校验 → 部署
  ('7a409814-4b39-4711-aed5-fd23c5aaef12', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'integration_test',
   '🧪 集成测试', 'agent', 250, 900,
   '{"instruction": "对前后端代码进行集成测试。输出：1) 测试用例 2) 执行结果 3) Bug列表 4) 覆盖率报告。", "timeout": 1200}', NOW()),

  ('3857ea25-cfa8-47f9-9510-72bf55c7ce3d', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'test_validation',
   '✅ 测试校验（自动）', 'validation', 250, 1000,
   '{"validator": "test_pass", "criteria": "所有测试必须通过，无FAILED/FAILURES/AssertionError", "on_fail": "reject", "max_retries": 2}', NOW()),

  ('223ad2a1-8954-42f5-a82c-1945e2f2b9eb', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'deploy',
   '🚀 部署发布', 'agent', 250, 1120,
   '{"instruction": "将通过测试的代码部署到生产环境。输出：1) 部署步骤 2) 配置变更 3) 回滚预案 4) 监控配置。", "timeout": 600}', NOW())
ON CONFLICT (id) DO NOTHING;

-- 19条边：15条Forward + 4条Reject（打回路径）
INSERT INTO workflow_edges (id, workflow_id, source_id, target_id, type, created_at) VALUES
  -- === Forward 边（正向流程） ===
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '20ddfd33-2ba9-47ed-bf7c-0924ec2425bf', '894ff415-f485-4a16-89f3-004ba9a35a33', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '894ff415-f485-4a16-89f3-004ba9a35a33', '476f2f3b-4da0-4436-bc68-b5daa8fea616', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '476f2f3b-4da0-4436-bc68-b5daa8fea616', '21fd1bab-0293-47b1-ba4b-c5ca91aab31e', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '21fd1bab-0293-47b1-ba4b-c5ca91aab31e', '0379a95f-cd70-4424-ae7b-684eb3ec02f8', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '0379a95f-cd70-4424-ae7b-684eb3ec02f8', '0a6ae93d-8e47-4643-a873-9d7ed7071834', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '0a6ae93d-8e47-4643-a873-9d7ed7071834', 'b1ec772c-dd90-48d5-b13f-fc98f633d505', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'b1ec772c-dd90-48d5-b13f-fc98f633d505', '8a8bedf0-80f2-43c2-a7bd-fe359845130a', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'b1ec772c-dd90-48d5-b13f-fc98f633d505', '990fa328-f03f-4d74-83a4-00008d6b7962', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '8a8bedf0-80f2-43c2-a7bd-fe359845130a', '8f5a033f-6954-4d56-982d-9ed766571729', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '990fa328-f03f-4d74-83a4-00008d6b7962', '8f5a033f-6954-4d56-982d-9ed766571729', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '8f5a033f-6954-4d56-982d-9ed766571729', 'be46d2d9-e8c8-43cc-b004-88be89cbb2e8', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'be46d2d9-e8c8-43cc-b004-88be89cbb2e8', '7a409814-4b39-4711-aed5-fd23c5aaef12', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '7a409814-4b39-4711-aed5-fd23c5aaef12', '3857ea25-cfa8-47f9-9510-72bf55c7ce3d', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '3857ea25-cfa8-47f9-9510-72bf55c7ce3d', '223ad2a1-8954-42f5-a82c-1945e2f2b9eb', 'forward', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '223ad2a1-8954-42f5-a82c-1945e2f2b9eb', '811aa1f0-f99e-4792-92ca-791d6ba38b96', 'forward', NOW()),

  -- === Reject 边（打回路径，红色虚线） ===
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '21fd1bab-0293-47b1-ba4b-c5ca91aab31e', '894ff415-f485-4a16-89f3-004ba9a35a33', 'reject', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'b1ec772c-dd90-48d5-b13f-fc98f633d505', '0379a95f-cd70-4424-ae7b-684eb3ec02f8', 'reject', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', 'be46d2d9-e8c8-43cc-b004-88be89cbb2e8', '8a8bedf0-80f2-43c2-a7bd-fe359845130a', 'reject', NOW()),
  (gen_random_uuid(), '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', '3857ea25-cfa8-47f9-9510-72bf55c7ce3d', '8a8bedf0-80f2-43c2-a7bd-fe359845130a', 'reject', NOW())
ON CONFLICT DO NOTHING;

-- ════════════════ Team LangGraph 配置 ════════════════

-- 工作流验证团队 绑定新的复杂流程
INSERT INTO team_langgraph_configs (id, team_id, workflow_id, created_at) VALUES
  ('710fc2a1-b6c5-4192-8b01-53787106e5ec', '45cb97fa-f1c9-4063-b9a7-a6bc32971cbf', '62cf6b2b-26b7-4ddd-9454-5100b2dc6750', NOW())
ON CONFLICT (team_id) DO UPDATE SET workflow_id = '62cf6b2b-26b7-4ddd-9454-5100b2dc6750';

-- Node → Agent 绑定（12个可执行节点绑定到对应Agent）
INSERT INTO team_langgraph_node_bindings (id, config_id, node_key, agent_id, created_at) VALUES
  -- 需求分析 → 产品经理
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'requirement_analysis', '1692749d-a00a-4f8e-b8ca-057fbe46ae11', NOW()),
  -- 方案设计 → 架构师
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'solution_design', 'b2acb11b-b867-40cf-966b-c9be77684046', NOW()),
  -- 后端开发 → 后端工程师
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'backend_dev', '58f4721c-3fd4-484e-917e-57c1f382ccdf', NOW()),
  -- 前端开发 → 前端工程师
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'frontend_dev', 'facc3a7c-c310-4c30-88f7-325b83a8867c', NOW()),
  -- 集成测试 → 测试员
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'integration_test', '1af85ade-ce4d-4c1b-9f8d-e5afc0e46bde', NOW()),
  -- 部署发布 → 运维
  (gen_random_uuid(), '710fc2a1-b6c5-4192-8b01-53787106e5ec', 'deploy', '008c5ac7-b5b4-44b0-8cf7-bc78ed8fd6b5', NOW())
ON CONFLICT DO NOTHING;

-- 简单流程的绑定保留（兼容）
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

import { useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { ReactFlowProvider, type Node as ReactFlowNode, type Edge, type OnSelectionChangeFunc } from '@xyflow/react';
import { useSopEditor } from './hooks/useSopEditor';
import { useYamlSync } from './hooks/useYamlSync';
import { Canvas } from './Canvas';
import { NodePanel } from './NodePanel';
import { PropertyPanel } from './PropertyPanel';
import { YamlPreview } from './YamlPreview';
import { Toolbar } from './Toolbar';
import { sopsApi } from '../../shared/api/sops';
import { api } from '../../shared/api/client';
import type { SOPDefinition } from '../../shared/types/sop';

export function SOPDesigner() {
  const { sopId } = useParams<{ sopId?: string }>();
  const [searchParams] = useSearchParams();
  const isFromTeamCreate = searchParams.get('from_team_create') === 'true';
  const teamId = searchParams.get('team_id');

  const editor = useSopEditor();
  const [selectedNode, setSelectedNode] = useState<ReactFlowNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<Edge | null>(null);
  const [loading, setLoading] = useState(false);

  const yamlSync = useYamlSync({
    getSop: editor.toSopDefinition,
    loadSop: editor.loadSop,
  });

  // 从 API 加载 SOP
  useEffect(() => {
    const loadSopById = async (id: string) => {
      setLoading(true);
      sopsApi.get(id)
        .then((sop: SOPDefinition) => {
          editor.loadSop(sop);
          yamlSync.syncToYaml();
        })
        .catch((err) => {
          console.error('Failed to load SOP:', err);
        })
        .finally(() => setLoading(false));
    };

    if (sopId) {
      // 判断来源：/workflows/:id → 用 workflow API，/sop-designer/:id → 用 SOP API
      const isWorkflowRoute = window.location.pathname.startsWith('/workflows/');
      if (isWorkflowRoute) {
        setLoading(true);
        import('../../shared/api/workflows').then(({ workflowApi }) => {
          workflowApi.getDetail(sopId).then((wf) => {
            // 将 workflow 转为 SOP 格式
            const sopDef: SOPDefinition = {
              id: wf.id,
              name: wf.name,
              description: wf.description || '',
              nodes: ((wf as any).nodes || wf.definition?.nodes || []).map((n: any) => ({
                id: n.id,
                type: n.type,
                label: n.label,
                node_key: n.node_key,
                config: n.config || {},
                position: n.position_x != null ? { x: n.position_x, y: n.position_y } : undefined,
              })),
              edges: ((wf as any).edges || wf.definition?.edges || []).map((e: any) => ({
                id: e.id,
                source_id: e.source_id,
                target_id: e.target_id,
                type: e.type,
                condition: e.condition,
              })),
              version: wf.version,
            };
            editor.loadSop(sopDef);
            yamlSync.syncToYaml();
          }).catch((err) => {
            console.error('Failed to load workflow:', err);
          }).finally(() => setLoading(false));
        });
      } else {
        loadSopById(sopId);
      }
    } else if (teamId) {
      // Load team's SOP by team_id
      setLoading(true);
      api.get<SOPDefinition[]>(`/api/v1/sops?team_id=${teamId}`)
        .then((sops) => {
          if (sops && sops.length > 0) {
            const teamSop = sops[0];
            editor.loadSop(teamSop);
            // Update URL to reflect the SOP ID
            window.history.replaceState({}, '', `/sop-designer/${teamSop.id}`);
            yamlSync.syncToYaml();
          } else {
            // No SOP found for this team, create new one
            editor.setName(`团队 ${teamId.slice(0, 8)} 工作流`);
            editor.setWorkflowMode('team_specific');
          }
        })
        .catch((err) => {
          console.error('Failed to load team SOP:', err);
        })
        .finally(() => setLoading(false));
    }
    // Only run on mount when sopId or teamId is present
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sopId, teamId]);

  // 从团队创建流程进入时，设置 workflowMode 和 agents
  useEffect(() => {
    if (!isFromTeamCreate) {
      // 非团队创建模式，加载所有可用 agents
      api.get<Array<{ id: string; name: string }>>('/api/v1/agents')
        .then((allAgents) => {
          editor.setAvailableAgents(allAgents || []);
        })
        .catch(() => {
          console.error('Failed to load agents');
        });
      return;
    }

    // 设置为团队专属模式
    editor.setWorkflowMode('team_specific');

    // 从 sessionStorage 获取选中的 agents
    const savedState = sessionStorage.getItem('team_create_wizard_state');
    if (savedState) {
      try {
        const state = JSON.parse(savedState);
        const selectedAgentIds = state.selected_agents || [];

        // 获取 agents 列表
        api.get<Array<{ id: string; name: string }>>('/api/v1/agents')
          .then((allAgents) => {
            // 只包含选中的 agents
            const selectedAgents = allAgents.filter((a) =>
              selectedAgentIds.includes(a.id)
            );
            editor.setAvailableAgents(selectedAgents);
          })
          .catch(() => {
            console.error('Failed to load agents');
          });
      } catch (e) {
        console.error('Failed to parse saved state:', e);
      }
    }
  }, [isFromTeamCreate, editor]);

  const handleSelectionChange: OnSelectionChangeFunc = useCallback(
    ({ nodes, edges }) => {
      setSelectedNode(nodes.length === 1 ? nodes[0] : null);
      setSelectedEdge(edges.length === 1 ? edges[0] : null);
    },
    []
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      editor.updateNodeData(nodeId, data);
    },
    [editor]
  );

  const handleUpdateEdge = useCallback(
    (edgeId: string, data: Record<string, unknown>) => {
      editor.updateEdgeData(edgeId, data);
    },
    [editor]
  );

  return (
    <ReactFlowProvider>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Toolbar
          name={editor.name}
          onNameChange={editor.setName}
          getSop={editor.toSopDefinition}
          loadSop={(sop) => {
            editor.loadSop(sop);
            yamlSync.syncToYaml();
          }}
          onAutoLayout={editor.doAutoLayout}
          onClear={editor.clearAll}
          onDeleteSelected={editor.deleteSelected}
          syncToYaml={yamlSync.syncToYaml}
          workflowMode={editor.workflowMode}
          onModeChange={(mode) => {
            editor.setWorkflowMode(mode);
          }}
          availableAgents={editor.availableAgents}
          sopId={sopId}
        />

        {loading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
            加载工作流...
          </div>
        ) : (
          <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
            <NodePanel onAddNode={editor.addNode} />

            <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              <Canvas
                nodes={editor.nodes}
                edges={editor.edges}
                onNodesChange={editor.onNodesChange}
                onEdgesChange={editor.onEdgesChange}
                onConnect={editor.onConnect}
                onSelectionChange={handleSelectionChange}
              />

              <YamlPreview
                yaml={yamlSync.yaml}
                errors={yamlSync.errors}
                onChange={yamlSync.onYamlChange}
              />
            </div>

            <PropertyPanel
              node={selectedNode}
              edge={selectedEdge}
              onUpdateNode={handleUpdateNode}
              onUpdateEdge={handleUpdateEdge}
              workflowMode={editor.workflowMode}
              availableAgents={editor.availableAgents}
            />
          </div>
        )}
      </div>
    </ReactFlowProvider>
  );
}

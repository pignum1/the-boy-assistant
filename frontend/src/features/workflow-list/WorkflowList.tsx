/** WorkflowList：工作流列表页面

显示所有工作流，支持创建、编辑、删除操作
*/

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { workflowApi } from '../../shared/api/workflows';
import { Pagination } from '../resources/shared/Pagination';
import type { Workflow } from '../../shared/types/workflow';

export function WorkflowList() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'draft' | 'active'>('all');
  const [showTemplates, setShowTemplates] = useState(false);
  const [page, setPage] = useState(0);
  const [pageSize] = useState(20);
  const [total, setTotal] = useState(0);

  const loadWorkflows = useCallback(async () => {
    try {
      setLoading(true);
      const data = await workflowApi.list({
        status: filter === 'all' ? undefined : filter,
        is_template: showTemplates || undefined,
        skip: page * pageSize,
        limit: pageSize,
      });
      if (Array.isArray(data)) {
        setWorkflows(data);
      } else {
        setWorkflows((data as any).items || []);
        if ((data as any).total !== undefined) setTotal((data as any).total);
      }
    } catch (error) {
      console.error('Failed to load workflows:', error);
    } finally {
      setLoading(false);
    }
  }, [filter, showTemplates, page, pageSize]);

  useEffect(() => {
    loadWorkflows();
  }, [loadWorkflows]);

  const handleCreate = () => {
    navigate('/workflows/new');
  };

  const handleEdit = (id: string) => {
    navigate(`/workflows/${id}`);
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除工作流 "${name}" 吗？`)) {
      return;
    }

    try {
      await workflowApi.delete(id);
      setWorkflows((ws) => ws.filter((w) => w.id !== id));
    } catch (error) {
      console.error('Failed to delete workflow:', error);
      alert('删除失败');
    }
  };

  const handleDuplicate = async (workflow: Workflow) => {
    try {
      const newWorkflow = await workflowApi.create({
        name: `${workflow.name} (副本)`,
        description: workflow.description,
        definition: workflow.definition,
      });
      navigate(`/workflows/${newWorkflow.id}`);
    } catch (error) {
      console.error('Failed to duplicate workflow:', error);
      alert('复制失败');
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return { bg: '#dcfce7', text: '#166534' };
      case 'draft':
        return { bg: '#fef3c7', text: '#92400e' };
      case 'archived':
        return { bg: '#f3f4f6', text: '#374151' };
      default:
        return { bg: '#f3f4f6', text: '#374151' };
    }
  };

  const getStatusLabel = (status: string) => {
    switch (status) {
      case 'active':
        return '活跃';
      case 'draft':
        return '草稿';
      case 'archived':
        return '已归档';
      default:
        return status;
    }
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px' }}>
      {/* 标题和操作栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ margin: 0, fontSize: '28px', fontWeight: '700', color: '#111827' }}>
          工作流管理
        </h1>

        <div style={{ display: 'flex', gap: '12px' }}>
          <button
            onClick={() => setShowTemplates(!showTemplates)}
            style={{
              padding: '10px 16px',
              background: showTemplates ? '#e5e7eb' : '#ffffff',
              border: '1px solid #d1d5db',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#374151',
            }}
          >
            {showTemplates ? '显示全部' : '显示模板'}
          </button>

          <button
            onClick={handleCreate}
            style={{
              padding: '10px 20px',
              background: '#3b82f6',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              color: '#ffffff',
              fontWeight: '500',
            }}
          >
            + 新建工作流
          </button>
        </div>
      </div>

      {/* 筛选器 */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        <button
          onClick={() => setFilter('all')}
          style={{
            padding: '8px 16px',
            background: filter === 'all' ? '#3b82f6' : '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            color: filter === 'all' ? '#ffffff' : '#374151',
          }}
        >
          全部
        </button>
        <button
          onClick={() => setFilter('active')}
          style={{
            padding: '8px 16px',
            background: filter === 'active' ? '#3b82f6' : '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            color: filter === 'active' ? '#ffffff' : '#374151',
          }}
        >
          活跃
        </button>
        <button
          onClick={() => setFilter('draft')}
          style={{
            padding: '8px 16px',
            background: filter === 'draft' ? '#3b82f6' : '#ffffff',
            border: '1px solid #d1d5db',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px',
            color: filter === 'draft' ? '#ffffff' : '#374151',
          }}
        >
          草稿
        </button>
      </div>

      {/* 工作流列表 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
          加载中...
        </div>
      ) : workflows.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '60px 20px',
            background: '#f9fafb',
            borderRadius: '12px',
            border: '2px dashed #e5e7eb',
          }}
        >
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📋</div>
          <div style={{ fontSize: '16px', color: '#6b7280', marginBottom: '16px' }}>
            {showTemplates ? '暂无模板工作流' : '暂无工作流'}
          </div>
          {!showTemplates && (
            <button
              onClick={handleCreate}
              style={{
                padding: '10px 20px',
                background: '#3b82f6',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '14px',
                color: '#ffffff',
              }}
            >
              创建第一个工作流
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '16px' }}>
          {workflows.map((workflow) => {
            const statusColor = getStatusColor(workflow.status);
            const nodeCount = workflow.definition?.nodes?.length || 0;
            const edgeCount = workflow.definition?.edges?.length || 0;

            return (
              <div
                key={workflow.id}
                style={{
                  padding: '20px',
                  background: '#ffffff',
                  border: '1px solid #e5e7eb',
                  borderRadius: '12px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  transition: 'box-shadow 0.2s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)')}
                onMouseLeave={(e) => (e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.05)')}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                      <h3
                        style={{
                          margin: 0,
                          fontSize: '18px',
                          fontWeight: '600',
                          color: '#111827',
                          cursor: 'pointer',
                        }}
                        onClick={() => handleEdit(workflow.id)}
                      >
                        {workflow.name}
                      </h3>

                      <span
                        style={{
                          padding: '4px 10px',
                          background: statusColor.bg,
                          color: statusColor.text,
                          fontSize: '12px',
                          borderRadius: '12px',
                          fontWeight: '500',
                        }}
                      >
                        {getStatusLabel(workflow.status)}
                      </span>

                      {workflow.is_template && (
                        <span
                          style={{
                            padding: '4px 10px',
                            background: '#e0e7ff',
                            color: '#4338ca',
                            fontSize: '12px',
                            borderRadius: '12px',
                            fontWeight: '500',
                          }}
                        >
                          模板
                        </span>
                      )}
                    </div>

                    {workflow.description && (
                      <p style={{ margin: '0 0 12px', fontSize: '14px', color: '#6b7280' }}>
                        {workflow.description}
                      </p>
                    )}

                    <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: '#9ca3af' }}>
                      <span>{nodeCount} 个节点</span>
                      <span>{edgeCount} 条连线</span>
                      <span>版本 {workflow.version}</span>
                      <span>更新于 {new Date(workflow.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                      onClick={() => handleEdit(workflow.id)}
                      style={{
                        padding: '8px 16px',
                        background: '#ffffff',
                        border: '1px solid #d1d5db',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        color: '#374151',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f3f4f6')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '#ffffff')}
                    >
                      编辑
                    </button>

                    <button
                      onClick={() => handleDuplicate(workflow)}
                      style={{
                        padding: '8px 16px',
                        background: '#ffffff',
                        border: '1px solid #d1d5db',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        color: '#374151',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#f3f4f6')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '#ffffff')}
                    >
                      复制
                    </button>

                    <button
                      onClick={() => handleDelete(workflow.id, workflow.name)}
                      style={{
                        padding: '8px 16px',
                        background: '#ffffff',
                        border: '1px solid #fecaca',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        color: '#dc2626',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = '#fef2f2')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = '#ffffff')}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <Pagination
        skip={page * pageSize}
        limit={pageSize}
        total={total}
        onPageChange={(skip) => setPage(Math.floor(skip / pageSize))}
      />
    </div>
  );
}

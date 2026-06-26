import { useState, useEffect, useCallback } from 'react';
import { api } from '../../shared/api/client';

interface Item {
  id: string;
  name: string;
  status: string;
  created_at: string;
}

export function CrudPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Item[]>(`/api/v1/items?page=${page}&keyword=${search}`);
      setItems(data);
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [page, search]);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const handleDelete = async (id: string) => {
    if (!confirm('确认删除？')) return;
    await api.del(`/api/v1/items/${id}`);
    fetchItems();
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center' }}>加载中...</div>;
  if (error) return <div style={{ padding: 40, textAlign: 'center' }}><p>加载失败</p><button onClick={fetchItems}>重试</button></div>;

  return (
    <div style={{ padding: 28 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>数据管理</h1>
      <div style={{ display: 'flex', gap: 10, margin: '16px 0' }}>
        <input placeholder="搜索..." value={search} onChange={(e) => setSearch(e.target.value)} style={{ flex: 1, maxWidth: 360, padding: 8 }} />
        <button onClick={() => {/* open create panel */}}>+ 新增</button>
      </div>
      {items.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60 }}>暂无数据</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th>名称</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.status}</td>
                <td>{item.created_at}</td>
                <td>
                  <button onClick={() => handleDelete(item.id)}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

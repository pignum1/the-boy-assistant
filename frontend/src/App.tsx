import { BrowserRouter, Routes, Route, useSearchParams } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { Layout } from './components/Layout';
import { Dashboard } from './features/dashboard';
import { ChatRoomIndex } from './features/chatroom/ChatRoomIndex';
import { ModelsPage } from './features/resources/ModelsPage';
import { MCPServersPage } from './features/resources/MCPServersPage';
import { SkillsPage } from './features/resources/SkillsPage';
import { PersonasPage } from './features/resources/PersonasPage';
import { AgentsPage } from './features/resources/AgentsPage';
import { Tasks } from './features/tasks';
import { Teams } from './features/teams';
import { WorkflowList } from './features/workflow-list';

// 代码分割：延迟加载大型路由组件
const SOPDesigner = lazy(() => import('./features/sop-designer').then(m => ({ default: m.SOPDesigner })));

/** 代码分割加载占位 */
function PageLoader() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100%', color: 'var(--text-muted)', fontSize: 14,
    }}>
      <span>⏳ 加载中...</span>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sop-designer" element={<Suspense fallback={<PageLoader />}><SOPDesigner /></Suspense>} />
          <Route path="/sop-designer/:sopId" element={<Suspense fallback={<PageLoader />}><SOPDesigner /></Suspense>} />
          <Route path="/chat" element={<ChatRoomRoute />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/teams" element={<Teams />} />
          <Route path="/workflows" element={<WorkflowList />} />
          <Route path="/workflows/:sopId" element={<Suspense fallback={<PageLoader />}><SOPDesigner /></Suspense>} />
          <Route path="/resources/models" element={<ModelsPage />} />
          <Route path="/resources/mcp-servers" element={<MCPServersPage />} />
          <Route path="/resources/skills" element={<SkillsPage />} />
          <Route path="/resources/personas" element={<PersonasPage />} />
          <Route path="/resources/agents" element={<AgentsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

/** ChatRoom 路由组件：从 URL 参数读取 session + team */
function ChatRoomRoute() {
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session');
  const teamId = searchParams.get('team');

  if (!sessionId || !teamId) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: 'var(--text-muted)', gap: 16, position: 'relative', zIndex: 1,
      }}>
        <div style={{ fontSize: 48 }}>💬</div>
        <div style={{ fontSize: 16, fontWeight: 600 }}>未指定会话或团队</div>
        <div style={{ fontSize: 13 }}>请从工作台或团队页面开始新对话</div>
        <a href="/" style={{
          padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 500,
          background: 'linear-gradient(135deg, var(--gold-500), #d97706)',
          color: '#0a0f1e', textDecoration: 'none',
        }}>
          返回工作台
        </a>
      </div>
    );
  }

  return <ChatRoomIndex sessionId={sessionId} teamId={teamId} />;
}

export default App;

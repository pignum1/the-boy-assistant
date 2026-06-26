import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function Layout() {
  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg-deep)' }}>
      <Sidebar />
      <main
        style={{
          flex: 1,
          overflowY: 'auto',
          background: [
            'radial-gradient(ellipse at 20% 0%, rgba(245,158,11,0.03) 0%, transparent 50%)',
            'radial-gradient(ellipse at 80% 100%, rgba(56,189,248,0.02) 0%, transparent 50%)',
            'var(--bg-deep)',
          ].join(', '),
          position: 'relative',
        }}
      >
        {/* Grid overlay */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: [
              'linear-gradient(var(--border-subtle) 1px, transparent 1px)',
              'linear-gradient(90deg, var(--border-subtle) 1px, transparent 1px)',
            ].join(', '),
            backgroundSize: '60px 60px',
            opacity: 0.4,
            pointerEvents: 'none',
          }}
        />
        <Outlet />
      </main>
    </div>
  );
}

/**
 * App.tsx — 路由定义 + 全局布局外壳
 *
 * 页面结构（V1.1，组合管理合并进仪表盘后）：
 *   /login          → Login.tsx
 *   /               → Dashboard.tsx  ← 含组合管理（增删组合/股票）
 *   /stock/:mkt/:code → StockDetail.tsx
 *   /accuracy       → Accuracy.tsx
 *
 * 侧边栏导航：仪表盘 / 预测准确率（2项，去掉独立的「我的组合」）
 *
 * 修改指南：
 *   加新页面 → 1) 在 src/pages/ 新建 .tsx  2) 这里加 Route  3) 这里加导航项
 *   改全局样式 → src/index.css 的 CSS 变量
 *   改认证逻辑 → isAuthed() 函数 + api.ts 的 authApi
 */
import { BrowserRouter, Routes, Route, Navigate, NavLink, useNavigate } from 'react-router-dom'
import Dashboard  from './pages/Dashboard'
import StockDetail from './pages/StockDetail'
import Accuracy   from './pages/Accuracy'
import Login      from './pages/Login'
import './index.css'

function isAuthed() { return !!localStorage.getItem('token') }

function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const userName = localStorage.getItem('user_name') || '用户'

  function logout() { localStorage.clear(); navigate('/login') }

  const navItems = [
    { to: '/',          label: '仪表盘',    icon: '⊞' },
    { to: '/accuracy',  label: '预测准确率', icon: '◎' },
  ]

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* ── 侧边栏 ── */}
      <aside style={{
        width: 216, background: 'var(--bg2)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
      }}>
        <div style={{ padding: '22px 20px 18px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent2)', letterSpacing: '-0.5px' }}>
            AI投资助手
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>量化辅助决策 V1.1</div>
        </div>

        <nav style={{ flex: 1, padding: '14px 10px', display: 'flex', flexDirection: 'column', gap: 3 }}>
          {navItems.map(item => (
            <NavLink key={item.to} to={item.to} end={item.to === '/'} style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '9px 12px', borderRadius: 8,
              textDecoration: 'none', fontSize: 14, fontWeight: 500,
              color:      isActive ? 'var(--accent2)' : 'var(--muted)',
              background: isActive ? 'rgba(99,102,241,0.12)' : 'transparent',
              transition: 'all 0.15s',
            })}>
              <span style={{ fontSize: 16 }}>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div style={{
          padding: '14px 18px',
          borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>{userName}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)' }}>家庭账户</div>
          </div>
          <button onClick={logout} style={{
            background: 'none', border: '1px solid var(--border)',
            borderRadius: 6, color: 'var(--muted)',
            padding: '4px 9px', cursor: 'pointer', fontSize: 11,
          }}>退出</button>
        </div>
      </aside>

      {/* ── 主内容区 ── */}
      <main style={{ flex: 1, overflow: 'auto', background: 'var(--bg)' }}>
        {children}
      </main>
    </div>
  )
}

function Protected({ children }: { children: React.ReactNode }) {
  if (!isAuthed()) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><Dashboard /></Protected>} />
        <Route path="/stock/:market/:code" element={<Protected><StockDetail /></Protected>} />
        <Route path="/accuracy" element={<Protected><Accuracy /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

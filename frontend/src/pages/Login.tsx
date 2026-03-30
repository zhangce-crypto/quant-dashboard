/**
 * Login.tsx — 登录/注册页
 * 关联：认证成功后 navigate('/') 进入 Dashboard
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../lib/api'

export default function Login() {
  const navigate = useNavigate()
  const [mode, setMode]   = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [name,  setName]  = useState('')
  const [pw,    setPw]    = useState('')
  const [err,   setErr]   = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(''); setLoading(true)
    try {
      const res = mode === 'login'
        ? await authApi.login(email, pw)
        : await authApi.register(email, name, pw)
      localStorage.setItem('token',     res.data.access_token)
      localStorage.setItem('user_name', res.data.user_name)
      navigate('/')
    } catch (e: any) {
      setErr(e.response?.data?.detail || '操作失败，请重试')
    } finally { setLoading(false) }
  }

  const INP: React.CSSProperties = {
    width: '100%', padding: '11px 14px', marginBottom: 12,
    background: 'var(--bg3)', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', fontSize: 14, outline: 'none',
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ width: 380 }}>
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{ fontSize: 30, fontWeight: 700, color: 'var(--accent2)', marginBottom: 8 }}>AI投资助手</div>
          <div style={{ color: 'var(--muted)', fontSize: 14 }}>量化辅助决策，让投资有据可依</div>
        </div>

        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '28px 30px' }}>
          <div style={{ display: 'flex', gap: 4, marginBottom: 24, background: 'var(--bg3)', borderRadius: 8, padding: 4 }}>
            {(['login', 'register'] as const).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{
                flex: 1, padding: '8px 0', border: 'none', borderRadius: 6,
                cursor: 'pointer', fontSize: 14, fontWeight: 500,
                background: mode === m ? 'var(--accent)' : 'transparent',
                color: mode === m ? '#fff' : 'var(--muted)',
                transition: 'all .15s',
              }}>{m === 'login' ? '登录' : '注册'}</button>
            ))}
          </div>

          <form onSubmit={submit}>
            {mode === 'register' && (
              <input style={INP} placeholder="昵称" value={name} onChange={e => setName(e.target.value)} required />
            )}
            <input style={INP} type="email" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)} required />
            <input style={INP} type="password" placeholder="密码" value={pw} onChange={e => setPw(e.target.value)} required />

            {err && <div style={{ color: 'var(--down)', fontSize: 13, marginBottom: 12 }}>{err}</div>}

            <button type="submit" disabled={loading} style={{
              width: '100%', padding: '12px', background: 'var(--accent)',
              border: 'none', borderRadius: 8, color: '#fff', fontSize: 15, fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? .7 : 1,
            }}>{loading ? '请稍候...' : mode === 'login' ? '登录' : '注册'}</button>
          </form>
        </div>

        <div style={{ textAlign: 'center', marginTop: 20, color: 'var(--muted)', fontSize: 12 }}>
          所有预测仅供参考，不构成投资建议。股市有风险，投资需谨慎。
        </div>
      </div>
    </div>
  )
}

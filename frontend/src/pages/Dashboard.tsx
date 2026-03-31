/**
 * Dashboard.tsx — 仪表盘 V2.0
 * 改动：评分轮询、T+1/T+3列、搜索防抖、组合选择器、空状态引导、spinner替代"计算中"
 */
import { useEffect, useState, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { portfolioApi, marketApi } from '../lib/api'

type Portfolio   = { id: string; name: string; description: string }
type StockRow    = {
  id: string; code: string; name: string; market: string; tag: string
  price?: number; change_pct?: number; change_amt?: number
  total_score?: number; signal?: string; signal_strength?: number
  cost_price?: number; shares?: number; profit_pct?: number
  t1_prob_up?: number; t3_prob_up?: number
  t1_range_low?: number; t1_range_high?: number
  t3_range_low?: number; t3_range_high?: number
}
type SearchResult = { code: string; name: string; market: string }

function ScoreRing({ score }: { score?: number }) {
  if (score == null) return (
    <div style={{ width: 44, height: 44, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span className="spinner" />
    </div>
  )
  const color = score >= 65 ? 'var(--up)' : score <= 40 ? 'var(--down)' : 'var(--neutral)'
  const r = 18, circ = 2 * Math.PI * r
  return (
    <svg width={44} height={44} viewBox="0 0 44 44">
      <circle cx={22} cy={22} r={r} fill="none" stroke="var(--border)" strokeWidth={3} />
      <circle cx={22} cy={22} r={r} fill="none" stroke={color} strokeWidth={3}
        strokeLinecap="round" strokeDasharray={`${score / 100 * circ} ${circ}`}
        transform="rotate(-90 22 22)" style={{ transition: 'stroke-dasharray 0.5s' }} />
      <text x={22} y={26} textAnchor="middle" fontSize={11} fontWeight={600}
        fill={color} fontFamily="DM Mono, monospace">{Math.round(score)}</text>
    </svg>
  )
}

function SignalBadge({ signal, strength }: { signal?: string; strength?: number }) {
  if (!signal) return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><span className="spinner" /><span style={{ color: 'var(--muted)', fontSize: 11 }}>计算中</span></span>
  const MAP: Record<string, { color: string; label: string }> = {
    up: { color: 'var(--up)', label: '偏多' }, neutral: { color: 'var(--neutral)', label: '中性' }, down: { color: 'var(--down)', label: '偏空' },
  }
  const { color, label } = MAP[signal] || MAP.neutral
  const stars = '★'.repeat(strength || 1) + '☆'.repeat(5 - (strength || 1))
  return <span style={{ color, fontSize: 11, fontFamily: 'DM Mono, monospace' }}>{label} {stars}</span>
}

function ProbCell({ prob }: { prob?: number }) {
  if (prob == null) return <span style={{ color: 'var(--muted)', fontSize: 11 }}>—</span>
  const pct = Math.round(prob * 100)
  const color = pct >= 55 ? 'var(--up)' : pct <= 45 ? 'var(--down)' : 'var(--neutral)'
  return <span style={{ color, fontSize: 12, fontWeight: 500, fontFamily: 'DM Mono, monospace' }}>{pct}%</span>
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [portfolios, setPortfolios] = useState<Portfolio[]>([])
  const [curPortId, setCurPortId] = useState('')
  const [stocks, setStocks] = useState<StockRow[]>([])
  const [indices, setIndices] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showNewPort, setShowNewPort] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [searchMkt, setSearchMkt] = useState<'A'|'HK'>('A')
  const [searchRes, setSearchRes] = useState<SearchResult[]>([])
  const [picked, setPicked] = useState<SearchResult | null>(null)
  const [costPrice, setCostPrice] = useState('')
  const [sharesQty, setSharesQty] = useState('')
  const [searching, setSearching] = useState(false)
  const [adding, setAdding] = useState(false)
  const [newPortName, setNewPortName] = useState('')
  const [creating, setCreating] = useState(false)
  const [addToPortId, setAddToPortId] = useState('')

  const portNameRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<any>(null)

  useEffect(() => {
    portfolioApi.list().then(r => {
      setPortfolios(r.data)
      if (r.data.length > 0) { setCurPortId(r.data[0].id); setAddToPortId(r.data[0].id) }
    }).catch(() => {})
  }, [])

  const loadQuotes = useCallback(() => {
    if (!curPortId) return
    setLoading(true)
    marketApi.quotes(curPortId).then(r => {
      setStocks(r.data.stocks || [])
      setIndices(r.data.index || {})
    }).catch(() => {}).finally(() => setLoading(false))
  }, [curPortId])

  useEffect(() => { loadQuotes() }, [loadQuotes])

  // V2.0: 轮询 - 如果有股票无评分，每15秒刷新一次
  useEffect(() => {
    const hasNoScore = stocks.some(s => s.signal == null)
    if (!hasNoScore || !curPortId) return
    const timer = setInterval(() => {
      marketApi.quotes(curPortId).then(r => {
        setStocks(r.data.stocks || [])
        setIndices(r.data.index || {})
      }).catch(() => {})
    }, 15000)
    const timeout = setTimeout(() => clearInterval(timer), 180000) // 3分钟超时
    return () => { clearInterval(timer); clearTimeout(timeout) }
  }, [stocks, curPortId])

  const curPort = portfolios.find(p => p.id === curPortId)

  // V2.0: 搜索防抖
  useEffect(() => {
    if (!searchQ.trim() || searchQ.trim().length < 1) { setSearchRes([]); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setSearching(true)
      try {
        const r = await marketApi.search(searchQ.trim(), searchMkt)
        setSearchRes(r.data)
      } catch {} finally { setSearching(false) }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [searchQ, searchMkt])

  async function deletePortfolio(pid: string, e: React.MouseEvent) {
    e.stopPropagation()
    const p = portfolios.find(x => x.id === pid)
    if (!confirm(`确认删除「${p?.name}」？组合内股票记录也将删除。`)) return
    try {
      await portfolioApi.delete(pid)
      const rest = portfolios.filter(x => x.id !== pid)
      setPortfolios(rest)
      if (curPortId === pid) { setCurPortId(rest[0]?.id || ''); if (!rest.length) setStocks([]) }
    } catch (err: any) { alert(err.response?.data?.detail || '删除失败') }
  }

  async function createPortfolio() {
    if (!newPortName.trim()) return
    setCreating(true)
    try {
      await portfolioApi.create(newPortName.trim())
      const r = await portfolioApi.list()
      setPortfolios(r.data)
      const newP = r.data[r.data.length - 1]
      setCurPortId(newP?.id || '')
      setAddToPortId(newP?.id || '')
      setNewPortName(''); setShowNewPort(false)
    } catch (err: any) { alert(err.response?.data?.detail || '创建失败') }
    finally { setCreating(false) }
  }

  async function removeStock(sid: string, sname: string) {
    if (!confirm(`确认从「${curPort?.name}」移除「${sname}」？`)) return
    try {
      await portfolioApi.removeStock(curPortId, sid)
      setStocks(prev => prev.filter(s => s.id !== sid))
    } catch (err: any) { alert(err.response?.data?.detail || '移除失败') }
  }

  async function addStock() {
    if (!picked || !addToPortId) return
    setAdding(true)
    try {
      await portfolioApi.addStock(addToPortId, {
        code: picked.code, name: picked.name, market: picked.market,
        cost_price: costPrice ? parseFloat(costPrice) : null,
        shares: sharesQty ? parseFloat(sharesQty) : null, tag: '',
      })
      setShowAdd(false); resetAdd()
      if (addToPortId === curPortId) loadQuotes()
    } catch (err: any) { alert(err.response?.data?.detail || '添加失败') }
    finally { setAdding(false) }
  }

  function resetAdd() {
    setSearchQ(''); setSearchRes([]); setPicked(null); setCostPrice(''); setSharesQty('')
  }

  const INP: React.CSSProperties = {
    width: '100%', padding: '10px 13px', background: 'var(--bg3)', border: '1px solid var(--border)',
    borderRadius: 8, color: 'var(--text)', fontSize: 14, outline: 'none', marginBottom: 10,
  }
  const COL = '48px 1fr 68px 82px 72px 120px 60px 60px 72px 100px'

  return (
    <div style={{ padding: '26px 30px' }}>
      <div style={{ marginBottom: 18 }}>
        <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>仪表盘</h1>
        <div style={{ color: 'var(--muted)', fontSize: 12 }}>所有信号仅供参考，不构成投资建议</div>
      </div>

      {/* 大盘指数 */}
      {Object.keys(indices).length > 0 && (
        <div style={{ display: 'flex', gap: 24, padding: '10px 18px', background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, marginBottom: 16, flexWrap: 'wrap' }}>
          {[
            { key: 'sh000001', label: '上证指数' }, { key: 'sh000300', label: '沪深300' },
            { key: 'sz399001', label: '深证成指' }, { key: 'hkHSI', label: '恒生指数' },
          ].map(({ key, label }) => {
            const d = indices[key]; if (!d) return null
            const up = (d.change_pct ?? 0) >= 0
            return (
              <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</span>
                <span style={{ fontSize: 14, fontWeight: 500, fontFamily: 'monospace' }}>{d.price?.toFixed(2)}</span>
                <span style={{ fontSize: 11, fontFamily: 'monospace', color: up ? 'var(--up)' : 'var(--down)' }}>
                  {up ? '+' : ''}{d.change_pct?.toFixed(2)}%
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* 组合标签 + 操作按钮 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 7, flex: 1, flexWrap: 'wrap' }}>
          {portfolios.map(p => (
            <div key={p.id} style={{
              display: 'flex', alignItems: 'stretch',
              border: `1px solid ${p.id === curPortId ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 8, overflow: 'hidden', transition: 'border-color .15s',
            }}>
              <button onClick={() => setCurPortId(p.id)} style={{
                padding: '7px 13px', background: p.id === curPortId ? 'rgba(99,102,241,.12)' : 'transparent',
                border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 500,
                color: p.id === curPortId ? 'var(--accent2)' : 'var(--muted)',
              }}>{p.name}</button>
              <button onClick={e => deletePortfolio(p.id, e)} title="删除此组合" style={{
                padding: '7px 9px', background: 'transparent', border: 'none',
                borderLeft: '1px solid var(--border)', color: 'var(--muted)', cursor: 'pointer', fontSize: 14, lineHeight: 1,
              }} onMouseEnter={e => { e.currentTarget.style.color = 'var(--down)'; e.currentTarget.style.background = 'rgba(239,68,68,.1)' }}
                 onMouseLeave={e => { e.currentTarget.style.color = 'var(--muted)'; e.currentTarget.style.background = 'transparent' }}
              >×</button>
            </div>
          ))}
          {portfolios.length === 0 && <span style={{ fontSize: 13, color: 'var(--muted)', alignSelf: 'center' }}>暂无组合</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button onClick={() => { setShowAdd(true); if (portfolios.length > 0) setAddToPortId(curPortId || portfolios[0].id) }} style={{
            padding: '7px 15px', background: 'transparent', border: '1px solid var(--accent)', borderRadius: 8,
            color: 'var(--accent2)', cursor: 'pointer', fontSize: 13,
          }}>+ 添加股票</button>
          <button onClick={() => { setShowNewPort(true); setTimeout(() => portNameRef.current?.focus(), 80) }} style={{
            padding: '7px 15px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 8,
            color: 'var(--muted)', cursor: 'pointer', fontSize: 13,
          }}>+ 新建组合</button>
        </div>
      </div>

      {/* 股票列表 */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: COL, padding: '11px 16px', borderBottom: '1px solid var(--border)' }}>
          {['评分','股票','市场','最新价','涨跌幅','今日信号','T+1','T+3','持仓盈亏','操作'].map(h => (
            <div key={h} style={{ fontSize: 12, color: 'var(--muted)' }}>{h}</div>
          ))}
        </div>

        {loading ? (
          <div style={{ padding: 48, textAlign: 'center', color: 'var(--muted)' }}>加载中...</div>
        ) : !curPortId && portfolios.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)' }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>◫</div>
            <div style={{ marginBottom: 16 }}>搜索并添加你的第一只股票</div>
            <button onClick={() => setShowAdd(true)} style={{
              padding: '8px 20px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: '#fff', cursor: 'pointer', fontSize: 14,
            }}>+ 添加股票</button>
          </div>
        ) : stocks.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)' }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>◫</div>
            <div style={{ marginBottom: 16 }}>「{curPort?.name}」暂无股票</div>
            <button onClick={() => setShowAdd(true)} style={{
              padding: '8px 20px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: '#fff', cursor: 'pointer', fontSize: 14,
            }}>+ 添加股票</button>
          </div>
        ) : stocks.map((s, i) => {
          const up = (s.change_pct ?? 0) >= 0
          return (
            <div key={s.id} style={{
              display: 'grid', gridTemplateColumns: COL, padding: '11px 16px',
              borderBottom: i < stocks.length - 1 ? '1px solid var(--border)' : 'none',
              alignItems: 'center', cursor: 'pointer', transition: 'background .1s',
            }} onClick={() => navigate(`/stock/${s.market}/${s.code}`)}
               onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg3)')}
               onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
              <div onClick={e => e.stopPropagation()}><ScoreRing score={s.total_score} /></div>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2, fontFamily: 'monospace' }}>{s.code}</div>
              </div>
              <div>
                <span style={{
                  padding: '2px 8px', borderRadius: 4, fontSize: 11,
                  background: s.market === 'HK' ? 'rgba(139,92,246,.15)' : 'rgba(99,102,241,.15)',
                  color: s.market === 'HK' ? '#a78bfa' : 'var(--accent2)',
                }}>{s.market === 'HK' ? '港股通' : 'A股'}</span>
              </div>
              <div style={{ fontSize: 15, fontWeight: 500, fontFamily: 'monospace' }}>{s.price?.toFixed(2) ?? '—'}</div>
              <div style={{ color: up ? 'var(--up)' : 'var(--down)', fontSize: 13, fontWeight: 500, fontFamily: 'monospace' }}>
                {s.change_pct != null ? `${up ? '+' : ''}${s.change_pct.toFixed(2)}%` : '—'}
              </div>
              <div><SignalBadge signal={s.signal} strength={s.signal_strength} /></div>
              <div><ProbCell prob={s.t1_prob_up} /></div>
              <div><ProbCell prob={s.t3_prob_up} /></div>
              <div>
                {s.profit_pct != null
                  ? <span style={{ color: s.profit_pct >= 0 ? 'var(--up)' : 'var(--down)', fontSize: 13, fontFamily: 'monospace' }}>
                      {s.profit_pct >= 0 ? '+' : ''}{s.profit_pct.toFixed(2)}%
                    </span>
                  : <span style={{ color: 'var(--muted)' }}>—</span>}
              </div>
              <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
                <button onClick={() => navigate(`/stock/${s.market}/${s.code}`)} style={{
                  padding: '4px 10px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 6,
                  color: 'var(--muted)', cursor: 'pointer', fontSize: 12,
                }}>详情</button>
                <button onClick={() => removeStock(s.id, s.name)} style={{
                  padding: '4px 10px', background: 'transparent', border: '1px solid rgba(239,68,68,.4)', borderRadius: 6,
                  color: 'var(--down)', cursor: 'pointer', fontSize: 12,
                }}>移除</button>
              </div>
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 12, fontSize: 11, color: 'var(--muted)', textAlign: 'right' }}>
        行情延迟约3-5分钟 · 数据来源：新浪财经、AKShare · 仅为量化参考信号
      </div>

      {/* ══ 添加股票弹窗 V2.0: 带组合选择器 ══ */}
      {showAdd && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}
          onClick={() => { setShowAdd(false); resetAdd() }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '24px 28px', width: 460 }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>添加股票</div>
              <button onClick={() => { setShowAdd(false); resetAdd() }} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 22 }}>×</button>
            </div>

            {/* V2.0: 组合选择器 */}
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>添加到组合</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <select value={addToPortId} onChange={e => setAddToPortId(e.target.value)} style={{
                  ...INP, flex: 1, marginBottom: 0, cursor: 'pointer',
                }}>
                  {portfolios.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button onClick={() => { setShowNewPort(true); setTimeout(() => portNameRef.current?.focus(), 80) }} style={{
                  padding: '10px 14px', background: 'var(--bg3)', border: '1px solid var(--border)',
                  borderRadius: 8, color: 'var(--accent2)', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap',
                }}>+ 新建</button>
              </div>
            </div>

            {/* 市场切换 */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              {(['A', 'HK'] as const).map(m => (
                <button key={m} onClick={() => { setSearchMkt(m); setSearchRes([]); setPicked(null); setSearchQ('') }} style={{
                  flex: 1, padding: '8px 0', border: '1px solid',
                  borderColor: searchMkt === m ? 'var(--accent)' : 'var(--border)', borderRadius: 8,
                  background: searchMkt === m ? 'rgba(99,102,241,.12)' : 'transparent',
                  color: searchMkt === m ? 'var(--accent2)' : 'var(--muted)', cursor: 'pointer', fontSize: 13, fontWeight: 500,
                }}>{m === 'A' ? 'A股（沪深）' : '港股通'}</button>
              ))}
            </div>

            {/* 搜索 - V2.0: 实时搜索，无需按钮 */}
            {!picked && (
              <>
                <div style={{ position: 'relative', marginBottom: 10 }}>
                  <input style={{ ...INP, marginBottom: 0 }}
                    placeholder={searchMkt === 'A' ? '输入代码或名称，如 600519 / 茅台' : '输入港股代码，如 00700'}
                    value={searchQ} onChange={e => setSearchQ(e.target.value)} autoFocus />
                  {searching && <span className="spinner" style={{ position: 'absolute', right: 12, top: 12 }} />}
                </div>
                {searchRes.length > 0 && (
                  <div style={{ border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', marginBottom: 12, maxHeight: 240, overflowY: 'auto' }}>
                    {searchRes.map((r, i) => (
                      <div key={r.code} onClick={() => setPicked(r)} style={{
                        padding: '10px 14px', cursor: 'pointer', display: 'flex',
                        justifyContent: 'space-between', alignItems: 'center',
                        borderBottom: i < searchRes.length - 1 ? '1px solid var(--border)' : 'none', background: 'var(--bg3)',
                      }} onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg2)')}
                         onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg3)')}>
                        <div>
                          <span style={{ fontWeight: 500 }}>{r.name}</span>
                          <span style={{ color: 'var(--muted)', fontSize: 12, marginLeft: 10, fontFamily: 'monospace' }}>{r.code}</span>
                        </div>
                        <span style={{ color: 'var(--accent2)', fontSize: 12 }}>选择 →</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
            {picked && (
              <div style={{
                padding: '11px 14px', background: 'rgba(99,102,241,.1)',
                border: '1px solid var(--accent)', borderRadius: 8,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12,
              }}>
                <div>
                  <span style={{ fontWeight: 600 }}>{picked.name}</span>
                  <span style={{ color: 'var(--muted)', fontSize: 12, marginLeft: 10, fontFamily: 'monospace' }}>{picked.code}</span>
                </div>
                <button onClick={() => setPicked(null)} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 20 }}>×</button>
              </div>
            )}
            <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>持仓信息（可选）</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
              <input style={{ ...INP, marginBottom: 0 }} type="number" placeholder="买入成本价（元）"
                value={costPrice} onChange={e => setCostPrice(e.target.value)} />
              <input style={{ ...INP, marginBottom: 0 }} type="number" placeholder="持股数量（股）"
                value={sharesQty} onChange={e => setSharesQty(e.target.value)} />
            </div>
            <button onClick={addStock} disabled={!picked || adding || !addToPortId} style={{
              width: '100%', padding: '11px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: '#fff', cursor: picked && !adding ? 'pointer' : 'not-allowed',
              fontSize: 14, fontWeight: 500, opacity: picked && !adding ? 1 : .5,
            }}>{adding ? '添加中...' : `添加到「${portfolios.find(p => p.id === addToPortId)?.name || ''}」`}</button>
          </div>
        </div>
      )}

      {/* ══ 新建组合弹窗 ══ */}
      {showNewPort && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 101 }}
          onClick={() => { setShowNewPort(false); setNewPortName('') }}>
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 12, padding: '24px 28px', width: 360 }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>新建组合</div>
              <button onClick={() => { setShowNewPort(false); setNewPortName('') }} style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 22 }}>×</button>
            </div>
            <input ref={portNameRef} style={INP} placeholder="组合名称，如：我的A股、妻子A股"
              value={newPortName} onChange={e => setNewPortName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && createPortfolio()} />
            <button onClick={createPortfolio} disabled={!newPortName.trim() || creating} style={{
              width: '100%', padding: '11px', background: 'var(--accent)', border: 'none',
              borderRadius: 8, color: '#fff', cursor: newPortName.trim() && !creating ? 'pointer' : 'not-allowed',
              fontSize: 14, fontWeight: 500, opacity: newPortName.trim() && !creating ? 1 : .5,
            }}>{creating ? '创建中...' : '创建组合'}</button>
          </div>
        </div>
      )}
    </div>
  )
}

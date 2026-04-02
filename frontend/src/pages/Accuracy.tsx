/**
 * Accuracy.tsx — 预测准确率页 V2.0
 * 补全：个股准确率表、分市场/分信号强度统计
 */
import React, { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { accuracyApi } from '../lib/api'

type Summary = {
  overall_accuracy: number | null; baseline: number; beat_baseline: number | null
  total_predictions: number; correct_predictions: number
  by_horizon: Record<string, { accuracy: number | null; count: number; beat_baseline: number | null }>
  monthly_trend: { month: string; accuracy: number | null; count: number; baseline: number }[]
}
type StockAcc = {
  code: string; market: string; name: string; total: number; correct: number
  accuracy: number | null; t1_accuracy: number | null; t1_total: number
  t3_accuracy: number | null; t3_total: number; beat_baseline: number | null
}
type CategoryData = {
  by_market: { market: string; total: number; correct: number; accuracy: number | null }[]
  by_strength: { strength: number; total: number; correct: number; accuracy: number | null }[]
}
type StockHistory = {
  predict_date: string; horizon: string; direction: string; prob_up: number
  pred_range_low: number; pred_range_high: number; is_correct: boolean | null
  actual_direction: string | null; actual_change_pct: number | null
  settled_at: string | null; ai_summary: string
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '14px 18px' }}>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 7 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, fontFamily: 'monospace', color: color || 'var(--text)' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 5 }}>{sub}</div>}
    </div>
  )
}

function AccBar({ label, accuracy, count }: { label: string; accuracy: number | null; count: number }) {
  const pct = accuracy != null ? accuracy * 100 : 0
  const color = pct >= 55 ? 'var(--up)' : pct >= 50 ? 'var(--neutral)' : 'var(--down)'
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
        <span style={{ color: 'var(--muted)' }}>{label}</span>
        <span style={{ color, fontWeight: 600, fontFamily: 'monospace' }}>{accuracy != null ? `${pct.toFixed(1)}%` : 'N/A'}</span>
      </div>
      <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${Math.min(pct, 100)}%`, background: color, borderRadius: 3, transition: 'width .6s' }} />
      </div>
      <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{count} 条样本</div>
    </div>
  )
}

export default function Accuracy() {
  const [data, setData] = useState<Summary | null>(null)
  const [stockAccs, setStockAccs] = useState<StockAcc[]>([])
  const [catData, setCatData] = useState<CategoryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedCode, setExpandedCode] = useState<string | null>(null)
  const [stockHistory, setStockHistory] = useState<StockHistory[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)

  useEffect(() => {
    Promise.all([
      accuracyApi.summary(),
      accuracyApi.byStock().catch(() => ({ data: [] })),
      accuracyApi.byCategory().catch(() => ({ data: { by_market: [], by_strength: [] } })),
    ]).then(([sumRes, stockRes, catRes]) => {
      setData(sumRes.data)
      setStockAccs(stockRes.data || [])
      setCatData(catRes.data)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  async function toggleStockDetail(code: string) {
    if (expandedCode === code) { setExpandedCode(null); return }
    setExpandedCode(code); setLoadingHistory(true)
    try { const r = await accuracyApi.history(code); setStockHistory(r.data) }
    catch {} finally { setLoadingHistory(false) }
  }

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)' }}><span className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} /><div style={{ marginTop: 12 }}>加载中...</div></div>

  if (!data || data.total_predictions === 0) return (
    <div style={{ padding: '26px 30px' }}>
      <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 6 }}>预测准确率</h1>
      <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 32 }}>对比模型预测与实际涨跌，验证量化信号有效性</div>
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '80px 0', textAlign: 'center', color: 'var(--muted)' }}>
        <div style={{ fontSize: 36, marginBottom: 16 }}>◎</div>
        <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 12 }}>暂无预测记录</div>
        <div style={{ fontSize: 14, maxWidth: 400, margin: '0 auto', lineHeight: 1.8 }}>在「仪表盘」添加股票后，系统会自动生成预测。预测到期后自动核对，准确率将在此展示。</div>
      </div>
    </div>
  )

  const overallPct = data.overall_accuracy != null ? (data.overall_accuracy * 100).toFixed(1) : 'N/A'
  const ringR = 52, ringCirc = 2 * Math.PI * ringR
  const ringArc = data.overall_accuracy != null ? data.overall_accuracy * ringCirc : 0

  const trendOpt = {
    backgroundColor: 'transparent',
    grid: { left: 44, right: 14, top: 16, bottom: 36 },
    xAxis: { type: 'category' as const, data: data.monthly_trend.map(t => t.month),
      axisLabel: { color: '#64748b', fontSize: 11 }, axisLine: { lineStyle: { color: '#252936' } } },
    yAxis: { type: 'value' as const, min: 40, max: 70,
      axisLabel: { color: '#64748b', fontSize: 11, formatter: (v: number) => v + '%' },
      splitLine: { lineStyle: { color: '#252936' } } },
    series: [
      { type: 'line' as const, name: '基准50%', data: data.monthly_trend.map(() => 50),
        lineStyle: { color: '#64748b', type: 'dashed' as const, width: 1 }, symbol: 'none' },
      { type: 'bar' as const, name: '准确率',
        data: data.monthly_trend.map(t => t.accuracy != null ? +(t.accuracy * 100).toFixed(1) : null),
        itemStyle: { borderRadius: [4, 4, 0, 0], color: (p: any) => p.value >= 55 ? '#22c55e' : p.value >= 50 ? '#f59e0b' : '#ef4444' },
        barMaxWidth: 40 },
    ],
    legend: { top: 0, right: 0, textStyle: { color: '#64748b', fontSize: 11 }, icon: 'rect', itemWidth: 12, itemHeight: 8 },
    tooltip: { trigger: 'axis' as const, backgroundColor: '#1a1e28', borderColor: '#252936', textStyle: { color: '#e2e8f0', fontSize: 12 } },
  }

  const dirLabel: Record<string, string> = { up: '偏多', neutral: '中性', down: '偏空' }
  const dirColor: Record<string, string> = { up: 'var(--up)', neutral: 'var(--neutral)', down: 'var(--down)' }
  const mktLabel: Record<string, string> = { A: 'A股', HK: '港股通' }

  return (
    <div style={{ padding: '26px 30px' }}>
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>预测准确率</h1>
        <div style={{ color: 'var(--muted)', fontSize: 12 }}>所有预测到期后自动核对实际涨跌 · 随机猜测基准 50%</div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 22 }}>
        <StatCard label="总体方向准确率" value={`${overallPct}%`}
          sub={data.beat_baseline != null ? `超基准 ${data.beat_baseline > 0 ? '+' : ''}${(data.beat_baseline * 100).toFixed(1)}%` : undefined}
          color={overallPct !== 'N/A' && parseFloat(overallPct) >= 52 ? 'var(--up)' : 'var(--neutral)'} />
        <StatCard label="随机基准" value="50%" sub="随机猜涨跌的期望" color="var(--muted)" />
        <StatCard label="T+1 准确率" value={data.by_horizon.T1?.accuracy != null ? `${(data.by_horizon.T1.accuracy * 100).toFixed(1)}%` : 'N/A'} sub={`${data.by_horizon.T1?.count || 0} 条`} />
        <StatCard label="T+3 准确率" value={data.by_horizon.T3?.accuracy != null ? `${(data.by_horizon.T3.accuracy * 100).toFixed(1)}%` : 'N/A'} sub={`${data.by_horizon.T3?.count || 0} 条`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr 240px', gap: 18, marginBottom: 18 }}>
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>综合准确率</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>累计 {data.total_predictions} 条 · {data.correct_predictions} 条准确</div>
          <div style={{ textAlign: 'center', paddingBottom: 12 }}>
            <svg width={130} height={130} viewBox="0 0 130 130">
              <circle cx={65} cy={65} r={ringR} fill="none" stroke="var(--border)" strokeWidth={8} />
              <circle cx={65} cy={65} r={ringR} fill="none" stroke="var(--muted)" strokeWidth={2} strokeDasharray={`${0.5 * ringCirc} ${ringCirc}`} transform="rotate(-90 65 65)" opacity={0.4} />
              {data.overall_accuracy != null && <circle cx={65} cy={65} r={ringR} fill="none" stroke={data.beat_baseline != null && data.beat_baseline > 0 ? 'var(--up)' : 'var(--down)'} strokeWidth={8} strokeLinecap="round" strokeDasharray={`${ringArc.toFixed(1)} ${ringCirc.toFixed(1)}`} transform="rotate(-90 65 65)" style={{ transition: 'stroke-dasharray 1s' }} />}
              <text x={65} y={60} textAnchor="middle" fontSize={22} fontWeight={700} fill={data.beat_baseline != null && data.beat_baseline > 0 ? '#22c55e' : '#ef4444'} fontFamily="DM Mono, monospace">{overallPct}%</text>
              <text x={65} y={78} textAnchor="middle" fontSize={11} fill="#64748b">方向准确率</text>
            </svg>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            {['T1', 'T3'].map(h => {
              const hd = data.by_horizon[h]; const hp = hd?.accuracy != null ? (hd.accuracy * 100).toFixed(1) : null
              const hc = hp != null && parseFloat(hp) >= 50 ? 'var(--up)' : 'var(--down)'
              return (<div key={h} style={{ flex: 1, background: 'var(--bg3)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{h === 'T1' ? 'T+1' : 'T+3'}</div>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'monospace', color: hc }}>{hp != null ? `${hp}%` : '—'}</div>
                <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>{hd?.count || 0}条</div>
              </div>)
            })}
          </div>
        </div>

        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>月度准确率趋势</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>绿≥55% · 黄50-55% · 红&lt;50%</div>
          {data.monthly_trend.length < 2 ? <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>数据积累中</div>
            : <ReactECharts option={trendOpt} style={{ height: 240 }} />}
        </div>

        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>分类准确率</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>按市场</div>
          {catData && catData.by_market.length > 0 ? catData.by_market.map(m => <AccBar key={m.market} label={mktLabel[m.market] || m.market} accuracy={m.accuracy} count={m.total} />)
            : <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>暂无数据</div>}
          <div style={{ height: 1, background: 'var(--border)', margin: '12px 0' }} />
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>按信号强度</div>
          {catData && catData.by_strength.length > 0 ? catData.by_strength.map(s => <AccBar key={s.strength} label={'★'.repeat(s.strength) + '☆'.repeat(5 - s.strength)} accuracy={s.accuracy} count={s.total} />)
            : <div style={{ fontSize: 12, color: 'var(--muted)' }}>暂无数据</div>}
        </div>
      </div>

      {/* 个股准确率表 */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '13px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600, fontSize: 15 }}>个股历史预测准确率</div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>点击展开历史明细</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px', padding: '9px 18px', borderBottom: '1px solid var(--border)' }}>
          {['股票', 'T+1', 'T+3', '预测条数', '超基准'].map(h => <div key={h} style={{ fontSize: 12, color: 'var(--muted)' }}>{h}</div>)}
        </div>
        {stockAccs.length === 0 ? <div style={{ padding: '20px 18px', color: 'var(--muted)', fontSize: 13, textAlign: 'center' }}>首批预测结算后自动显示</div>
        : stockAccs.map(sa => {
          const bc = sa.beat_baseline != null && sa.beat_baseline > 0 ? 'var(--up)' : sa.beat_baseline != null ? 'var(--down)' : 'var(--muted)'
          return (<div key={sa.code}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px', padding: '10px 18px', borderBottom: '1px solid var(--border)', cursor: 'pointer', alignItems: 'center', transition: 'background .1s' }}
              onClick={() => toggleStockDetail(sa.code)} onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg3)')} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
              <div>
                <span style={{ fontWeight: 500 }}>{sa.name}</span>
                <span style={{ color: 'var(--muted)', fontSize: 11, marginLeft: 8, fontFamily: 'monospace' }}>{sa.code}</span>
                <span style={{ marginLeft: 6, padding: '1px 5px', borderRadius: 3, fontSize: 10, background: sa.market === 'HK' ? 'rgba(139,92,246,.15)' : 'rgba(99,102,241,.15)', color: sa.market === 'HK' ? '#a78bfa' : 'var(--accent2)' }}>{sa.market === 'HK' ? '港股' : 'A股'}</span>
                <span style={{ color: 'var(--accent2)', fontSize: 11, marginLeft: 8 }}>{expandedCode === sa.code ? '▲' : '▼'}</span>
              </div>
              <div style={{ fontFamily: 'monospace', fontSize: 13, color: sa.t1_accuracy != null && sa.t1_accuracy >= 0.5 ? 'var(--up)' : 'var(--down)' }}>{sa.t1_accuracy != null ? `${(sa.t1_accuracy * 100).toFixed(1)}%` : '—'}</div>
              <div style={{ fontFamily: 'monospace', fontSize: 13, color: sa.t3_accuracy != null && sa.t3_accuracy >= 0.5 ? 'var(--up)' : 'var(--down)' }}>{sa.t3_accuracy != null ? `${(sa.t3_accuracy * 100).toFixed(1)}%` : '—'}</div>
              <div style={{ fontFamily: 'monospace', fontSize: 13 }}>{sa.total}</div>
              <div style={{ fontFamily: 'monospace', fontSize: 13, color: bc }}>{sa.beat_baseline != null ? `${sa.beat_baseline > 0 ? '+' : ''}${(sa.beat_baseline * 100).toFixed(1)}%` : '—'}</div>
            </div>
            {expandedCode === sa.code && (
              <div style={{ background: 'var(--bg3)', padding: '12px 18px' }}>
                {loadingHistory ? <div style={{ padding: 16, textAlign: 'center', color: 'var(--muted)' }}><span className="spinner" /> 加载中...</div>
                : stockHistory.length === 0 ? <div style={{ padding: 16, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>暂无记录</div>
                : <div style={{ display: 'grid', gridTemplateColumns: '90px 50px 54px 66px 96px 86px 70px' }}>
                    {['预测日','周期','方向','概率','区间','实际','结果'].map(h => <div key={h} style={{ fontSize: 11, color: 'var(--muted)', padding: '6px 4px', borderBottom: '1px solid var(--border)' }}>{h}</div>)}
                    {stockHistory.map((p, j) => (
                      <React.Fragment key={j}>
                        <div style={{ padding: '7px 4px', fontFamily: 'monospace', fontSize: 12, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>{p.predict_date}</div>
                        <div style={{ padding: '7px 4px', fontSize: 11, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}><span style={{ padding: '1px 5px', borderRadius: 3, background: 'var(--bg2)', color: 'var(--muted)', fontSize: 10 }}>{p.horizon === 'T1' ? 'T+1' : 'T+3'}</span></div>
                        <div style={{ padding: '7px 4px', color: dirColor[p.direction], fontWeight: 500, fontSize: 12, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>{dirLabel[p.direction] || p.direction}</div>
                        <div style={{ padding: '7px 4px', fontFamily: 'monospace', fontSize: 12, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>{(p.prob_up * 100).toFixed(0)}%</div>
                        <div style={{ padding: '7px 4px', fontFamily: 'monospace', fontSize: 11, color: 'var(--muted)', borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>{p.pred_range_low?.toFixed(1)}%~{p.pred_range_high?.toFixed(1)}%</div>
                        <div style={{ padding: '7px 4px', fontFamily: 'monospace', fontSize: 12, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>
                          {p.actual_change_pct != null ? <span style={{ color: p.actual_change_pct >= 0 ? 'var(--up)' : 'var(--down)' }}>{p.actual_change_pct >= 0 ? '+' : ''}{p.actual_change_pct.toFixed(2)}%</span> : <span style={{ color: 'var(--muted)' }}>待结算</span>}
                        </div>
                        <div style={{ padding: '7px 4px', fontSize: 12, borderBottom: j < stockHistory.length - 1 ? '1px solid var(--border)' : 'none' }}>
                          {p.is_correct === null ? <span style={{ color: 'var(--muted)' }}>—</span> : p.is_correct ? <span style={{ color: 'var(--up)' }}>✓</span> : <span style={{ color: 'var(--down)' }}>✗</span>}
                        </div>
                      </React.Fragment>
                    ))}
                  </div>}
              </div>
            )}
          </div>)
        })}
      </div>

      <div style={{ marginTop: 18, padding: '13px 18px', background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, fontSize: 12, color: 'var(--muted)', lineHeight: 1.9 }}>
        <strong style={{ color: 'var(--text)' }}>如何读懂准确率？</strong>&nbsp;随机猜涨跌的期望准确率约50%。本模型目标是持续超越这个基准。<strong style={{ color: 'var(--neutral)' }}>所有预测仅供参考，不构成投资建议。</strong>
      </div>
    </div>
  )
}

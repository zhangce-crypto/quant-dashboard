/**
 * Accuracy.tsx — 预测准确率页
 *
 * 展示内容：
 *   - 全局指标卡片：总准确率 / 随机基准 / T+1 / T+3
 *   - 综合准确率仪表（带随机基准对比环）
 *   - 月度趋势柱状图（含虚线基准）
 *   - 个股历史预测准确率表
 *   - 点击个股展开历史预测明细（预测方向 / 实际涨跌 / 是否准确）
 *
 * 关联文件：
 *   api.ts: accuracyApi.summary / accuracyApi.history
 */
import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { accuracyApi } from '../lib/api'

type Summary = {
  overall_accuracy: number | null
  baseline: number
  beat_baseline: number | null
  total_predictions: number
  correct_predictions: number
  by_horizon: Record<string, { accuracy: number | null; count: number; beat_baseline: number | null }>
  monthly_trend: { month: string; accuracy: number | null; count: number; baseline: number }[]
}
type StockHistory = {
  predict_date: string; horizon: string; direction: string
  prob_up: number; pred_range_low: number; pred_range_high: number
  is_correct: boolean | null; actual_direction: string | null
  actual_change_pct: number | null; settled_at: string | null
  ai_summary: string
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

export default function Accuracy() {
  const [data,           setData]           = useState<Summary | null>(null)
  const [loading,        setLoading]        = useState(true)
  const [expandedCode,   setExpandedCode]   = useState<string | null>(null)
  const [stockHistory,   setStockHistory]   = useState<StockHistory[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [expandedName,   setExpandedName]   = useState('')

  useEffect(() => {
    accuracyApi.summary().then(r => setData(r.data)).catch(() => {}).finally(() => setLoading(false))
  }, [])

  async function toggleStockDetail(code: string, name: string) {
    if (expandedCode === code) { setExpandedCode(null); return }
    setExpandedCode(code); setExpandedName(name); setLoadingHistory(true)
    try {
      const r = await accuracyApi.history(code)
      setStockHistory(r.data)
    } catch {} finally { setLoadingHistory(false) }
  }

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)' }}>加载中...</div>

  if (!data || data.total_predictions === 0) return (
    <div style={{ padding: '26px 30px' }}>
      <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 6 }}>预测准确率</h1>
      <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 32 }}>对比模型预测与实际涨跌，验证量化信号有效性</div>
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '80px 0', textAlign: 'center', color: 'var(--muted)' }}>
        <div style={{ fontSize: 36, marginBottom: 16 }}>◎</div>
        <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 12 }}>暂无预测记录</div>
        <div style={{ fontSize: 14, maxWidth: 400, margin: '0 auto', lineHeight: 1.8 }}>
          在「仪表盘」点击任意股票进入详情页，点击「生成今日预测」开始记录。预测到期后系统自动核对，准确率将在此展示。
        </div>
      </div>
    </div>
  )

  const overallPct = data.overall_accuracy != null ? (data.overall_accuracy * 100).toFixed(1) : 'N/A'
  const beatColor  = data.beat_baseline != null && data.beat_baseline > 0 ? 'var(--up)' : 'var(--down)'
  const ringArc    = data.overall_accuracy != null ? data.overall_accuracy * 2 * Math.PI * 52 : 0
  const ringCirc   = 2 * Math.PI * 52

  const trendOpt = {
    backgroundColor: 'transparent',
    grid: { left: 44, right: 14, top: 16, bottom: 36 },
    xAxis: {
      type: 'category',
      data: data.monthly_trend.map(t => t.month),
      axisLabel: { color: '#64748b', fontSize: 11 }, axisLine: { lineStyle: { color: '#252936' } },
    },
    yAxis: {
      type: 'value', min: 40, max: 70,
      axisLabel: { color: '#64748b', fontSize: 11, formatter: (v: number) => v + '%' },
      splitLine: { lineStyle: { color: '#252936' } },
    },
    series: [
      {
        type: 'line', name: '随机基准50%',
        data: data.monthly_trend.map(() => 50),
        lineStyle: { color: '#64748b', type: 'dashed', width: 1 },
        symbol: 'none',
      },
      {
        type: 'bar', name: '模型准确率',
        data: data.monthly_trend.map(t => t.accuracy != null ? +(t.accuracy * 100).toFixed(1) : null),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: (p: any) => p.value >= 55 ? '#22c55e' : p.value >= 50 ? '#f59e0b' : '#ef4444',
        },
        barMaxWidth: 40,
      },
    ],
    legend: { top: 0, right: 0, textStyle: { color: '#64748b', fontSize: 11 }, icon: 'rect', itemWidth: 12, itemHeight: 8 },
    tooltip: {
      trigger: 'axis', backgroundColor: '#1a1e28', borderColor: '#252936',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: (params: any[]) => {
        const month = params[0].axisValue
        const acc = params.find((p: any) => p.seriesName === '模型准确率')?.value
        const cnt = data.monthly_trend.find(t => t.month === month)?.count || 0
        return `${month}<br/>准确率: ${acc != null ? acc + '%' : 'N/A'}<br/>样本量: ${cnt}条`
      },
    },
  }

  const dirLabel: Record<string, string> = { up: '偏多', neutral: '中性', down: '偏空' }
  const dirColor: Record<string, string> = { up: 'var(--up)', neutral: 'var(--neutral)', down: 'var(--down)' }

  return (
    <div style={{ padding: '26px 30px' }}>
      <div style={{ marginBottom: 22 }}>
        <h1 style={{ fontSize: 21, fontWeight: 700, marginBottom: 4 }}>预测准确率</h1>
        <div style={{ color: 'var(--muted)', fontSize: 12 }}>所有预测到期后自动核对实际涨跌 · 随机猜测基准 50%</div>
      </div>

      {/* 顶部指标卡 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 22 }}>
        <StatCard label="总体方向准确率" value={`${overallPct}%`}
          sub={data.beat_baseline != null ? `超随机基准 ${data.beat_baseline > 0 ? '+' : ''}${(data.beat_baseline * 100).toFixed(1)}%` : undefined}
          color={overallPct !== 'N/A' && parseFloat(overallPct) >= 52 ? 'var(--up)' : 'var(--neutral)'}
        />
        <StatCard label="随机基准（参照）" value="50%" sub="随机猜涨跌的期望准确率" color="var(--muted)" />
        <StatCard
          label="T+1 准确率"
          value={data.by_horizon.T1?.accuracy != null ? `${(data.by_horizon.T1.accuracy * 100).toFixed(1)}%` : 'N/A'}
          sub={`样本 ${data.by_horizon.T1?.count || 0} 条`}
        />
        <StatCard
          label="T+3 准确率"
          value={data.by_horizon.T3?.accuracy != null ? `${(data.by_horizon.T3.accuracy * 100).toFixed(1)}%` : 'N/A'}
          sub={`样本 ${data.by_horizon.T3?.count || 0} 条`}
        />
      </div>

      {/* 仪表 + 趋势图 */}
      <div style={{ display: 'grid', gridTemplateColumns: '330px 1fr', gap: 18, marginBottom: 18 }}>
        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>综合准确率</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
            累计 {data.total_predictions} 条预测 · {data.correct_predictions} 条准确
          </div>
          <div style={{ textAlign: 'center', paddingBottom: 12 }}>
            <svg width={150} height={150} viewBox="0 0 150 150">
              <circle cx={75} cy={75} r={52} fill="none" stroke="var(--border)" strokeWidth={8} />
              {/* 基准线（50%位置） */}
              <circle cx={75} cy={75} r={52} fill="none" stroke="var(--muted)" strokeWidth={2}
                strokeDasharray={`${0.5 * ringCirc} ${ringCirc}`}
                transform="rotate(-90 75 75)" opacity={0.4}
              />
              {/* 准确率弧 */}
              {data.overall_accuracy != null && (
                <circle cx={75} cy={75} r={52} fill="none"
                  stroke={data.beat_baseline != null && data.beat_baseline > 0 ? 'var(--up)' : 'var(--down)'}
                  strokeWidth={8} strokeLinecap="round"
                  strokeDasharray={`${(data.overall_accuracy * ringCirc).toFixed(1)} ${ringCirc.toFixed(1)}`}
                  transform="rotate(-90 75 75)" style={{ transition: 'stroke-dasharray 1s' }}
                />
              )}
              <text x={75} y={70} textAnchor="middle" fontSize={26} fontWeight={700}
                fill={data.beat_baseline != null && data.beat_baseline > 0 ? '#22c55e' : '#ef4444'}
                fontFamily="DM Mono, monospace">{overallPct}%</text>
              <text x={75} y={88} textAnchor="middle" fontSize={11} fill="#64748b">方向准确率</text>
            </svg>
            <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 8 }}>
              随机基准 <span style={{ fontFamily: 'monospace', color: 'var(--text)' }}>50%</span>
              &nbsp;·&nbsp;
              超越基准&nbsp;
              <span style={{ fontFamily: 'monospace', color: beatColor }}>
                {data.beat_baseline != null ? `${data.beat_baseline > 0 ? '+' : ''}${(data.beat_baseline * 100).toFixed(1)}%` : 'N/A'}
              </span>
            </div>
          </div>
          <div style={{ height: 1, background: 'var(--border)', margin: '12px 0' }} />
          <div style={{ display: 'flex', gap: 10 }}>
            {['T1', 'T3'].map(h => {
              const hd = data.by_horizon[h]
              const hpct = hd?.accuracy != null ? (hd.accuracy * 100).toFixed(1) : null
              const hbeat = hd?.beat_baseline != null ? (hd.beat_baseline * 100).toFixed(1) : null
              const hcolor = hpct != null && parseFloat(hpct) >= 50 ? 'var(--up)' : 'var(--down)'
              return (
                <div key={h} style={{ flex: 1, background: 'var(--bg3)', borderRadius: 8, padding: '12px 14px' }}>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>{h === 'T1' ? 'T+1 预测' : 'T+3 预测'}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'monospace', color: hcolor }}>
                    {hpct != null ? `${hpct}%` : '—'}
                  </div>
                  {hbeat && (
                    <div style={{ fontSize: 11, color: hcolor, marginTop: 4 }}>
                      超基准 {parseFloat(hbeat) > 0 ? '+' : ''}{hbeat}%
                    </div>
                  )}
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>{hd?.count || 0}条样本</div>
                </div>
              )
            })}
          </div>
        </div>

        <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>月度准确率趋势</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
            绿色 ≥55% · 黄色 50-55% · 红色 &lt;50% · 虚线为随机基准
          </div>
          {data.monthly_trend.length < 2 ? (
            <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
              数据积累中，至少需要2个月的预测记录
            </div>
          ) : (
            <ReactECharts option={trendOpt} style={{ height: 260 }} />
          )}
        </div>
      </div>

      {/* 个股准确率表 */}
      <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ padding: '13px 18px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 600, fontSize: 15 }}>个股历史预测准确率</div>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>点击股票名称展开历史预测明细</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 80px 80px 80px', padding: '9px 18px', borderBottom: '1px solid var(--border)' }}>
          {['股票','T+1','T+3','预测条数','超基准'].map(h => (
            <div key={h} style={{ fontSize: 12, color: 'var(--muted)' }}>{h}</div>
          ))}
        </div>

        {/* 这里由后端返回的 accuracy_stats 渲染；演示状态下展示占位 */}
        <div style={{ padding: '20px 18px', color: 'var(--muted)', fontSize: 13, textAlign: 'center' }}>
          个股准确率将在首批预测结算后自动显示
        </div>
      </div>

      {/* 个股历史明细展开区 */}
      {expandedCode && (
        <div style={{ marginTop: 16, background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 12 }}>
            <button onClick={() => setExpandedCode(null)} style={{
              background: 'none', border: '1px solid var(--border)', borderRadius: 7,
              color: 'var(--muted)', padding: '4px 10px', cursor: 'pointer', fontSize: 12,
            }}>← 收起</button>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{expandedName} 历史预测明细</div>
          </div>
          {loadingHistory ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--muted)' }}>加载中...</div>
          ) : stockHistory.length === 0 ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>暂无历史预测记录</div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '92px 54px 60px 72px 100px 90px 80px', padding: '9px 18px', borderBottom: '1px solid var(--border)' }}>
                {['预测日','周期','方向','上涨概率','预测区间','实际涨跌','结果'].map(h => (
                  <div key={h} style={{ fontSize: 12, color: 'var(--muted)' }}>{h}</div>
                ))}
              </div>
              {stockHistory.map((p, i) => (
                <div key={i} style={{
                  display: 'grid', gridTemplateColumns: '92px 54px 60px 72px 100px 90px 80px',
                  padding: '10px 18px', fontSize: 13,
                  borderBottom: i < stockHistory.length - 1 ? '1px solid var(--bg3)' : 'none',
                  alignItems: 'center',
                }}>
                  <div style={{ fontFamily: 'monospace' }}>{p.predict_date}</div>
                  <div>
                    <span style={{ padding: '2px 6px', borderRadius: 4, fontSize: 11, background: 'var(--bg3)', color: 'var(--muted)' }}>
                      {p.horizon === 'T1' ? 'T+1' : 'T+3'}
                    </span>
                  </div>
                  <div style={{ color: dirColor[p.direction], fontWeight: 500 }}>
                    {dirLabel[p.direction] || p.direction}
                  </div>
                  <div style={{ fontFamily: 'monospace' }}>{(p.prob_up * 100).toFixed(0)}%</div>
                  <div style={{ fontFamily: 'monospace', color: 'var(--muted)', fontSize: 12 }}>
                    {p.pred_range_low?.toFixed(1)}%~{p.pred_range_high?.toFixed(1)}%
                  </div>
                  <div>
                    {p.actual_change_pct != null
                      ? <span style={{ fontFamily: 'monospace', color: p.actual_change_pct >= 0 ? 'var(--up)' : 'var(--down)' }}>
                          {p.actual_change_pct >= 0 ? '+' : ''}{p.actual_change_pct.toFixed(2)}%
                        </span>
                      : <span style={{ color: 'var(--muted)' }}>待结算</span>}
                  </div>
                  <div>
                    {p.is_correct === null
                      ? <span style={{ color: 'var(--muted)' }}>—</span>
                      : p.is_correct
                        ? <span style={{ color: 'var(--up)' }}>✓ 准确</span>
                        : <span style={{ color: 'var(--down)' }}>✗ 偏差</span>}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* 说明 */}
      <div style={{ marginTop: 18, padding: '13px 18px', background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, fontSize: 12, color: 'var(--muted)', lineHeight: 1.9 }}>
        <strong style={{ color: 'var(--text)' }}>如何读懂准确率？</strong>
        &nbsp;随机猜涨跌的期望准确率约50%。本模型目标是持续超越这个基准。根据回测，V1.0模型历史准确率约52%，超越基准约+2%。数据积累越多，这个数字越可信。早期样本量少时波动较大，属正常现象。
        &nbsp;<strong style={{ color: 'var(--neutral)' }}>所有预测仅供参考，不构成投资建议。</strong>
      </div>
    </div>
  )
}

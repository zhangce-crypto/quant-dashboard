/**
 * StockDetail.tsx — 股票详情页
 *
 * 进入路径：/stock/:market/:code
 * 返回路径：← 返回 → navigate(-1) 回仪表盘
 *
 * 展示内容：
 *   左侧：近60日K线图（ECharts）+ 预测记录表（生成后显示）
 *   右侧：综合评分环 + 四维评分条 + T+1概率 + T+3预测区间
 *
 * 关联文件：
 *   api.ts: marketApi.analysis / marketApi.predict
 *   Dashboard.tsx: 点击股票行跳转到此页
 */
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import { marketApi } from '../lib/api'

type Analysis = {
  code: string; market: string
  score: {
    total_score: number
    fundamental_score: number; technical_score: number
    fund_flow_score: number; sentiment_score: number
    prob_up: number; signal: string; signal_strength: number
    pred_range_low: number; pred_range_high: number
  }
  signal_label: string; advice: string
  recent_predictions: any[]
  history_dates: string[]; history_close: number[]; history_volume: number[]
}

function DimBar({ label, score }: { label: string; score: number }) {
  const color = score >= 65 ? 'var(--up)' : score <= 40 ? 'var(--down)' : 'var(--neutral)'
  return (
    <div style={{ marginBottom: 13 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{label}</span>
        <span style={{ fontSize: 12, color, fontWeight: 600, fontFamily: 'monospace' }}>{score.toFixed(0)}</span>
      </div>
      <div style={{ height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 2, transition: 'width .6s ease' }} />
      </div>
    </div>
  )
}

export default function StockDetail() {
  const { market, code } = useParams<{ market: string; code: string }>()
  const navigate = useNavigate()
  const [data,       setData]       = useState<Analysis | null>(null)
  const [loading,    setLoading]    = useState(true)
  const [predicting, setPredicting] = useState(false)
  const [err,        setErr]        = useState('')

  useEffect(() => {
    if (!code || !market) return
    setLoading(true); setErr('')
    marketApi.analysis(code, market)
      .then(r => setData(r.data))
      .catch(() => setErr('数据加载失败，请稍后重试'))
      .finally(() => setLoading(false))
  }, [code, market])

  async function predict() {
    if (!code || !market) return
    setPredicting(true)
    try {
      await marketApi.predict(code, market)
      const r = await marketApi.analysis(code, market)
      setData(r.data)
    } catch {} finally { setPredicting(false) }
  }

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: 'var(--muted)' }}>加载中...</div>
  if (err || !data) return <div style={{ padding: 60, textAlign: 'center', color: 'var(--down)' }}>{err || '暂无数据'}</div>

  const { score } = data

  const klineOpt = {
    backgroundColor: 'transparent',
    grid: [
      { left: 58, right: 16, top: 18, height: '62%' },
      { left: 58, right: 16, bottom: 36, height: '20%' },
    ],
    xAxis: [
      { type: 'category', data: data.history_dates, gridIndex: 0,
        axisLabel: { color: '#64748b', fontSize: 11 }, axisLine: { lineStyle: { color: '#252936' } } },
      { type: 'category', data: data.history_dates, gridIndex: 1,
        axisLabel: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0,
        axisLabel: { color: '#64748b', fontSize: 11 }, splitLine: { lineStyle: { color: '#252936' } } },
      { type: 'value', gridIndex: 1,
        axisLabel: { color: '#64748b', fontSize: 10, formatter: (v: number) => v >= 1e8 ? (v/1e8).toFixed(0)+'亿' : (v/1e4).toFixed(0)+'w' },
        splitLine: { lineStyle: { color: '#252936' } } },
    ],
    series: [
      { type: 'line', data: data.history_close, xAxisIndex: 0, yAxisIndex: 0, symbol: 'none', smooth: true,
        lineStyle: { color: '#818cf8', width: 2 },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99,102,241,.25)' }, { offset: 1, color: 'rgba(99,102,241,0)' }] } } },
      { type: 'bar', data: data.history_volume, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: '#252936', borderRadius: 2 } },
    ],
    tooltip: { trigger: 'axis', backgroundColor: '#1a1e28', borderColor: '#252936', textStyle: { color: '#e2e8f0', fontSize: 12 } },
  }

  const ringColor = score.total_score >= 65 ? 'var(--up)' : score.total_score <= 40 ? 'var(--down)' : 'var(--neutral)'
  const ringArc   = score.total_score / 100 * (2 * Math.PI * 42)
  const ringCirc  = 2 * Math.PI * 42

  const horizonLabel: Record<string, string> = { T1: 'T+1', T3: 'T+3' }
  const dirLabel: Record<string, string> = { up: '偏多', neutral: '中性', down: '偏空' }
  const dirColor: Record<string, string> = { up: 'var(--up)', neutral: 'var(--neutral)', down: 'var(--down)' }

  return (
    <div style={{ padding: '26px 30px' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={() => navigate(-1)} style={{
            background: 'none', border: '1px solid var(--border)', borderRadius: 8,
            color: 'var(--muted)', padding: '6px 13px', cursor: 'pointer', fontSize: 13,
          }}>← 返回</button>
          <div>
            <h1 style={{ fontSize: 21, fontWeight: 700 }}>{code}</h1>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 3 }}>
              {market === 'HK' ? '港股通' : 'A股'} · 以下所有信号仅供参考，不构成投资建议
            </div>
          </div>
        </div>
        <button onClick={predict} disabled={predicting} style={{
          padding: '9px 20px', background: 'var(--accent)', border: 'none',
          borderRadius: 8, color: '#fff', cursor: predicting ? 'not-allowed' : 'pointer',
          fontSize: 14, fontWeight: 500, opacity: predicting ? .6 : 1,
        }}>{predicting ? '计算中...' : '生成今日预测'}</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 312px', gap: 20 }}>
        {/* 左侧 */}
        <div>
          {/* K线图 */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px', marginBottom: 18 }}>
            <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>近60日走势</div>
            <ReactECharts option={klineOpt} style={{ height: 320 }} />
          </div>

          {/* 预测记录 */}
          {data.recent_predictions.length > 0 && (
            <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '16px 18px' }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>近期预测记录</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border)' }}>
                    {['预测日','周期','方向','上涨概率','预测区间','实际结果','是否准确'].map(h => (
                      <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: 'var(--muted)', fontWeight: 400 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.recent_predictions.map((p, i) => (
                    <tr key={i} style={{ borderBottom: i < data.recent_predictions.length - 1 ? '1px solid var(--border)' : 'none' }}>
                      <td style={{ padding: '9px 10px', fontFamily: 'monospace' }}>{p.predict_date}</td>
                      <td style={{ padding: '9px 10px' }}>
                        <span style={{ padding: '2px 7px', borderRadius: 4, fontSize: 11, background: 'var(--bg3)', color: 'var(--muted)' }}>
                          {horizonLabel[p.horizon] || p.horizon}
                        </span>
                      </td>
                      <td style={{ padding: '9px 10px', color: dirColor[p.direction], fontWeight: 500 }}>
                        {dirLabel[p.direction] || p.direction}
                      </td>
                      <td style={{ padding: '9px 10px', fontFamily: 'monospace' }}>{(p.prob_up * 100).toFixed(0)}%</td>
                      <td style={{ padding: '9px 10px', fontSize: 12, color: 'var(--muted)', fontFamily: 'monospace' }}>
                        {p.pred_range_low?.toFixed(1)}% ~ {p.pred_range_high?.toFixed(1)}%
                      </td>
                      <td style={{ padding: '9px 10px', fontFamily: 'monospace' }}>
                        {p.actual_change_pct != null
                          ? <span style={{ color: p.actual_change_pct >= 0 ? 'var(--up)' : 'var(--down)' }}>
                              {p.actual_change_pct >= 0 ? '+' : ''}{p.actual_change_pct.toFixed(2)}%
                            </span>
                          : <span style={{ color: 'var(--muted)' }}>待结算</span>}
                      </td>
                      <td style={{ padding: '9px 10px' }}>
                        {p.is_correct === null
                          ? <span style={{ color: 'var(--muted)' }}>—</span>
                          : p.is_correct
                            ? <span style={{ color: 'var(--up)' }}>✓ 准确</span>
                            : <span style={{ color: 'var(--down)' }}>✗ 偏差</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 右侧 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* 综合评分 */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <svg width={100} height={100} viewBox="0 0 100 100">
                <circle cx={50} cy={50} r={42} fill="none" stroke="var(--border)" strokeWidth={6} />
                <circle cx={50} cy={50} r={42} fill="none" stroke={ringColor} strokeWidth={6}
                  strokeLinecap="round"
                  strokeDasharray={`${ringArc.toFixed(1)} ${ringCirc.toFixed(1)}`}
                  transform="rotate(-90 50 50)" style={{ transition: 'stroke-dasharray .8s' }}
                />
                <text x={50} y={46} textAnchor="middle" fontSize={22} fontWeight={700}
                  fill={ringColor} fontFamily="DM Mono, monospace">
                  {Math.round(score.total_score)}
                </text>
                <text x={50} y={63} textAnchor="middle" fontSize={11} fill="#64748b">综合评分</text>
              </svg>
              <div style={{ fontSize: 15, fontWeight: 600, marginTop: 8 }}>{data.signal_label}</div>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>参考建议：{data.advice}</div>
            </div>
            <div style={{ height: 1, background: 'var(--border)', margin: '12px 0' }} />
            <DimBar label="基本面（代理因子）" score={score.fundamental_score} />
            <DimBar label="技术面" score={score.technical_score} />
            <DimBar label="资金流向" score={score.fund_flow_score} />
            <DimBar label="市场情绪" score={score.sentiment_score} />
          </div>

          {/* 概率 */}
          <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 10, padding: '18px 20px' }}>
            <div style={{ fontSize: 38, fontWeight: 700, fontFamily: 'monospace', color: score.prob_up >= .55 ? 'var(--up)' : score.prob_up <= .45 ? 'var(--down)' : 'var(--neutral)' }}>
              {(score.prob_up * 100).toFixed(0)}%
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6 }}>T+1 上涨概率</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>随机基准：50%</div>

            <div style={{ height: 1, background: 'var(--border)', margin: '14px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
              <div>
                <div style={{ color: 'var(--muted)', marginBottom: 5 }}>T+3 预测区间</div>
                <span style={{ fontFamily: 'monospace' }}>
                  {score.pred_range_low.toFixed(1)}% ~ {score.pred_range_high.toFixed(1)}%
                </span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--muted)', marginBottom: 5 }}>信号强度</div>
                <span style={{ color: score.total_score >= 65 ? 'var(--up)' : 'var(--neutral)' }}>
                  {'★'.repeat(score.signal_strength)}{'☆'.repeat(5 - score.signal_strength)}
                </span>
              </div>
            </div>

            <div style={{
              marginTop: 14, padding: '10px 12px',
              background: 'var(--bg3)', borderRadius: 8,
              fontSize: 12, color: 'var(--muted)', lineHeight: 1.6,
            }}>
              ⚠ 以上概率由量化模型计算，历史回测准确率约52%，仅供参考。股市有风险，投资需谨慎。
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

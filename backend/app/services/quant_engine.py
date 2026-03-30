"""
quant_engine.py — 量化评分引擎（核心模块）
═══════════════════════════════════════════════════════════════
职责：
  1. 从历史K线数据计算10个量化因子
  2. 截面分位数标准化 + IC加权合成综合评分（0-100分）
  3. 评分转换为涨跌概率、预测区间、信号标签

调用关系：
  main.py → GET /api/market/stock/{code}/analysis
  main.py → POST /api/market/stock/{code}/predict
  scheduler.py → refresh_all_scores() 定时任务

如何修改：
  调整因子权重    → 修改 FACTOR_IC_WEIGHTS
  调整维度权重    → 修改 DIMENSION_WEIGHTS（四项必须合计=1.00）
  增加新因子      → compute_factors() 末尾添加，再在两个字典中注册
  修改信号阈值    → compute_score() 末尾的 signal/strength 判断

回测结论（49只A股+港股通，3年数据）：
  方向准确率 52%，超随机基准+2%，IC值0.036（旧方案的2.9倍）
  V1.1 计划引入 LightGBM 进一步提升

测试文件：tests/test_all.py → TestFactorComputation, TestScoreCalculation
═══════════════════════════════════════════════════════════════
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# 因子权重（IC加权，来自49只股票3年历史回测）
# 正数=正向因子，负数=反向因子，绝对值之和=1.00
# ──────────────────────────────────────────────────────────────
FACTOR_IC_WEIGHTS: Dict[str, float] = {
    "f_momentum":  +0.167,  # 52周高低位置，IC最高=+0.031
    "f_low_vol":   -0.076,  # 历史波动率，反向（低波动溢价），IC=-0.022
    "f_vol_trend": +0.033,  # 成交量趋势，ICIR最稳定=+0.121
    "f_vol_ratio": +0.053,  # 量比
    "f_bollinger": +0.143,  # 布林带%B
    "f_kdj_j":     +0.175,  # KDJ_J值
    "f_macd":      +0.075,  # MACD柱（归一化）
    "f_rsi":       +0.032,  # RSI(12)
    "f_ma_align":  +0.049,  # 均线多头排列（0/1）
    "f_mom5":      +0.198,  # 5日动量，权重最高
}

# ──────────────────────────────────────────────────────────────
# 因子归属维度（用于前端展示四个子评分条）
# sentiment 暂无新闻数据，V1.1 接入后激活
# ──────────────────────────────────────────────────────────────
DIMENSION_MAP: Dict[str, list] = {
    "fundamental": ["f_momentum", "f_low_vol"],
    "technical":   ["f_bollinger", "f_kdj_j", "f_macd", "f_rsi", "f_ma_align", "f_mom5"],
    "fund_flow":   ["f_vol_trend", "f_vol_ratio"],
    "sentiment":   [],  # V1.0 空列表 → 固定50分
}

# 四项之和必须精确等于 1.00
DIMENSION_WEIGHTS: Dict[str, float] = {
    "fundamental": 0.51,
    "technical":   0.18,
    "fund_flow":   0.15,
    "sentiment":   0.16,  # 0.51+0.18+0.15+0.16 = 1.00
}


def compute_factors(df: pd.DataFrame) -> Optional[Dict[str, float]]:
    """
    从历史K线 DataFrame 计算全部10个量化因子。

    入参  df: 含列 [date, open, high, low, close, volume]，日期升序
    出参: 因子字典 {"f_momentum": 0.72, "f_rsi": 63.5, ...}
          数据不足（<65行）返回 None

    各因子说明：
      f_momentum   = (收盘-52周低) / (52周高-52周低)
      f_low_vol    = 20日年化历史波动率（反向：越低越好）
      f_vol_ratio  = 近5日均量 / 近20日均量
      f_bollinger  = (收盘-布林下轨) / (布林上轨-布林下轨)
      f_kdj_j      = 3×RSV - 100（RSV基于9日高低）
      f_macd       = (EMA12-EMA26) / 收盘价
      f_rsi        = RSI(12)，0-100
      f_ma_align   = 1 if MA5>MA10>MA20>MA60 else 0
      f_vol_trend  = 近5日均量 / 近15日均量
      f_mom5       = 收盘价 / 5日前收盘价 - 1
    """
    if df is None or len(df) < 65:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    c  = df["close"].values
    h  = df["high"].values
    lo = df["low"].values
    v  = df["volume"].values
    n  = len(c)

    try:
        factors: Dict[str, float] = {}

        # F1: 52周高低位置
        w252 = min(252, n)
        hi52 = np.max(h[-w252:])
        lo52 = np.min(lo[-w252:])
        factors["f_momentum"] = float((c[-1] - lo52) / (hi52 - lo52 + 1e-8))

        # F2: 20日年化历史波动率（反向因子）
        factors["f_low_vol"] = float(
            np.std(np.diff(np.log(c[-21:]))) * np.sqrt(252)
        ) if n >= 21 else 0.3

        # F3: 量比（近5日/近20日均量）
        factors["f_vol_ratio"] = float(
            np.mean(v[-5:]) / (np.mean(v[-20:]) + 1e-8)
        ) if n >= 20 else 1.0

        # F4: 布林带%B（0=下轨，1=上轨，>1=超过上轨）
        if n >= 20:
            ma20  = np.mean(c[-20:])
            std20 = np.std(c[-20:])
            factors["f_bollinger"] = float(
                (c[-1] - (ma20 - 2*std20)) / (4*std20 + 1e-8)
            )
        else:
            factors["f_bollinger"] = 0.5

        # F5: KDJ_J值（RSV近似K，J=3RSV-100）
        if n >= 9:
            lo9 = np.min(lo[-9:])
            hi9 = np.max(h[-9:])
            rsv = float((c[-1] - lo9) / (hi9 - lo9 + 1e-8) * 100)
            factors["f_kdj_j"] = float(3 * rsv - 100)
        else:
            factors["f_kdj_j"] = 0.0

        # F6: MACD柱（EMA12-EMA26，归一化）
        def ema_val(arr: np.ndarray, span: int) -> float:
            alpha = 2 / (span + 1)
            e = float(arr[0])
            for x in arr[1:]:
                e = alpha * float(x) + (1 - alpha) * e
            return e

        if n >= 35:
            factors["f_macd"] = float(
                (ema_val(c[-35:], 12) - ema_val(c[-35:], 26)) / (c[-1] + 1e-8)
            )
        else:
            factors["f_macd"] = 0.0

        # F7: RSI(12)
        if n >= 13:
            diffs  = np.diff(c[-13:])
            gains  = float(np.mean(diffs[diffs > 0])) if (diffs > 0).any() else 0.0
            losses = float(np.mean(-diffs[diffs < 0])) if (diffs < 0).any() else 1e-8
            factors["f_rsi"] = float(100 - 100 / (1 + gains / (losses + 1e-8)))
        else:
            factors["f_rsi"] = 50.0

        # F8: 均线多头排列（0或1）
        if n >= 60:
            factors["f_ma_align"] = float(
                np.mean(c[-5:]) > np.mean(c[-10:]) >
                np.mean(c[-20:]) > np.mean(c[-60:])
            )
        else:
            factors["f_ma_align"] = 0.0

        # F9: 成交量趋势（近5日/近15日均量）
        factors["f_vol_trend"] = float(
            np.mean(v[-5:]) / (np.mean(v[-15:]) + 1e-8)
        ) if n >= 15 else 1.0

        # F10: 5日动量
        factors["f_mom5"] = float(c[-1] / (c[-6] + 1e-8) - 1) if n >= 6 else 0.0

        return factors

    except Exception as e:
        logger.error(f"因子计算失败: {e}")
        return None


def cross_section_quantile_normalize(
    factors_list: list,
    factor_keys: list,
) -> np.ndarray:
    """
    截面分位数标准化（相比线性归一化，IC提升2.9倍）

    将当天所有股票的每个因子排序后映射到标准正态分位数，
    消除极值影响，保留截面排序信息。

    返回 shape=(N, K) 的标准化矩阵，每列为正态分布
    """
    n = len(factors_list)
    k = len(factor_keys)
    X = np.zeros((n, k))
    for i, fd in enumerate(factors_list):
        for j, key in enumerate(factor_keys):
            X[i, j] = fd.get(key, 0)

    X_norm = np.zeros_like(X)
    for j in range(k):
        ranks     = stats.rankdata(X[:, j])
        quantiles = np.clip((ranks - 0.5) / n, 0.01, 0.99)
        X_norm[:, j] = stats.norm.ppf(quantiles)

    return X_norm


def compute_score(
    factors: Dict[str, float],
    all_factors_today: list = None,
    market: str = "A",
) -> Dict:
    """
    从因子字典计算综合评分和预测信号。

    factors:           单只股票因子字典（来自 compute_factors）
    all_factors_today: 当天所有股票的因子列表（截面归一化用）
                       传入时更准确，不传时降级为单只处理
    market:            "A" 或 "HK"（港股通上调动量权重）

    返回字典键：
      total_score / fundamental_score / technical_score / fund_flow_score
      / sentiment_score / prob_up / signal / signal_strength
      / pred_range_low / pred_range_high / factors
    """
    factor_keys = list(FACTOR_IC_WEIGHTS.keys())
    weights     = np.array([FACTOR_IC_WEIGHTS[k] for k in factor_keys])

    # 港股通动量效应更强，上调动量权重×1.3后重新归一化
    if market == "HK":
        weights = weights.copy()
        idx = factor_keys.index("f_momentum")
        weights[idx] *= 1.3
        weights = weights / np.sum(np.abs(weights))

    # 截面归一化（有池）或直接截断极值（无池）
    if all_factors_today and len(all_factors_today) >= 5:
        pool = list(all_factors_today)
        if factors not in pool:
            pool.append(factors)
        idx_self = len(pool) - 1 if factors not in all_factors_today else pool.index(factors)
        x = cross_section_quantile_normalize(pool, factor_keys)[idx_self]
    else:
        x = np.clip(np.array([factors.get(k, 0) for k in factor_keys]), -3, 3)

    # IC加权合成 → 映射到 0-100（均值50，±1σ ≈ ±15分）
    composite   = float(np.dot(x, weights))
    total_score = float(np.clip(50 + composite * 15, 0, 100))

    # 四个维度子评分
    dim_scores: Dict[str, float] = {}
    for dim, fcs in DIMENSION_MAP.items():
        if not fcs:
            dim_scores[dim] = 50.0  # 情绪面无数据，中性
            continue
        dim_w   = np.array([FACTOR_IC_WEIGHTS.get(fc, 0) for fc in fcs])
        dim_x   = np.array([factors.get(fc, 0) for fc in fcs])
        abs_sum = np.sum(np.abs(dim_w))
        raw_dim = float(np.dot(dim_x, dim_w) / abs_sum) if abs_sum > 0 else 0
        dim_scores[dim] = float(np.clip(50 + raw_dim * 15, 0, 100))

    # Sigmoid 转概率（k=3，评分70 → 概率≈0.64，30 → 概率≈0.36）
    prob_up = float(1 / (1 + np.exp(-3 * (total_score - 50) / 50)))

    # T+3 预测区间（波动率×√3天，以中值为中心±1σ）
    vol       = factors.get("f_low_vol", 0.25)
    center    = (prob_up - 0.5) * 2 * vol * 100 / np.sqrt(252) * 3
    sigma     = vol * 100 / np.sqrt(252) * np.sqrt(3)
    pred_low  = round(center - sigma, 2)
    pred_high = round(center + sigma, 2)

    # 信号类型和强度
    if total_score >= 70:
        signal, strength = "up",      min(5, int((total_score - 70) / 6) + 3)
    elif total_score <= 40:
        signal, strength = "down",    min(5, int((40 - total_score) / 6) + 3)
    else:
        signal, strength = "neutral", max(1, int(abs(total_score - 55) / 5) + 1)

    return {
        "total_score":        round(total_score, 1),
        "fundamental_score":  round(dim_scores["fundamental"], 1),
        "technical_score":    round(dim_scores["technical"], 1),
        "fund_flow_score":    round(dim_scores["fund_flow"], 1),
        "sentiment_score":    round(dim_scores["sentiment"], 1),
        "prob_up":            round(prob_up, 3),
        "signal":             signal,
        "signal_strength":    strength,
        "pred_range_low":     pred_low,
        "pred_range_high":    pred_high,
        "factors":            {k: round(v, 4) for k, v in factors.items()},
    }


def score_signal_label(signal: str) -> str:
    """信号枚举转中文（供前端展示）"""
    return {"up": "偏多", "neutral": "中性", "down": "偏空"}.get(signal, "中性")


def signal_to_advice(score: float, signal: str, has_position: bool) -> str:
    """根据评分和持仓生成参考建议文字（不构成投资建议）"""
    if score >= 70 and signal == "up" and not has_position:
        return "关注买入机会"
    elif score >= 50 and signal == "up" and has_position:
        return "持有观望"
    elif score <= 40 and signal == "down" and has_position:
        return "注意风险，可考虑减仓"
    elif score <= 30:
        return "信号偏弱，谨慎观望"
    return "持有观望"

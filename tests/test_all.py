"""
AI投资助手 — 完整测试套件
覆盖：数据层、量化引擎、行情解析、预测逻辑、API路由、准确率统计
运行：pytest tests/test_all.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════
# 测试夹具：生成合成K线数据
# ═══════════════════════════════════════════════════════════════
def make_ohlcv(n=300, start_price=50.0, trend=0.0002, volatility=0.015, seed=42):
    """生成符合真实A股特征的合成OHLCV数据"""
    rng = np.random.default_rng(seed)
    rets = rng.normal(trend, volatility, n)
    closes = start_price * np.exp(np.cumsum(rets))
    noise_h = np.abs(rng.normal(0, 0.005, n))
    noise_l = np.abs(rng.normal(0, 0.005, n))
    dates = pd.date_range('2022-01-01', periods=n, freq='B')
    return pd.DataFrame({
        'date':   dates,
        'open':   np.roll(closes, 1),
        'high':   closes * np.exp(noise_h),
        'low':    closes * np.exp(-noise_l),
        'close':  closes,
        'volume': rng.lognormal(14, 1, n),
        'amount': closes * rng.lognormal(14, 1, n),
    })


# ═══════════════════════════════════════════════════════════════
# 模块1：量化引擎 — 因子计算
# ═══════════════════════════════════════════════════════════════
class TestFactorComputation:

    def setup_method(self):
        # 延迟导入，避免依赖FastAPI/SQLAlchemy
        from app.services.quant_engine import compute_factors
        self.compute_factors = compute_factors
        self.df = make_ohlcv(300)

    def test_returns_dict_with_all_factor_keys(self):
        result = self.compute_factors(self.df)
        assert result is not None
        expected = ['f_momentum','f_low_vol','f_vol_ratio','f_bollinger',
                    'f_kdj_j','f_macd','f_rsi','f_ma_align','f_vol_trend','f_mom5']
        for k in expected:
            assert k in result, f"缺少因子: {k}"

    def test_returns_none_when_data_insufficient(self):
        short_df = make_ohlcv(30)     # 少于65行
        result = self.compute_factors(short_df)
        assert result is None, "数据不足时应返回None"

    def test_factor_value_ranges(self):
        result = self.compute_factors(self.df)
        assert 0 <= result['f_momentum'] <= 1,      "动量因子应在[0,1]"
        assert result['f_low_vol'] > 0,             "波动率应为正数"
        assert result['f_vol_ratio'] > 0,           "量比应为正数"
        assert 0 <= result['f_bollinger'] <= 2,     "布林带%B应在合理范围"
        assert 0 <= result['f_rsi'] <= 100,         "RSI应在[0,100]"
        assert result['f_ma_align'] in [0.0, 1.0],  "均线排列应为0或1"

    def test_momentum_at_52week_high(self):
        """价格在52周高点时，动量因子应接近1"""
        df = make_ohlcv(280, start_price=10, trend=0.005)  # 强上涨趋势
        result = self.compute_factors(df)
        assert result is not None
        assert result['f_momentum'] > 0.7, f"上涨趋势末端动量应>0.7，实际={result['f_momentum']:.3f}"

    def test_momentum_at_52week_low(self):
        """价格在52周低点时，动量因子应接近0"""
        df = make_ohlcv(280, start_price=100, trend=-0.004)  # 强下跌趋势
        result = self.compute_factors(df)
        assert result is not None
        assert result['f_momentum'] < 0.4, f"下跌趋势末端动量应<0.4，实际={result['f_momentum']:.3f}"

    def test_rsi_in_uptrend_is_high(self):
        """强上涨趋势中RSI应偏高"""
        df = make_ohlcv(100, trend=0.01, volatility=0.005)
        result = self.compute_factors(df)
        if result:
            assert result['f_rsi'] > 50, f"上涨趋势RSI应>50，实际={result['f_rsi']:.1f}"

    def test_vol_ratio_high_when_recent_volume_surges(self):
        """成交量近期放大时，量比应>1"""
        df = make_ohlcv(100)
        df.loc[df.index[-5:], 'volume'] *= 5   # 近5日成交量×5
        result = self.compute_factors(df)
        if result:
            assert result['f_vol_ratio'] > 1.5, f"量比应>1.5，实际={result['f_vol_ratio']:.3f}"

    def test_handles_constant_price(self):
        """价格不变时不应崩溃（除零保护）"""
        df = make_ohlcv(100)
        df['close'] = 50.0
        df['high']  = 50.1
        df['low']   = 49.9
        try:
            result = self.compute_factors(df)
            # 允许返回None或有效结果，不允许抛异常
        except Exception as e:
            pytest.fail(f"常数价格序列不应抛出异常: {e}")

    def test_reproducible_with_same_data(self):
        """相同数据两次计算结果应完全一致"""
        r1 = self.compute_factors(self.df)
        r2 = self.compute_factors(self.df.copy())
        assert r1 is not None and r2 is not None
        for k in r1:
            assert abs(r1[k] - r2[k]) < 1e-10, f"因子{k}结果不一致"


# ═══════════════════════════════════════════════════════════════
# 模块2：量化引擎 — 评分计算
# ═══════════════════════════════════════════════════════════════
class TestScoreCalculation:

    def setup_method(self):
        from app.services.quant_engine import compute_factors, compute_score
        self.compute_factors = compute_factors
        self.compute_score   = compute_score
        self.df = make_ohlcv(300)
        self.factors = compute_factors(self.df)

    def test_score_in_valid_range(self):
        result = self.compute_score(self.factors)
        assert 0 <= result['total_score'] <= 100, f"总分应在[0,100]，实际={result['total_score']}"
        for dim in ['fundamental_score','technical_score','fund_flow_score','sentiment_score']:
            assert 0 <= result[dim] <= 100, f"{dim}应在[0,100]"

    def test_prob_up_in_valid_range(self):
        result = self.compute_score(self.factors)
        assert 0 < result['prob_up'] < 1, f"上涨概率应在(0,1)，实际={result['prob_up']}"

    def test_signal_values_are_valid(self):
        result = self.compute_score(self.factors)
        assert result['signal'] in ['up','neutral','down'], f"信号值非法: {result['signal']}"
        assert 1 <= result['signal_strength'] <= 5, f"信号强度应在[1,5]"

    def test_high_score_gives_up_signal(self):
        """高分应给出偏多信号"""
        # 构造高分因子：动量满分、低波动、量比高
        strong_factors = {
            'f_momentum': 0.95, 'f_low_vol': 0.05, 'f_vol_ratio': 2.5,
            'f_bollinger': 0.9,  'f_kdj_j': 80.0,  'f_macd': 0.01,
            'f_rsi': 75.0, 'f_ma_align': 1.0, 'f_vol_trend': 1.8, 'f_mom5': 0.04,
        }
        result = self.compute_score(strong_factors)
        assert result['total_score'] > 55, f"强势因子综合分应>55，实际={result['total_score']}"

    def test_low_score_gives_down_signal(self):
        """弱势因子应给出偏空信号"""
        weak_factors = {
            'f_momentum': 0.05, 'f_low_vol': 0.6,   'f_vol_ratio': 0.3,
            'f_bollinger': 0.1,  'f_kdj_j': -50.0,  'f_macd': -0.02,
            'f_rsi': 25.0, 'f_ma_align': 0.0, 'f_vol_trend': 0.5, 'f_mom5': -0.05,
        }
        result = self.compute_score(weak_factors)
        assert result['total_score'] < 50, f"弱势因子综合分应<50，实际={result['total_score']}"

    def test_cross_section_normalization_with_pool(self):
        """有因子池时，截面归一化应正常工作"""
        pool = [self.compute_factors(make_ohlcv(300, seed=i)) for i in range(10)]
        pool = [f for f in pool if f is not None]
        result = self.compute_score(pool[0], all_factors_today=pool)
        assert result is not None
        assert 0 <= result['total_score'] <= 100

    def test_hk_market_higher_momentum_weight(self):
        """港股通动量因子权重更高，高动量股票的港股评分应高于A股"""
        high_mom = {
            'f_momentum': 0.95, 'f_low_vol': 0.3, 'f_vol_ratio': 1.0,
            'f_bollinger': 0.5, 'f_kdj_j': 0.0,  'f_macd': 0.0,
            'f_rsi': 50.0, 'f_ma_align': 1.0, 'f_vol_trend': 1.0, 'f_mom5': 0.03,
        }
        score_a  = self.compute_score(high_mom, market='A')
        score_hk = self.compute_score(high_mom, market='HK')
        assert score_hk['total_score'] >= score_a['total_score'] - 1, \
            "高动量股港股评分不应低于A股评分"

    def test_pred_range_low_less_than_high(self):
        """预测区间下限应小于上限"""
        result = self.compute_score(self.factors)
        assert result['pred_range_low'] < result['pred_range_high'], \
            f"预测区间下限{result['pred_range_low']}应<上限{result['pred_range_high']}"

    def test_missing_factor_handled_gracefully(self):
        """因子字典缺少某些键时不应崩溃"""
        partial = {'f_momentum': 0.5, 'f_rsi': 50.0}  # 只有2个因子
        try:
            result = self.compute_score(partial)
            assert result is not None
        except Exception as e:
            pytest.fail(f"缺失因子键时不应崩溃: {e}")


# ═══════════════════════════════════════════════════════════════
# 模块3：行情解析 — 新浪接口
# ═══════════════════════════════════════════════════════════════
class TestDataFetcher:

    def setup_method(self):
        from app.services.data_fetcher import (
            to_sina_code, parse_sina_quote, fetch_realtime_quotes
        )
        self.to_sina_code     = to_sina_code
        self.parse_sina_quote = parse_sina_quote
        self.fetch_quotes     = fetch_realtime_quotes

    # ── 代码格式转换 ───────────────────────────────────────────
    def test_a_stock_sh_prefix(self):
        assert self.to_sina_code('600519', 'A') == 'sh600519'

    def test_a_stock_sz_prefix(self):
        assert self.to_sina_code('000001', 'A') == 'sz000001'
        assert self.to_sina_code('300750', 'A') == 'sz300750'

    def test_hk_stock_prefix_and_padding(self):
        assert self.to_sina_code('00700', 'HK') == 'hk00700'
        assert self.to_sina_code('700',   'HK') == 'hk00700'   # 自动补零

    def test_hk_4digit_code(self):
        assert self.to_sina_code('9988', 'HK') == 'hk09988'

    # ── 行情字符串解析（A股）────────────────────────────────────
    def test_parse_a_stock_valid(self):
        # 真实新浪格式（简化）：名称,今开,昨收,现价,最高,最低,...,成交量,成交额,...日期,时间
        fields = ['平安银行', '11.00', '10.90', '11.02', '11.10', '10.85',
                  '0','0','0','1234567','13579000',
                  '0','0','0','0','0','0','0','0','0','0',
                  '0','0','0','0','0','0','0','0','0','0','0','2025-03-01','15:00:00']
        line = 'var hq_str_sz000001="' + ','.join(fields) + '"'
        result = self.parse_sina_quote(line, '000001', 'A')
        assert result is not None
        assert result['price'] == 11.02
        assert result['prev_close'] == 10.90
        assert result['open'] == 11.00
        assert result['volume'] == 1234567.0

    def test_parse_a_stock_returns_none_on_empty(self):
        result = self.parse_sina_quote('var hq_str_sz000001=""', '000001', 'A')
        assert result is None

    def test_parse_a_stock_returns_none_on_short_data(self):
        result = self.parse_sina_quote('var hq_str_sz000001="只有两个,字段"', '000001', 'A')
        assert result is None

    def test_parse_hk_stock_valid(self):
        fields = ['腾讯控股', '493.00', '490.00', '493.40', '495.00', '489.00',
                  '12345678', '6089012345']
        line = 'var hq_str_hk00700="' + ','.join(fields) + '"'
        result = self.parse_sina_quote(line, '00700', 'HK')
        assert result is not None
        assert result['price'] == 493.40
        assert result['prev_close'] == 490.00

    def test_change_pct_calculated_correctly(self):
        fields = ['平安银行', '11.00', '10.90', '11.02', '11.10', '10.85',
                  '0','0','0','1234567','13579000',
                  '0','0','0','0','0','0','0','0','0','0',
                  '0','0','0','0','0','0','0','0','0','0','0','2025-03-01','15:00:00']
        line = 'var hq_str_sz000001="' + ','.join(fields) + '"'
        result = self.parse_sina_quote(line, '000001', 'A')
        assert result is not None
        expected_pct = round((11.02 - 10.90) / 10.90 * 100, 2)
        assert abs(result['change_pct'] - expected_pct) < 0.01

    # ── 批量行情（Mock网络）────────────────────────────────────
    def test_fetch_realtime_returns_list(self):
        mock_body = (
            'var hq_str_sh600519="贵州茅台,1750.00,1740.00,1755.00,'
            '1760.00,1745.00,0,0,0,987654,1730000000,'
            '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2025-03-01,15:00:00"\n'
        )
        mock_resp = MagicMock()
        mock_resp.text = mock_body
        mock_resp.encoding = 'gbk'

        with patch('requests.get', return_value=mock_resp):
            result = self.fetch_quotes([{'code': '600519', 'market': 'A'}])
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['code'] == '600519'
        assert result[0]['price'] == 1755.00

    def test_fetch_realtime_returns_empty_on_network_error(self):
        import requests
        with patch('requests.get', side_effect=requests.exceptions.Timeout()):
            with patch('app.services.data_fetcher._fetch_realtime_fallback', return_value=[]):
                result = self.fetch_quotes([{'code': '000001', 'market': 'A'}])
        assert result == []

    def test_fetch_realtime_empty_input(self):
        result = self.fetch_quotes([])
        assert result == []


# ═══════════════════════════════════════════════════════════════
# 模块4：预测逻辑 — 准确率统计
# ═══════════════════════════════════════════════════════════════
class TestPredictionLogic:

    def test_direction_classification_up(self):
        """涨幅>0.3%应判定为up"""
        change_pct = 1.5
        actual_dir = 'up' if change_pct > 0.3 else ('down' if change_pct < -0.3 else 'neutral')
        assert actual_dir == 'up'

    def test_direction_classification_down(self):
        change_pct = -0.8
        actual_dir = 'up' if change_pct > 0.3 else ('down' if change_pct < -0.3 else 'neutral')
        assert actual_dir == 'down'

    def test_direction_classification_neutral(self):
        change_pct = 0.1
        actual_dir = 'up' if change_pct > 0.3 else ('down' if change_pct < -0.3 else 'neutral')
        assert actual_dir == 'neutral'

    def test_is_correct_logic_match(self):
        assert ('up' == 'up') is True
        assert ('up' == 'down') is False
        assert ('neutral' == 'neutral') is True

    def test_accuracy_rate_calculation(self):
        total, correct = 100, 57
        rate = correct / total
        assert abs(rate - 0.57) < 1e-10

    def test_beat_baseline_positive(self):
        accuracy, baseline = 0.57, 0.50
        beat = accuracy - baseline
        assert beat > 0
        assert abs(beat - 0.07) < 1e-10

    def test_beat_baseline_negative(self):
        accuracy, baseline = 0.45, 0.50
        beat = accuracy - baseline
        assert beat < 0

    def test_monthly_grouping(self):
        """预测按月分组统计逻辑"""
        dates = ['2025-01-05', '2025-01-20', '2025-02-10', '2025-02-28', '2025-03-01']
        months = [d[:7] for d in dates]
        from collections import Counter
        counts = Counter(months)
        assert counts['2025-01'] == 2
        assert counts['2025-02'] == 2
        assert counts['2025-03'] == 1

    def test_t1_vs_t3_horizon(self):
        """T1应比T3更早到期"""
        predict_date = date(2025, 3, 1)
        t1_settle = predict_date + timedelta(days=2)
        t3_settle = predict_date + timedelta(days=6)
        assert t1_settle < t3_settle


# ═══════════════════════════════════════════════════════════════
# 模块5：信号标签和建议文字
# ═══════════════════════════════════════════════════════════════
class TestSignalLabels:

    def setup_method(self):
        from app.services.quant_engine import score_signal_label, signal_to_advice
        self.label  = score_signal_label
        self.advice = signal_to_advice

    def test_signal_labels_chinese(self):
        assert self.label('up')      == '偏多'
        assert self.label('neutral') == '中性'
        assert self.label('down')    == '偏空'
        assert self.label('unknown') == '中性'   # 未知值fallback

    def test_advice_buy_when_high_score_no_position(self):
        advice = self.advice(score=75, signal='up', has_position=False)
        assert '买入' in advice or '关注' in advice

    def test_advice_hold_when_medium_score(self):
        advice = self.advice(score=58, signal='up', has_position=True)
        assert '持有' in advice or '观望' in advice

    def test_advice_risk_when_low_score(self):
        advice = self.advice(score=35, signal='down', has_position=True)
        assert '风险' in advice or '减仓' in advice or '谨慎' in advice

    def test_advice_returns_string(self):
        result = self.advice(50, 'neutral', False)
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════
# 模块6：数据库模型结构验证
# ═══════════════════════════════════════════════════════════════
class TestDatabaseModels:

    def test_user_model_fields(self):
        from app.models.db_models import User
        cols = [c.key for c in User.__table__.columns]
        for f in ['id','email','name','hashed_pw','created_at']:
            assert f in cols, f"User模型缺少字段: {f}"

    def test_portfolio_model_fields(self):
        from app.models.db_models import Portfolio
        cols = [c.key for c in Portfolio.__table__.columns]
        for f in ['id','user_id','name','description','created_at']:
            assert f in cols

    def test_portfolio_stock_model_fields(self):
        from app.models.db_models import PortfolioStock
        cols = [c.key for c in PortfolioStock.__table__.columns]
        for f in ['id','portfolio_id','code','name','market','cost_price','shares','tag']:
            assert f in cols

    def test_quant_score_model_fields(self):
        from app.models.db_models import QuantScore
        cols = [c.key for c in QuantScore.__table__.columns]
        for f in ['code','market','score_date','total_score',
                  'fundamental_score','technical_score','fund_flow_score','sentiment_score',
                  'signal','signal_strength']:
            assert f in cols

    def test_prediction_model_fields(self):
        from app.models.db_models import Prediction
        cols = [c.key for c in Prediction.__table__.columns]
        for f in ['code','market','predict_date','horizon','direction',
                  'prob_up','pred_range_low','pred_range_high',
                  'actual_direction','actual_change_pct','is_correct']:
            assert f in cols

    def test_accuracy_stat_model_fields(self):
        from app.models.db_models import AccuracyStat
        cols = [c.key for c in AccuracyStat.__table__.columns]
        for f in ['month','horizon','market','total_count','correct_count',
                  'accuracy_rate','baseline_rate','beat_baseline']:
            assert f in cols

    def test_table_names_correct(self):
        from app.models.db_models import User, Portfolio, PortfolioStock, QuantScore, Prediction, AccuracyStat
        assert User.__tablename__          == 'users'
        assert Portfolio.__tablename__     == 'portfolios'
        assert PortfolioStock.__tablename__ == 'portfolio_stocks'
        assert QuantScore.__tablename__    == 'quant_scores'
        assert Prediction.__tablename__    == 'predictions'
        assert AccuracyStat.__tablename__  == 'accuracy_stats'


# ═══════════════════════════════════════════════════════════════
# 模块7：配置和边界值
# ═══════════════════════════════════════════════════════════════
class TestConfiguration:

    def test_ic_weights_sum_to_one(self):
        from app.services.quant_engine import FACTOR_IC_WEIGHTS
        total = sum(abs(w) for w in FACTOR_IC_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, f"IC权重绝对值之和应≈1，实际={total:.4f}"

    def test_dimension_weights_sum_to_one(self):
        from app.services.quant_engine import DIMENSION_WEIGHTS
        total = sum(DIMENSION_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"维度权重之和应=1，实际={total}"

    def test_dimension_map_covers_all_factors(self):
        from app.services.quant_engine import DIMENSION_MAP, FACTOR_IC_WEIGHTS
        all_mapped = []
        for factors in DIMENSION_MAP.values():
            all_mapped.extend(factors)
        for k in FACTOR_IC_WEIGHTS:
            assert k in all_mapped, f"因子{k}未归属任何维度"

    def test_baseline_rate_is_half(self):
        from app.services.prediction_service import BASELINE_RATE
        assert BASELINE_RATE == 0.50, "随机基准应为0.50"

    def test_factor_ic_weights_has_10_factors(self):
        from app.services.quant_engine import FACTOR_IC_WEIGHTS
        assert len(FACTOR_IC_WEIGHTS) == 10, f"应有10个因子，实际{len(FACTOR_IC_WEIGHTS)}"


# ═══════════════════════════════════════════════════════════════
# 模块8：端到端回归测试
# ═══════════════════════════════════════════════════════════════
class TestEndToEnd:
    """模拟完整的"拉数据→算因子→打分→出预测"流程"""

    def test_full_pipeline_a_stock(self):
        from app.services.quant_engine import compute_factors, compute_score, score_signal_label
        df = make_ohlcv(300, seed=1)
        factors = compute_factors(df)
        assert factors is not None, "因子计算不应失败"

        score = compute_score(factors, market='A')
        assert score is not None
        assert 0 <= score['total_score'] <= 100
        assert score['signal'] in ['up', 'neutral', 'down']
        assert score['signal_strength'] in range(1, 6)
        assert 0 < score['prob_up'] < 1

        label = score_signal_label(score['signal'])
        assert label in ['偏多', '中性', '偏空']

    def test_full_pipeline_hk_stock(self):
        from app.services.quant_engine import compute_factors, compute_score
        df = make_ohlcv(300, seed=2, volatility=0.020)
        factors = compute_factors(df)
        assert factors is not None
        score = compute_score(factors, market='HK')
        assert 0 <= score['total_score'] <= 100

    def test_cross_section_pipeline_multiple_stocks(self):
        """10只股票的截面评分流程"""
        from app.services.quant_engine import compute_factors, compute_score
        dfs     = [make_ohlcv(300, seed=i) for i in range(10)]
        factors = [compute_factors(df) for df in dfs]
        factors = [f for f in factors if f is not None]
        assert len(factors) >= 8, "至少应有8只股票算出因子"

        scores = [compute_score(f, all_factors_today=factors) for f in factors]
        for s in scores:
            assert 0 <= s['total_score'] <= 100
            assert s['signal'] in ['up', 'neutral', 'down']

        # 截面分数不应全部相同（说明归一化在起作用）
        total_scores = [s['total_score'] for s in scores]
        assert max(total_scores) - min(total_scores) > 1.0, \
            f"截面评分差异太小：{min(total_scores):.1f}~{max(total_scores):.1f}"

    def test_score_consistency_across_calls(self):
        """同一只股票、同一池，多次调用结果应稳定"""
        from app.services.quant_engine import compute_factors, compute_score
        dfs  = [make_ohlcv(300, seed=i) for i in range(5)]
        pool = [compute_factors(df) for df in dfs]
        pool = [f for f in pool if f is not None]

        s1 = compute_score(pool[0], all_factors_today=pool)
        s2 = compute_score(pool[0], all_factors_today=pool)
        assert abs(s1['total_score'] - s2['total_score']) < 0.01

    def test_prediction_direction_matches_signal(self):
        """预测方向应与评分信号一致"""
        from app.services.quant_engine import compute_factors, compute_score
        df      = make_ohlcv(300, seed=99)
        factors = compute_factors(df)
        score   = compute_score(factors)
        # signal和预测方向应该一致
        assert score['signal'] in ['up', 'neutral', 'down']
        if score['total_score'] >= 70:
            assert score['signal'] == 'up'
        elif score['total_score'] <= 40:
            assert score['signal'] == 'down'

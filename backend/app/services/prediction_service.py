"""
预测结算服务：到期后对比实际涨跌，更新准确率统计
"""
# ── 常量（无依赖，可独立导入）────────────────────────────────
BASELINE_RATE = 0.50   # 随机猜测基准（二分类期望准确率）

from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func
from app.models.db_models import Prediction, AccuracyStat
from app.services.data_fetcher import fetch_realtime_quotes
import logging

logger = logging.getLogger(__name__)

async def settle_predictions(db: AsyncSession):
    """
    结算到期预测：
    - T1预测：发出后1个交易日后结算
    - T3预测：发出后3个交易日后结算
    """
    today = date.today().strftime("%Y-%m-%d")
    settled_count = 0

    # 查询所有未结算预测
    unsettled = await db.execute(
        select(Prediction).where(Prediction.is_correct.is_(None))
    )
    predictions = unsettled.scalars().all()

    # 按股票分组批量拉行情
    stock_set = {(p.code, p.market) for p in predictions}
    if not stock_set:
        return 0

    quotes = fetch_realtime_quotes([{"code": c, "market": m} for c, m in stock_set])
    quote_map = {q["code"]: q for q in quotes}

    for pred in predictions:
        predict_dt = datetime.strptime(pred.predict_date, "%Y-%m-%d").date()
        days_needed = 1 if pred.horizon == "T1" else 3
        settle_date = predict_dt + timedelta(days=days_needed * 2)  # 保守估计（含周末）

        if date.today() < settle_date:
            continue

        q = quote_map.get(pred.code)
        if not q:
            continue

        # 用当前价计算实际涨跌幅（相对于预测发出日收盘价的近似值）
        # 精确做法是记录预测日收盘价，这里用 prev_close 近似
        actual_pct = q.get("change_pct", 0)
        actual_dir = "up" if actual_pct > 0.3 else ("down" if actual_pct < -0.3 else "neutral")
        is_correct = pred.direction == actual_dir

        await db.execute(
            update(Prediction)
            .where(Prediction.id == pred.id)
            .values(
                actual_direction=actual_dir,
                actual_change_pct=actual_pct,
                is_correct=is_correct,
                settled_at=datetime.now(),
            )
        )
        settled_count += 1

    await db.commit()

    if settled_count > 0:
        await update_accuracy_stats(db)

    logger.info(f"结算预测 {settled_count} 条")
    return settled_count


async def update_accuracy_stats(db: AsyncSession):
    """重新计算并更新月度准确率统计"""
    # 查询所有已结算预测
    result = await db.execute(
        select(
            func.substr(Prediction.predict_date, 1, 7).label("month"),
            Prediction.horizon,
            Prediction.market,
            func.count(Prediction.id).label("total"),
            func.sum(Prediction.is_correct.cast(int)).label("correct"),
        )
        .where(Prediction.is_correct.isnot(None))
        .group_by("month", Prediction.horizon, Prediction.market)
    )
    rows = result.all()

    for row in rows:
        month, horizon, market, total, correct = row
        correct = correct or 0
        accuracy = correct / total if total > 0 else 0
        beat = accuracy - BASELINE_RATE

        # upsert
        existing = await db.execute(
            select(AccuracyStat).where(
                and_(
                    AccuracyStat.month == month,
                    AccuracyStat.horizon == horizon,
                    AccuracyStat.market == market,
                )
            )
        )
        stat = existing.scalar_one_or_none()
        if stat:
            stat.total_count   = total
            stat.correct_count = correct
            stat.accuracy_rate = round(accuracy, 4)
            stat.beat_baseline = round(beat, 4)
        else:
            db.add(AccuracyStat(
                month=month, horizon=horizon, market=market,
                total_count=total, correct_count=correct,
                accuracy_rate=round(accuracy, 4),
                baseline_rate=BASELINE_RATE,
                beat_baseline=round(beat, 4),
            ))

    # 全市场汇总（ALL）
    result_all = await db.execute(
        select(
            func.substr(Prediction.predict_date, 1, 7).label("month"),
            Prediction.horizon,
            func.count(Prediction.id).label("total"),
            func.sum(Prediction.is_correct.cast(int)).label("correct"),
        )
        .where(Prediction.is_correct.isnot(None))
        .group_by("month", Prediction.horizon)
    )
    for row in result_all.all():
        month, horizon, total, correct = row
        correct = correct or 0
        accuracy = correct / total if total > 0 else 0
        existing = await db.execute(
            select(AccuracyStat).where(
                and_(
                    AccuracyStat.month == month,
                    AccuracyStat.horizon == horizon,
                    AccuracyStat.market == "ALL",
                )
            )
        )
        stat = existing.scalar_one_or_none()
        if stat:
            stat.total_count   = total
            stat.correct_count = correct
            stat.accuracy_rate = round(accuracy, 4)
            stat.beat_baseline = round(accuracy - BASELINE_RATE, 4)
        else:
            db.add(AccuracyStat(
                month=month, horizon=horizon, market="ALL",
                total_count=total, correct_count=correct,
                accuracy_rate=round(accuracy, 4),
                baseline_rate=BASELINE_RATE,
                beat_baseline=round(accuracy - BASELINE_RATE, 4),
            ))

    await db.commit()


async def get_accuracy_summary(db: AsyncSession) -> dict:
    """
    获取准确率总览（供前端展示）
    包含：总体准确率、vs基准、分时间维度、分市场
    """
    result = await db.execute(
        select(AccuracyStat).where(AccuracyStat.market == "ALL")
        .order_by(AccuracyStat.month.desc())
    )
    stats = result.scalars().all()

    if not stats:
        return {
            "overall_accuracy": None,
            "baseline": BASELINE_RATE,
            "beat_baseline": None,
            "total_predictions": 0,
            "by_horizon": {},
            "monthly_trend": [],
        }

    # 全部汇总
    total_all   = sum(s.total_count for s in stats)
    correct_all = sum(s.correct_count for s in stats)
    overall_acc = correct_all / total_all if total_all > 0 else 0

    # 按horizon分组
    by_horizon = {}
    for h in ["T1", "T3"]:
        h_stats = [s for s in stats if s.horizon == h]
        t = sum(s.total_count for s in h_stats)
        c = sum(s.correct_count for s in h_stats)
        by_horizon[h] = {
            "accuracy": round(c / t, 4) if t > 0 else None,
            "count": t,
            "beat_baseline": round(c / t - BASELINE_RATE, 4) if t > 0 else None,
        }

    # 月度趋势（最近12个月）
    monthly = {}
    for s in stats:
        key = s.month
        if key not in monthly:
            monthly[key] = {"total": 0, "correct": 0}
        monthly[key]["total"]   += s.total_count
        monthly[key]["correct"] += s.correct_count

    monthly_trend = [
        {
            "month": k,
            "accuracy": round(v["correct"] / v["total"], 4) if v["total"] > 0 else None,
            "count": v["total"],
            "baseline": BASELINE_RATE,
        }
        for k, v in sorted(monthly.items())[-12:]
    ]

    return {
        "overall_accuracy": round(overall_acc, 4),
        "baseline": BASELINE_RATE,
        "beat_baseline": round(overall_acc - BASELINE_RATE, 4),
        "total_predictions": total_all,
        "correct_predictions": correct_all,
        "by_horizon": by_horizon,
        "monthly_trend": monthly_trend,
    }

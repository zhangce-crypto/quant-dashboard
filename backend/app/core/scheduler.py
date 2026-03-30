"""
后台定时任务：
- 交易时间每5分钟刷新评分缓存
- 收盘后结算预测、更新准确率
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.db_models import PortfolioStock, QuantScore
from app.services.data_fetcher import fetch_history
from app.services.quant_engine import compute_factors, compute_score
from app.services.prediction_service import settle_predictions
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

async def refresh_all_scores():
    """为所有自选股重新计算量化评分（交易时间每30分钟一次）"""
    today = date.today().strftime("%Y-%m-%d")
    weekday = date.today().weekday()
    if weekday >= 5:  # 周末跳过
        return

    logger.info("开始刷新量化评分...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(PortfolioStock.code, PortfolioStock.market).distinct())
        stocks = result.all()

        all_factors = []
        stock_map = []
        for code, market in stocks:
            hist = fetch_history(code, market, days=400)
            if hist.empty:
                continue
            f = compute_factors(hist)
            if f:
                all_factors.append(f)
                stock_map.append((code, market))

        for i, (code, market) in enumerate(stock_map):
            score = compute_score(all_factors[i], all_factors_today=all_factors, market=market)
            # 更新或插入今日评分
            existing = await db.execute(select(QuantScore).where(
                QuantScore.code == code, QuantScore.score_date == today))
            qs = existing.scalar_one_or_none()
            if qs:
                qs.total_score       = score["total_score"]
                qs.fundamental_score = score["fundamental_score"]
                qs.technical_score   = score["technical_score"]
                qs.fund_flow_score   = score["fund_flow_score"]
                qs.sentiment_score   = score["sentiment_score"]
                qs.signal            = score["signal"]
                qs.signal_strength   = score["signal_strength"]
            else:
                db.add(QuantScore(
                    code=code, market=market, score_date=today,
                    total_score=score["total_score"],
                    fundamental_score=score["fundamental_score"],
                    technical_score=score["technical_score"],
                    fund_flow_score=score["fund_flow_score"],
                    sentiment_score=score["sentiment_score"],
                    signal=score["signal"],
                    signal_strength=score["signal_strength"],
                ))

        await db.commit()
        logger.info(f"评分刷新完成，{len(stock_map)} 只股票")

async def settle_job():
    """收盘后结算预测（每个工作日15:30执行）"""
    async with AsyncSessionLocal() as db:
        n = await settle_predictions(db)
        logger.info(f"预测结算完成，{n} 条")

def start_scheduler():
    # 交易时间每30分钟刷新评分 (9:30-15:00)
    scheduler.add_job(
        refresh_all_scores, CronTrigger(
            day_of_week="mon-fri",
            hour="9-14", minute="0,30",
            timezone="Asia/Shanghai"
        ), id="refresh_scores", replace_existing=True
    )
    # 收盘后结算预测
    scheduler.add_job(
        settle_job, CronTrigger(
            day_of_week="mon-fri", hour=15, minute=35,
            timezone="Asia/Shanghai"
        ), id="settle_predictions", replace_existing=True
    )
    scheduler.start()
    logger.info("定时任务已启动")

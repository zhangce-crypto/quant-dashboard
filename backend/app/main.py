"""
AI投资助手 —— FastAPI 后端主入口 V2.0
改动：搜索用内存、懒评分、自动预测、注册建默认组合、准确率分类API
"""
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
import asyncio, logging

from app.core.config import settings
from app.core.scheduler import start_scheduler
from app.db.session import get_db, init_db
from app.models.db_models import User, Portfolio, PortfolioStock, QuantScore, Prediction, AccuracyStat
from app.services.data_fetcher import (
    fetch_realtime_quotes, fetch_index_quotes, fetch_history,
    search_a_stocks, search_hk_stocks, preload_a_stock_table, fetch_hk_stock_name,
)
from app.services.quant_engine import compute_factors, compute_score, score_signal_label, signal_to_advice
from app.services.prediction_service import get_accuracy_summary, settle_predictions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI投资助手 API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"], expose_headers=["*"], max_age=3600,
)

@app.on_event("startup")
async def startup():
    await init_db()
    start_scheduler()
    preload_a_stock_table()

@app.get("/")
async def health_check():
    return {"status": "ok", "message": "AI投资助手 API V2.0 运行正常"}

# ═══════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2  = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def create_token(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.SECRET_KEY, algorithm="HS256")

async def current_user(token: str = Depends(oauth2), db: AsyncSession = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token无效")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user: raise HTTPException(status_code=401, detail="用户不存在")
    return user

class RegisterReq(BaseModel):
    email: str; name: str; password: str
class TokenResp(BaseModel):
    access_token: str; token_type: str = "bearer"; user_name: str; user_id: str
class PortfolioCreate(BaseModel):
    name: str; description: str = ""
class StockAdd(BaseModel):
    code: str; name: str; market: str
    cost_price: Optional[float] = None; shares: Optional[float] = None; tag: str = ""

# ═══════════════════════════════════════════════════════════════
# Auth Routes
# ═══════════════════════════════════════════════════════════════
@app.post("/api/auth/register", response_model=TokenResp)
async def register(req: RegisterReq, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "邮箱已注册")
    user = User(email=req.email, name=req.name, hashed_pw=pwd_ctx.hash(req.password))
    db.add(user)
    await db.flush()
    # V2.0: 自动创建默认组合
    db.add(Portfolio(user_id=user.id, name="我的观测", description="默认组合"))
    await db.commit()
    await db.refresh(user)
    token = create_token(user.id)
    return TokenResp(access_token=token, user_name=user.name, user_id=user.id)

@app.post("/api/auth/login", response_model=TokenResp)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not pwd_ctx.verify(form.password, user.hashed_pw):
        raise HTTPException(401, "邮箱或密码错误")
    token = create_token(user.id)
    return TokenResp(access_token=token, user_name=user.name, user_id=user.id)

@app.get("/api/auth/me")
async def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}

# ═══════════════════════════════════════════════════════════════
# Portfolio Routes
# ═══════════════════════════════════════════════════════════════
@app.get("/api/portfolios")
async def list_portfolios(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.user_id == user.id))
    return [{"id": p.id, "name": p.name, "description": p.description, "created_at": p.created_at}
            for p in result.scalars().all()]

@app.post("/api/portfolios", status_code=201)
async def create_portfolio(req: PortfolioCreate, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    p = Portfolio(user_id=user.id, name=req.name, description=req.description)
    db.add(p); await db.commit(); await db.refresh(p)
    return {"id": p.id, "name": p.name}

@app.delete("/api/portfolios/{pid}")
async def delete_portfolio(pid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    p = result.scalar_one_or_none()
    if not p: raise HTTPException(404, "组合不存在")
    await db.delete(p); await db.commit()
    return {"ok": True}

@app.post("/api/portfolios/{pid}/stocks", status_code=201)
async def add_stock(pid: str, req: StockAdd, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    if not result.scalar_one_or_none(): raise HTTPException(404, "组合不存在")
    dup = await db.execute(select(PortfolioStock).where(PortfolioStock.portfolio_id == pid, PortfolioStock.code == req.code))
    if dup.scalar_one_or_none(): raise HTTPException(400, "股票已在组合中")
    s = PortfolioStock(portfolio_id=pid, code=req.code, name=req.name, market=req.market,
                       cost_price=req.cost_price, shares=req.shares, tag=req.tag)
    db.add(s); await db.commit(); await db.refresh(s)
    # V2.0: 自动触发评分和预测（后台异步）
    asyncio.create_task(_auto_score_and_predict(req.code, req.market))
    return {"id": s.id, "code": s.code, "name": s.name}

async def _auto_score_and_predict(code: str, market: str):
    """后台异步计算评分和预测"""
    try:
        from app.db.session import AsyncSessionLocal
        history = fetch_history(code, market, days=400)
        if history.empty: return
        factors = compute_factors(history)
        if not factors: return
        score_result = compute_score(factors, market=market)
        today = datetime.now().strftime("%Y-%m-%d")
        async with AsyncSessionLocal() as db:
            dup = await db.execute(select(QuantScore).where(QuantScore.code == code, QuantScore.score_date == today))
            if not dup.scalar_one_or_none():
                db.add(QuantScore(code=code, market=market, score_date=today,
                    total_score=score_result["total_score"],
                    fundamental_score=score_result["fundamental_score"],
                    technical_score=score_result["technical_score"],
                    fund_flow_score=score_result["fund_flow_score"],
                    sentiment_score=score_result["sentiment_score"],
                    signal=score_result["signal"], signal_strength=score_result["signal_strength"]))
            for horizon in ["T1", "T3"]:
                dup2 = await db.execute(select(Prediction).where(
                    Prediction.code == code, Prediction.predict_date == today, Prediction.horizon == horizon))
                if not dup2.scalar_one_or_none():
                    db.add(Prediction(code=code, market=market, predict_date=today, horizon=horizon,
                        direction=score_result["signal"], signal_strength=score_result["signal_strength"],
                        prob_up=score_result["prob_up"],
                        pred_range_low=score_result["pred_range_low"], pred_range_high=score_result["pred_range_high"]))
            await db.commit()
        logger.info(f"自动评分完成: {code}")
    except Exception as e:
        logger.error(f"自动评分失败 {code}: {e}")

@app.delete("/api/portfolios/{pid}/stocks/{sid}")
async def remove_stock(pid: str, sid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    if not result.scalar_one_or_none(): raise HTTPException(404, "组合不存在")
    s_res = await db.execute(select(PortfolioStock).where(PortfolioStock.id == sid, PortfolioStock.portfolio_id == pid))
    s = s_res.scalar_one_or_none()
    if not s: raise HTTPException(404, "持股记录不存在")
    await db.delete(s); await db.commit()
    return {"ok": True}

# ═══════════════════════════════════════════════════════════════
# Market Data Routes
# ═══════════════════════════════════════════════════════════════
@app.get("/api/market/quotes/{pid}")
async def portfolio_quotes(pid: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    port = result.scalar_one_or_none()
    if not port: raise HTTPException(404, "组合不存在")
    stocks_res = await db.execute(select(PortfolioStock).where(PortfolioStock.portfolio_id == pid))
    stocks = stocks_res.scalars().all()
    if not stocks: return {"stocks": [], "index": {}}

    quotes = fetch_realtime_quotes([{"code": s.code, "market": s.market} for s in stocks])
    quote_map = {q["code"]: q for q in quotes}

    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    scores_res = await db.execute(select(QuantScore).where(
        QuantScore.code.in_([s.code for s in stocks]), QuantScore.score_date == today))
    score_map = {s.code: s for s in scores_res.scalars().all()}

    # V2.0: 查今日预测
    preds_res = await db.execute(select(Prediction).where(
        Prediction.code.in_([s.code for s in stocks]), Prediction.predict_date == today))
    preds_all = preds_res.scalars().all()
    pred_map = {}
    for p in preds_all:
        pred_map.setdefault(p.code, {})[p.horizon] = p

    # V2.0: 懒评分 - 对无评分的股票触发后台计算
    needs_score = [s for s in stocks if s.code not in score_map]
    for s in needs_score:
        asyncio.create_task(_auto_score_and_predict(s.code, s.market))

    items = []
    for s in stocks:
        q = quote_map.get(s.code, {})
        sc = score_map.get(s.code)
        preds = pred_map.get(s.code, {})
        t1 = preds.get("T1")
        t3 = preds.get("T3")
        profit_pct = None
        if s.cost_price and q.get("price"):
            profit_pct = round((q["price"] - s.cost_price) / s.cost_price * 100, 2)
        # 用行情接口的名称更新（更准确）
        display_name = q.get("name") or s.name
        items.append({
            "id": s.id, "code": s.code, "name": display_name,
            "market": s.market, "tag": s.tag,
            "price": q.get("price"), "change_pct": q.get("change_pct"),
            "change_amt": q.get("change_amt"), "volume": q.get("volume"),
            "high": q.get("high"), "low": q.get("low"), "open": q.get("open"),
            "prev_close": q.get("prev_close"),
            "cost_price": s.cost_price, "shares": s.shares, "profit_pct": profit_pct,
            "total_score": sc.total_score if sc else None,
            "signal": sc.signal if sc else None,
            "signal_strength": sc.signal_strength if sc else None,
            "t1_prob_up": t1.prob_up if t1 else None,
            "t3_prob_up": t3.prob_up if t3 else None,
            "t1_range_low": t1.pred_range_low if t1 else None,
            "t1_range_high": t1.pred_range_high if t1 else None,
            "t3_range_low": t3.pred_range_low if t3 else None,
            "t3_range_high": t3.pred_range_high if t3 else None,
        })
    index = fetch_index_quotes()
    return {"stocks": items, "index": index}

@app.get("/api/market/stock/{code}/analysis")
async def stock_analysis(code: str, market: str = "A", user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    history = fetch_history(code, market, days=400)
    if history.empty: raise HTTPException(503, "行情数据获取失败，请稍后重试")
    factors = compute_factors(history)
    if not factors: raise HTTPException(422, "数据不足，无法计算因子")
    score_result = compute_score(factors, market=market)

    # V2.0: 获取股票名称
    quotes = fetch_realtime_quotes([{"code": code, "market": market}])
    stock_name = quotes[0]["name"] if quotes else code

    pred_res = await db.execute(
        select(Prediction).where(Prediction.code == code)
        .order_by(Prediction.created_at.desc()).limit(10))
    recent_preds = pred_res.scalars().all()

    return {
        "code": code, "market": market, "name": stock_name,
        "score": score_result,
        "signal_label": score_signal_label(score_result["signal"]),
        "advice": signal_to_advice(score_result["total_score"], score_result["signal"], False),
        "recent_predictions": [
            {"predict_date": p.predict_date, "horizon": p.horizon,
             "direction": p.direction, "prob_up": p.prob_up,
             "signal_strength": p.signal_strength,
             "pred_range_low": p.pred_range_low, "pred_range_high": p.pred_range_high,
             "is_correct": p.is_correct, "actual_change_pct": p.actual_change_pct, "ai_summary": p.ai_summary}
            for p in recent_preds],
        "history_dates":  history["date"].dt.strftime("%Y-%m-%d").tolist()[-60:],
        "history_close":  [round(v, 2) for v in history["close"].tolist()[-60:]],
        "history_volume": [int(v) for v in history["volume"].tolist()[-60:]],
    }

@app.post("/api/market/stock/{code}/predict")
async def create_prediction(code: str, market: str = "A", user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    history = fetch_history(code, market, days=400)
    if history.empty: raise HTTPException(503, "行情数据获取失败")
    factors = compute_factors(history)
    if not factors: raise HTTPException(422, "数据不足")
    score_result = compute_score(factors, market=market)
    today = datetime.now().strftime("%Y-%m-%d")
    preds = []
    for horizon in ["T1", "T3"]:
        dup = await db.execute(select(Prediction).where(
            Prediction.code == code, Prediction.predict_date == today, Prediction.horizon == horizon))
        if dup.scalar_one_or_none(): continue
        db.add(Prediction(code=code, market=market, predict_date=today, horizon=horizon,
            direction=score_result["signal"], signal_strength=score_result["signal_strength"],
            prob_up=score_result["prob_up"],
            pred_range_low=score_result["pred_range_low"], pred_range_high=score_result["pred_range_high"]))
        preds.append(horizon)
    dup_score = await db.execute(select(QuantScore).where(QuantScore.code == code, QuantScore.score_date == today))
    if not dup_score.scalar_one_or_none():
        db.add(QuantScore(code=code, market=market, score_date=today,
            total_score=score_result["total_score"],
            fundamental_score=score_result["fundamental_score"],
            technical_score=score_result["technical_score"],
            fund_flow_score=score_result["fund_flow_score"],
            sentiment_score=score_result["sentiment_score"],
            signal=score_result["signal"], signal_strength=score_result["signal_strength"]))
    await db.commit()
    return {"ok": True, "created_horizons": preds, "score": score_result}

# ═══════════════════════════════════════════════════════════════
# Accuracy Routes
# ═══════════════════════════════════════════════════════════════
@app.get("/api/accuracy")
async def accuracy_summary(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await get_accuracy_summary(db)

@app.get("/api/accuracy/history/{code}")
async def stock_prediction_history(code: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Prediction).where(Prediction.code == code).order_by(Prediction.created_at.desc()).limit(30))
    return [{"predict_date": p.predict_date, "horizon": p.horizon, "direction": p.direction,
             "prob_up": p.prob_up, "signal_strength": p.signal_strength,
             "pred_range_low": p.pred_range_low, "pred_range_high": p.pred_range_high,
             "is_correct": p.is_correct, "actual_direction": p.actual_direction,
             "actual_change_pct": p.actual_change_pct, "settled_at": p.settled_at, "ai_summary": p.ai_summary}
            for p in result.scalars().all()]

@app.get("/api/accuracy/by-stock")
async def accuracy_by_stock(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """V2.0: 按个股统计准确率"""
    from sqlalchemy import func, and_, case
    result = await db.execute(
        select(
            Prediction.code, Prediction.market,
            func.count(Prediction.id).label("total"),
            func.sum(case((Prediction.is_correct == True, 1), else_=0)).label("correct"),
            func.sum(case((and_(Prediction.horizon == "T1", Prediction.is_correct == True), 1), else_=0)).label("t1_correct"),
            func.sum(case((Prediction.horizon == "T1", 1), else_=0)).label("t1_total"),
            func.sum(case((and_(Prediction.horizon == "T3", Prediction.is_correct == True), 1), else_=0)).label("t3_correct"),
            func.sum(case((Prediction.horizon == "T3", 1), else_=0)).label("t3_total"),
        ).where(Prediction.is_correct.isnot(None))
        .group_by(Prediction.code, Prediction.market)
    )
    rows = result.all()
    # 查名称
    codes = [r[0] for r in rows]
    stocks_res = await db.execute(select(PortfolioStock.code, PortfolioStock.name).where(
        PortfolioStock.code.in_(codes)).distinct())
    name_map = {r[0]: r[1] for r in stocks_res.all()}

    return [
        {"code": r[0], "market": r[1], "name": name_map.get(r[0], r[0]),
         "total": r[2], "correct": r[3] or 0,
         "accuracy": round((r[3] or 0) / r[2], 4) if r[2] > 0 else None,
         "t1_accuracy": round((r[4] or 0) / r[5], 4) if r[5] and r[5] > 0 else None,
         "t1_total": r[5] or 0,
         "t3_accuracy": round((r[6] or 0) / r[7], 4) if r[7] and r[7] > 0 else None,
         "t3_total": r[7] or 0,
         "beat_baseline": round((r[3] or 0) / r[2] - 0.5, 4) if r[2] > 0 else None}
        for r in rows
    ]

@app.get("/api/accuracy/by-category")
async def accuracy_by_category(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """V2.0: 按市场和信号强度统计准确率"""
    from sqlalchemy import func, case
    # 按市场
    by_market = await db.execute(
        select(Prediction.market,
               func.count(Prediction.id).label("total"),
               func.sum(case((Prediction.is_correct == True, 1), else_=0)).label("correct"))
        .where(Prediction.is_correct.isnot(None)).group_by(Prediction.market))
    markets = [{"market": r[0], "total": r[1], "correct": r[2] or 0,
                "accuracy": round((r[2] or 0) / r[1], 4) if r[1] > 0 else None}
               for r in by_market.all()]
    # 按信号强度
    by_strength = await db.execute(
        select(Prediction.signal_strength,
               func.count(Prediction.id).label("total"),
               func.sum(case((Prediction.is_correct == True, 1), else_=0)).label("correct"))
        .where(Prediction.is_correct.isnot(None)).group_by(Prediction.signal_strength)
        .order_by(Prediction.signal_strength.desc()))
    strengths = [{"strength": r[0], "total": r[1], "correct": r[2] or 0,
                  "accuracy": round((r[2] or 0) / r[1], 4) if r[1] > 0 else None}
                 for r in by_strength.all()]
    return {"by_market": markets, "by_strength": strengths}

# ═══════════════════════════════════════════════════════════════
# Search (V2.0: 内存查询，<100ms)
# ═══════════════════════════════════════════════════════════════
@app.get("/api/search")
async def search_stock(q: str, market: str = "A", user: User = Depends(current_user)):
    if market == "HK":
        return search_hk_stocks(q)
    else:
        return search_a_stocks(q.strip())

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}

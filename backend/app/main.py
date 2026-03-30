"""
AI投资助手 —— FastAPI 后端主入口
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
from pydantic import BaseModel, EmailStr
import logging

from app.core.config import settings
from app.db.session import get_db, init_db
from app.models.db_models import User, Portfolio, PortfolioStock, QuantScore, Prediction, AccuracyStat
from app.services.data_fetcher import fetch_realtime_quotes, fetch_index_quotes, fetch_history
from app.services.quant_engine import compute_factors, compute_score, score_signal_label, signal_to_advice
from app.services.prediction_service import get_accuracy_summary, settle_predictions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI投资助手 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_db()

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
    user   = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user

# ── Pydantic Schemas ───────────────────────────────────────────
class RegisterReq(BaseModel):
    email: str
    name: str
    password: str

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    user_id: str

class PortfolioCreate(BaseModel):
    name: str
    description: str = ""

class StockAdd(BaseModel):
    code: str
    name: str
    market: str          # A / HK
    cost_price: Optional[float] = None
    shares: Optional[float] = None
    tag: str = ""

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
    await db.commit()
    await db.refresh(user)
    token = create_token(user.id)
    return TokenResp(access_token=token, user_name=user.name, user_id=user.id)

@app.post("/api/auth/login", response_model=TokenResp)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user   = result.scalar_one_or_none()
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
    ports  = result.scalars().all()
    return [{"id": p.id, "name": p.name, "description": p.description,
             "created_at": p.created_at} for p in ports]

@app.post("/api/portfolios", status_code=201)
async def create_portfolio(req: PortfolioCreate, user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    p = Portfolio(user_id=user.id, name=req.name, description=req.description)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "name": p.name}

@app.delete("/api/portfolios/{pid}")
async def delete_portfolio(pid: str, user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "组合不存在")
    await db.delete(p)
    await db.commit()
    return {"ok": True}

@app.post("/api/portfolios/{pid}/stocks", status_code=201)
async def add_stock(pid: str, req: StockAdd, user: User = Depends(current_user),
                    db: AsyncSession = Depends(get_db)):
    # 验证组合归属
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "组合不存在")
    # 检查是否已存在
    dup = await db.execute(select(PortfolioStock).where(
        PortfolioStock.portfolio_id == pid, PortfolioStock.code == req.code))
    if dup.scalar_one_or_none():
        raise HTTPException(400, "股票已在组合中")
    s = PortfolioStock(
        portfolio_id=pid, code=req.code, name=req.name, market=req.market,
        cost_price=req.cost_price, shares=req.shares, tag=req.tag,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return {"id": s.id, "code": s.code, "name": s.name}

@app.delete("/api/portfolios/{pid}/stocks/{sid}")
async def remove_stock(pid: str, sid: str, user: User = Depends(current_user),
                       db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "组合不存在")
    s_res = await db.execute(select(PortfolioStock).where(
        PortfolioStock.id == sid, PortfolioStock.portfolio_id == pid))
    s = s_res.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "持股记录不存在")
    await db.delete(s)
    await db.commit()
    return {"ok": True}

# ═══════════════════════════════════════════════════════════════
# Market Data Routes
# ═══════════════════════════════════════════════════════════════
@app.get("/api/market/quotes/{pid}")
async def portfolio_quotes(pid: str, user: User = Depends(current_user),
                           db: AsyncSession = Depends(get_db)):
    """获取组合内所有股票实时行情 + 最新评分"""
    result = await db.execute(select(Portfolio).where(Portfolio.id == pid, Portfolio.user_id == user.id))
    port = result.scalar_one_or_none()
    if not port:
        raise HTTPException(404, "组合不存在")

    stocks_res = await db.execute(select(PortfolioStock).where(PortfolioStock.portfolio_id == pid))
    stocks = stocks_res.scalars().all()
    if not stocks:
        return {"stocks": [], "index": {}}

    # 批量拉行情
    quotes = fetch_realtime_quotes([{"code": s.code, "market": s.market} for s in stocks])
    quote_map = {q["code"]: q for q in quotes}

    # 查最新评分
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")
    scores_res = await db.execute(
        select(QuantScore).where(
            QuantScore.code.in_([s.code for s in stocks]),
            QuantScore.score_date == today,
        )
    )
    score_map = {s.code: s for s in scores_res.scalars().all()}

    items = []
    for s in stocks:
        q = quote_map.get(s.code, {})
        sc = score_map.get(s.code)
        profit_pct = None
        if s.cost_price and q.get("price"):
            profit_pct = round((q["price"] - s.cost_price) / s.cost_price * 100, 2)
        items.append({
            "id": s.id, "code": s.code, "name": s.name,
            "market": s.market, "tag": s.tag,
            "price": q.get("price"), "change_pct": q.get("change_pct"),
            "change_amt": q.get("change_amt"), "volume": q.get("volume"),
            "high": q.get("high"), "low": q.get("low"), "open": q.get("open"),
            "prev_close": q.get("prev_close"),
            "cost_price": s.cost_price, "shares": s.shares,
            "profit_pct": profit_pct,
            "total_score": sc.total_score if sc else None,
            "signal": sc.signal if sc else None,
            "signal_strength": sc.signal_strength if sc else None,
        })

    index = fetch_index_quotes()
    return {"stocks": items, "index": index}

@app.get("/api/market/stock/{code}/analysis")
async def stock_analysis(code: str, market: str = "A",
                         user: User = Depends(current_user),
                         db: AsyncSession = Depends(get_db)):
    """单只股票完整分析：因子评分 + 最新预测"""
    # 历史数据 + 因子计算
    history = fetch_history(code, market, days=400)
    if history.empty:
        raise HTTPException(503, "行情数据获取失败，请稍后重试")

    factors = compute_factors(history)
    if not factors:
        raise HTTPException(422, "数据不足，无法计算因子")

    score_result = compute_score(factors, market=market)

    # 查最近预测记录
    pred_res = await db.execute(
        select(Prediction)
        .where(Prediction.code == code)
        .order_by(Prediction.created_at.desc())
        .limit(5)
    )
    recent_preds = pred_res.scalars().all()

    return {
        "code": code, "market": market,
        "score": score_result,
        "signal_label": score_signal_label(score_result["signal"]),
        "advice": signal_to_advice(score_result["total_score"], score_result["signal"], False),
        "recent_predictions": [
            {
                "predict_date": p.predict_date, "horizon": p.horizon,
                "direction": p.direction, "prob_up": p.prob_up,
                "signal_strength": p.signal_strength,
                "pred_range_low": p.pred_range_low, "pred_range_high": p.pred_range_high,
                "is_correct": p.is_correct, "actual_change_pct": p.actual_change_pct,
                "ai_summary": p.ai_summary,
            }
            for p in recent_preds
        ],
        "history_dates":   history["date"].dt.strftime("%Y-%m-%d").tolist()[-60:],
        "history_close":   [round(v, 2) for v in history["close"].tolist()[-60:]],
        "history_volume":  [int(v) for v in history["volume"].tolist()[-60:]],
    }

@app.post("/api/market/stock/{code}/predict")
async def create_prediction(code: str, market: str = "A",
                            user: User = Depends(current_user),
                            db: AsyncSession = Depends(get_db)):
    """为某只股票生成T1/T3预测记录并存库"""
    history = fetch_history(code, market, days=400)
    if history.empty:
        raise HTTPException(503, "行情数据获取失败")
    factors = compute_factors(history)
    if not factors:
        raise HTTPException(422, "数据不足")

    score_result = compute_score(factors, market=market)
    today = datetime.now().strftime("%Y-%m-%d")

    preds = []
    for horizon in ["T1", "T3"]:
        # 避免重复
        dup = await db.execute(select(Prediction).where(
            Prediction.code == code, Prediction.predict_date == today,
            Prediction.horizon == horizon))
        if dup.scalar_one_or_none():
            continue
        p = Prediction(
            code=code, market=market, predict_date=today, horizon=horizon,
            direction=score_result["signal"],
            signal_strength=score_result["signal_strength"],
            prob_up=score_result["prob_up"],
            pred_range_low=score_result["pred_range_low"],
            pred_range_high=score_result["pred_range_high"],
        )
        db.add(p)
        preds.append(horizon)

    # 存评分快照
    dup_score = await db.execute(select(QuantScore).where(
        QuantScore.code == code, QuantScore.score_date == today))
    if not dup_score.scalar_one_or_none():
        db.add(QuantScore(
            code=code, market=market, score_date=today,
            total_score=score_result["total_score"],
            fundamental_score=score_result["fundamental_score"],
            technical_score=score_result["technical_score"],
            fund_flow_score=score_result["fund_flow_score"],
            sentiment_score=score_result["sentiment_score"],
            signal=score_result["signal"],
            signal_strength=score_result["signal_strength"],
        ))

    await db.commit()
    return {"ok": True, "created_horizons": preds, "score": score_result}

# ═══════════════════════════════════════════════════════════════
# Accuracy Routes
# ═══════════════════════════════════════════════════════════════
@app.get("/api/accuracy")
async def accuracy_summary(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    """准确率总览（含基准线对比）"""
    return await get_accuracy_summary(db)

@app.get("/api/accuracy/history/{code}")
async def stock_prediction_history(code: str, user: User = Depends(current_user),
                                   db: AsyncSession = Depends(get_db)):
    """某只股票的历史预测记录"""
    result = await db.execute(
        select(Prediction).where(Prediction.code == code)
        .order_by(Prediction.created_at.desc()).limit(30)
    )
    preds = result.scalars().all()
    return [
        {
            "predict_date": p.predict_date, "horizon": p.horizon,
            "direction": p.direction, "prob_up": p.prob_up,
            "signal_strength": p.signal_strength,
            "pred_range_low": p.pred_range_low, "pred_range_high": p.pred_range_high,
            "is_correct": p.is_correct, "actual_direction": p.actual_direction,
            "actual_change_pct": p.actual_change_pct, "settled_at": p.settled_at,
            "ai_summary": p.ai_summary,
        }
        for p in preds
    ]

# ═══════════════════════════════════════════════════════════════
# Stock Search (for adding stocks)
# ═══════════════════════════════════════════════════════════════
@app.get("/api/search")
async def search_stock(q: str, market: str = "A", user: User = Depends(current_user)):
    """搜索股票（A股用AKShare，港股通验证代码格式）"""
    import akshare as ak
    try:
        if market == "HK":
            code = q.strip().zfill(5)
            # 验证港股代码存在
            info = ak.stock_individual_info_em(symbol=code) if len(code) == 6 else None
            return [{"code": code, "name": q, "market": "HK"}]
        else:
            df = ak.stock_info_a_code_name()
            mask = df["code"].str.contains(q, na=False) | df["name"].str.contains(q, na=False)
            results = df[mask].head(10)
            return [{"code": r["code"], "name": r["name"], "market": "A"}
                    for _, r in results.iterrows()]
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return []

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

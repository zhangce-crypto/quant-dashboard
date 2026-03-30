from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum, uuid

class Base(DeclarativeBase):
    pass

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    id         = Column(String, primary_key=True, default=gen_uuid)
    email      = Column(String, unique=True, nullable=False, index=True)
    name       = Column(String, nullable=False)
    hashed_pw  = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")

class Portfolio(Base):
    __tablename__ = "portfolios"
    id          = Column(String, primary_key=True, default=gen_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False)
    description = Column(String, default="")
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    user        = relationship("User", back_populates="portfolios")
    stocks      = relationship("PortfolioStock", back_populates="portfolio", cascade="all, delete-orphan")

class MarketEnum(str, enum.Enum):
    A  = "A"   # 沪深A股
    HK = "HK"  # 港股通

class PortfolioStock(Base):
    __tablename__ = "portfolio_stocks"
    id           = Column(String, primary_key=True, default=gen_uuid)
    portfolio_id = Column(String, ForeignKey("portfolios.id"), nullable=False)
    code         = Column(String, nullable=False)   # e.g. 600519 / 00700
    name         = Column(String, nullable=False)
    market       = Column(String, nullable=False)   # A / HK
    cost_price   = Column(Float, nullable=True)     # 可选：买入成本
    shares       = Column(Float, nullable=True)     # 可选：持股数量
    tag          = Column(String, default="")       # 长期持有 / 短线观察
    added_at     = Column(DateTime(timezone=True), server_default=func.now())
    portfolio    = relationship("Portfolio", back_populates="stocks")

class QuantScore(Base):
    """每日量化评分快照"""
    __tablename__ = "quant_scores"
    id                = Column(String, primary_key=True, default=gen_uuid)
    code              = Column(String, nullable=False, index=True)
    market            = Column(String, nullable=False)
    score_date        = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    total_score       = Column(Float)   # 0-100
    fundamental_score = Column(Float)
    technical_score   = Column(Float)
    fund_flow_score   = Column(Float)
    sentiment_score   = Column(Float)
    signal            = Column(String)  # up / neutral / down
    signal_strength   = Column(Integer) # 1-5
    computed_at       = Column(DateTime(timezone=True), server_default=func.now())

class HorizonEnum(str, enum.Enum):
    T1 = "T1"
    T3 = "T3"

class Prediction(Base):
    """预测记录 + 到期后回填实际结果"""
    __tablename__ = "predictions"
    id                  = Column(String, primary_key=True, default=gen_uuid)
    code                = Column(String, nullable=False, index=True)
    market              = Column(String, nullable=False)
    predict_date        = Column(String, nullable=False)  # 预测发出日
    horizon             = Column(String, nullable=False)  # T1 / T3
    direction           = Column(String, nullable=False)  # up / neutral / down
    signal_strength     = Column(Integer)
    prob_up             = Column(Float)   # 上涨概率 0-1
    pred_range_low      = Column(Float)   # 预测涨跌幅下限（%）
    pred_range_high     = Column(Float)   # 预测涨跌幅上限（%）
    ai_summary          = Column(Text, default="")  # LLM分析文本
    # 到期后回填
    actual_direction    = Column(String, nullable=True)
    actual_change_pct   = Column(Float, nullable=True)
    is_correct          = Column(Boolean, nullable=True)
    settled_at          = Column(DateTime(timezone=True), nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

class AccuracyStat(Base):
    """准确率统计月度汇总"""
    __tablename__ = "accuracy_stats"
    id              = Column(String, primary_key=True, default=gen_uuid)
    month           = Column(String, nullable=False)   # YYYY-MM
    horizon         = Column(String, nullable=False)   # T1 / T3
    market          = Column(String, nullable=False)   # A / HK / ALL
    total_count     = Column(Integer, default=0)
    correct_count   = Column(Integer, default=0)
    accuracy_rate   = Column(Float, default=0.0)
    baseline_rate   = Column(Float, default=0.5)       # 固定随机基准
    beat_baseline   = Column(Float, default=0.0)       # accuracy_rate - 0.5
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

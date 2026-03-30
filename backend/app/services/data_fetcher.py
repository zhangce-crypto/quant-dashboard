"""
行情数据抓取服务
实时行情：新浪财经批量接口（<1秒）+ 腾讯财经备用
历史K线：AKShare 东方财富接口
"""
import requests
import akshare as ak
import pandas as pd
import numpy as np
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── 新浪接口代码格式转换 ──────────────────────────────────────
def to_sina_code(code: str, market: str) -> str:
    """600519,A → sh600519 | 00700,HK → hk00700"""
    if market == "HK":
        return f"hk{code.zfill(5)}"
    if code.startswith("6"):
        return f"sh{code}"
    return f"sz{code}"

def parse_sina_quote(raw_line: str, code: str, market: str) -> Optional[Dict]:
    """解析新浪行情返回的字符串"""
    try:
        m = re.search(r'"([^"]+)"', raw_line)
        if not m or not m.group(1):
            return None
        parts = m.group(1).split(",")
        def _pct(price, prev):
            """计算涨跌幅，含除零保护"""
            if prev and prev != 0:
                return round((price - prev) / prev * 100, 2)
            return 0.0

        if market == "HK":
            # 港股格式：名称,今开,昨收,最新价,最高,最低,...
            if len(parts) < 8:
                return None
            price = float(parts[3] or 0)
            prev  = float(parts[2] or 0)
            return {
                "code": code, "market": market,
                "name": parts[0],
                "open": float(parts[1] or 0),
                "prev_close": prev,
                "price": price,
                "high": float(parts[4] or 0),
                "low": float(parts[5] or 0),
                "volume": float(parts[6] or 0),
                "amount": float(parts[7] or 0),
                "change_pct": _pct(price, prev),
                "change_amt": round(price - prev, 3),
            }
        else:
            # A股格式：名称,今开,昨收,最新价,最高,最低,买1,卖1,成交量,成交额,...
            if len(parts) < 32:
                return None
            price = float(parts[3] or 0)
            prev  = float(parts[2] or 0)
            return {
                "code": code, "market": market,
                "name": parts[0],
                "open": float(parts[1] or 0),
                "prev_close": prev,
                "price": price,
                "high": float(parts[4] or 0),
                "low": float(parts[5] or 0),
                "volume": float(parts[9] or 0),
                "amount": float(parts[10] or 0),
                "change_pct": _pct(price, prev),
                "change_amt": round(price - prev, 3),
            }
    except Exception:
        return None

def fetch_realtime_quotes(stocks: List[Dict]) -> List[Dict]:
    """
    批量获取实时行情（新浪接口，<1秒）
    stocks: [{"code": "600519", "market": "A"}, ...]
    """
    if not stocks:
        return []

    sina_codes = [to_sina_code(s["code"], s["market"]) for s in stocks]
    code_map   = {to_sina_code(s["code"], s["market"]): s for s in stocks}
    batch_str  = ",".join(sina_codes)

    try:
        resp = requests.get(
            f"https://hq.sinajs.cn/list={batch_str}",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=8
        )
        resp.encoding = "gbk"
        lines  = resp.text.strip().split("\n")
        quotes = []
        for line in lines:
            m = re.match(r'var hq_str_(\w+)=', line)
            if not m:
                continue
            sina_code = m.group(1)
            orig      = code_map.get(sina_code)
            if not orig:
                continue
            q = parse_sina_quote(line, orig["code"], orig["market"])
            if q:
                quotes.append(q)
        return quotes
    except Exception as e:
        logger.error(f"新浪行情接口失败: {e}")
        return _fetch_realtime_fallback(stocks)

def _fetch_realtime_fallback(stocks: List[Dict]) -> List[Dict]:
    """腾讯财经备用接口"""
    try:
        codes_str = ",".join(to_sina_code(s["code"], s["market"]) for s in stocks)
        resp = requests.get(
            f"https://qt.gtimg.cn/q={codes_str}",
            headers={"Referer": "https://gu.qq.com"},
            timeout=8
        )
        resp.encoding = "gbk"
        quotes = []
        for line in resp.text.strip().split("\n"):
            m = re.search(r'"([^"]+)"', line)
            if not m:
                continue
            parts = m.group(1).split("~")
            if len(parts) < 32:
                continue
            # 腾讯格式：0=名称,1=代码,2=现价,3=昨收,4=今开,5=成交量,...
            code_raw = parts[1]
            # 反推原始code
            code = code_raw.lstrip("shsz").lstrip("hk")
            mkt  = "HK" if code_raw.startswith("hk") else "A"
            quotes.append({
                "code": code, "market": mkt,
                "name": parts[0],
                "price": float(parts[2] or 0),
                "prev_close": float(parts[3] or 0),
                "open": float(parts[4] or 0),
                "volume": float(parts[5] or 0),
                "high": float(parts[33] or 0) if len(parts) > 33 else 0,
                "low": float(parts[34] or 0) if len(parts) > 34 else 0,
                "amount": float(parts[36] or 0) if len(parts) > 36 else 0,
                "change_pct": float(parts[31] or 0) if len(parts) > 31 else 0,
                "change_amt": float(parts[31] or 0) if len(parts) > 31 else 0,
            })
        return quotes
    except Exception as e:
        logger.error(f"腾讯行情备用接口也失败: {e}")
        return []

def fetch_index_quotes() -> Dict:
    """获取大盘指数（上证、深证、沪深300）"""
    try:
        resp = requests.get(
            "https://hq.sinajs.cn/list=s_sh000001,s_sh000300,s_sz399001",
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=5
        )
        resp.encoding = "gbk"
        result = {}
        mapping = {
            "s_sh000001": "sh000001",
            "s_sh000300": "sh000300",
            "s_sz399001": "sz399001",
        }
        for line in resp.text.strip().split("\n"):
            m_code = re.match(r'var hq_str_(\w+)=', line)
            m_data = re.search(r'"([^"]+)"', line)
            if not m_code or not m_data:
                continue
            parts = m_data.group(1).split(",")
            if len(parts) < 5:
                continue
            key = mapping.get(m_code.group(1), m_code.group(1))
            result[key] = {
                "name": parts[0],
                "price": float(parts[1] or 0),
                "change_amt": float(parts[2] or 0),
                "change_pct": float(parts[3] or 0),
                "volume": float(parts[4] or 0),
            }
        return result
    except Exception as e:
        logger.error(f"指数接口失败: {e}")
        return {}

def fetch_history(code: str, market: str, days: int = 365) -> pd.DataFrame:
    """
    获取历史日K线（用于因子计算）
    返回 DataFrame: date, open, high, low, close, volume, amount
    """
    end   = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        if market == "A":
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start, end_date=end, adjust="qfq"
            )
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close",
                "成交量": "volume", "成交额": "amount", "换手率": "turnover"
            })
        else:
            df = ak.stock_hk_hist(
                symbol=code.zfill(5), period="daily",
                start_date=start, end_date=end, adjust="qfq"
            )
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close",
                "成交量": "volume", "成交额": "amount"
            })
            if "turnover" not in df.columns:
                df["turnover"] = np.nan

        df["date"] = pd.to_datetime(df["date"])
        keep = ["date", "open", "high", "low", "close", "volume", "amount"]
        return df[[c for c in keep if c in df.columns]].sort_values("date").reset_index(drop=True)
    except Exception as e:
        logger.error(f"历史K线 {code} 失败: {e}")
        return pd.DataFrame()

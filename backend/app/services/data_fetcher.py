"""
行情数据抓取服务 V2.0
- 内存缓存层（A股代码表/历史K线/实时行情）
- 港股搜索返回真实名称
- 新增恒生指数
"""
import requests, akshare as ak, pandas as pd, numpy as np, re, logging, time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── 缓存 ──────────────────────────────────────────────────────
_cache: Dict[str, dict] = {}
def _cget(key: str, ttl: int = 86400):
    e = _cache.get(key)
    return e["data"] if e and time.time() - e["ts"] < ttl else None
def _cset(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}

# ── A股代码表（内存常驻）─────────────────────────────────────
_a_table: Optional[pd.DataFrame] = None
_a_table_ts: float = 0

def get_a_stock_table() -> pd.DataFrame:
    global _a_table, _a_table_ts
    if _a_table is not None and time.time() - _a_table_ts < 86400:
        return _a_table
    try:
        _a_table = ak.stock_info_a_code_name()
        _a_table_ts = time.time()
        logger.info(f"A股代码表已加载: {len(_a_table)} 条")
    except Exception as e:
        logger.error(f"加载A股代码表失败: {e}")
        if _a_table is None:
            _a_table = pd.DataFrame(columns=["code", "name"])
    return _a_table

def preload_a_stock_table():
    get_a_stock_table()

def search_a_stocks(q: str, limit: int = 10) -> List[Dict]:
    df = get_a_stock_table()
    if df.empty: return []
    mask = df["code"].str.contains(q, na=False) | df["name"].str.contains(q, na=False)
    return [{"code": r["code"], "name": r["name"], "market": "A"} for _, r in df[mask].head(limit).iterrows()]

# ── 新浪代码 ──────────────────────────────────────────────────
def to_sina_code(code: str, market: str) -> str:
    if market == "HK": return f"hk{code.zfill(5)}"
    return f"sh{code}" if code.startswith("6") else f"sz{code}"

def parse_sina_quote(raw_line: str, code: str, market: str) -> Optional[Dict]:
    try:
        m = re.search(r'"([^"]+)"', raw_line)
        if not m or not m.group(1): return None
        parts = m.group(1).split(",")
        def _pct(p, prev): return round((p - prev) / prev * 100, 2) if prev else 0.0
        if market == "HK":
            if len(parts) < 8: return None
            price, prev = float(parts[3] or 0), float(parts[2] or 0)
            return {"code": code, "market": market, "name": parts[0].strip(),
                    "open": float(parts[1] or 0), "prev_close": prev, "price": price,
                    "high": float(parts[4] or 0), "low": float(parts[5] or 0),
                    "volume": float(parts[6] or 0), "amount": float(parts[7] or 0),
                    "change_pct": _pct(price, prev), "change_amt": round(price - prev, 3)}
        else:
            if len(parts) < 32: return None
            price, prev = float(parts[3] or 0), float(parts[2] or 0)
            return {"code": code, "market": market, "name": parts[0].strip(),
                    "open": float(parts[1] or 0), "prev_close": prev, "price": price,
                    "high": float(parts[4] or 0), "low": float(parts[5] or 0),
                    "volume": float(parts[9] or 0), "amount": float(parts[10] or 0),
                    "change_pct": _pct(price, prev), "change_amt": round(price - prev, 3)}
    except Exception:
        return None

def fetch_realtime_quotes(stocks: List[Dict]) -> List[Dict]:
    if not stocks: return []
    ck = "quotes:" + ",".join(sorted(f"{s['code']}_{s['market']}" for s in stocks))
    cached = _cget(ck, ttl=30)
    if cached: return cached
    sina_codes = [to_sina_code(s["code"], s["market"]) for s in stocks]
    code_map = {to_sina_code(s["code"], s["market"]): s for s in stocks}
    try:
        resp = requests.get(f"https://hq.sinajs.cn/list={','.join(sina_codes)}",
                            headers={"Referer": "https://finance.sina.com.cn"}, timeout=8)
        resp.encoding = "gbk"
        quotes = []
        for line in resp.text.strip().split("\n"):
            m = re.match(r'var hq_str_(\w+)=', line)
            if not m: continue
            orig = code_map.get(m.group(1))
            if not orig: continue
            q = parse_sina_quote(line, orig["code"], orig["market"])
            if q: quotes.append(q)
        _cset(ck, quotes)
        return quotes
    except Exception as e:
        logger.error(f"新浪行情接口失败: {e}")
        return _fetch_realtime_fallback(stocks)

def _fetch_realtime_fallback(stocks: List[Dict]) -> List[Dict]:
    try:
        codes_str = ",".join(to_sina_code(s["code"], s["market"]) for s in stocks)
        resp = requests.get(f"https://qt.gtimg.cn/q={codes_str}",
                            headers={"Referer": "https://gu.qq.com"}, timeout=8)
        resp.encoding = "gbk"
        quotes = []
        for line in resp.text.strip().split("\n"):
            m = re.search(r'"([^"]+)"', line)
            if not m: continue
            parts = m.group(1).split("~")
            if len(parts) < 32: continue
            code = parts[1].lstrip("shsz").lstrip("hk")
            mkt = "HK" if parts[1].startswith("hk") else "A"
            quotes.append({"code": code, "market": mkt, "name": parts[0],
                           "price": float(parts[2] or 0), "prev_close": float(parts[3] or 0),
                           "open": float(parts[4] or 0), "volume": float(parts[5] or 0),
                           "high": float(parts[33] or 0) if len(parts) > 33 else 0,
                           "low": float(parts[34] or 0) if len(parts) > 34 else 0,
                           "amount": float(parts[36] or 0) if len(parts) > 36 else 0,
                           "change_pct": float(parts[31] or 0) if len(parts) > 31 else 0,
                           "change_amt": float(parts[31] or 0) if len(parts) > 31 else 0})
        return quotes
    except Exception as e:
        logger.error(f"腾讯行情备用接口也失败: {e}")
        return []

def fetch_index_quotes() -> Dict:
    cached = _cget("idx", ttl=30)
    if cached: return cached
    try:
        resp = requests.get(
            "https://hq.sinajs.cn/list=s_sh000001,s_sh000300,s_sz399001,rt_hkHSI",
            headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        resp.encoding = "gbk"
        result = {}
        mapping = {"s_sh000001": "sh000001", "s_sh000300": "sh000300", "s_sz399001": "sz399001"}
        for line in resp.text.strip().split("\n"):
            mc = re.match(r'var hq_str_(\w+)=', line)
            md = re.search(r'"([^"]+)"', line)
            if not mc or not md: continue
            rc, parts = mc.group(1), md.group(1).split(",")
            if rc == "rt_hkHSI" and len(parts) >= 9:
                p, prev = float(parts[6] or 0), float(parts[3] or 0)
                result["hkHSI"] = {"name": "恒生指数", "price": p,
                    "change_amt": round(p - prev, 2),
                    "change_pct": round((p - prev) / prev * 100, 2) if prev else 0, "volume": 0}
            elif rc in mapping and len(parts) >= 5:
                result[mapping[rc]] = {"name": parts[0], "price": float(parts[1] or 0),
                    "change_amt": float(parts[2] or 0), "change_pct": float(parts[3] or 0),
                    "volume": float(parts[4] or 0)}
        _cset("idx", result)
        return result
    except Exception as e:
        logger.error(f"指数接口失败: {e}")
        return {}

def fetch_hk_stock_name(code: str) -> str:
    try:
        sina_code = f"hk{code.zfill(5)}"
        resp = requests.get(f"https://hq.sinajs.cn/list={sina_code}",
                            headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        resp.encoding = "gbk"
        m = re.search(r'"([^"]+)"', resp.text)
        if m and m.group(1):
            nm = m.group(1).split(",")[0].strip()
            if nm: return nm
    except Exception: pass
    return code

def search_hk_stocks(query: str) -> List[Dict]:
    code = query.strip().zfill(5)
    name = fetch_hk_stock_name(code)
    return [{"code": code, "name": name, "market": "HK"}]

def fetch_history(code: str, market: str, days: int = 365) -> pd.DataFrame:
    ck = f"hist:{code}:{market}:{days}"
    cached = _cget(ck, ttl=86400)
    if cached is not None: return cached
    end = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        if market == "A":
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            df = df.rename(columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                                    "收盘": "close", "成交量": "volume", "成交额": "amount", "换手率": "turnover"})
        else:
            df = ak.stock_hk_hist(symbol=code.zfill(5), period="daily", start_date=start, end_date=end, adjust="qfq")
            df = df.rename(columns={"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
                                    "收盘": "close", "成交量": "volume", "成交额": "amount"})
            if "turnover" not in df.columns: df["turnover"] = np.nan
        df["date"] = pd.to_datetime(df["date"])
        keep = ["date", "open", "high", "low", "close", "volume", "amount"]
        result = df[[c for c in keep if c in df.columns]].sort_values("date").reset_index(drop=True)
        _cset(ck, result)
        return result
    except Exception as e:
        logger.error(f"历史K线 {code} 失败: {e}")
        return pd.DataFrame()

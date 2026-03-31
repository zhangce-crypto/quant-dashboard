"""
config.py — 后端配置中心

职责：
  从环境变量（或 .env 文件）读取所有配置项，统一在这里管理。
  其他模块通过 `from app.core.config import settings` 使用。

如何修改：
  本地开发  → 修改 backend/.env 文件
  生产环境  → 在 Railway 控制台 Variables 里设置，不需要改代码

关键配置说明：
  CORS_ORIGINS  控制哪些前端域名可以访问后端 API
                格式：JSON 数组字符串，例如：
                  ["https://quant-dashboard-opal.vercel.app"]
                多个域名：
                  ["https://xxx.vercel.app","https://www.yourdomain.com"]
                Railway 里已设置此变量，会自动覆盖下方默认值

关联文件：
  main.py       使用 settings.cors_origins_list 配置 CORS 中间件
  db/session.py 使用 settings.async_database_url 连接数据库
"""
from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # ── 数据库 ────────────────────────────────────────────────
    DATABASE_URL: str                          # Railway 自动注入，格式：postgresql://...

    # ── Redis（定时任务用）────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── JWT 认证 ──────────────────────────────────────────────
    SECRET_KEY: str                            # 用于签发 Token，生产环境必须设置强随机值
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080   # Token 有效期，默认 7 天

    # ── 可选功能 ──────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""                # 预留，V1.2 接入 AI 摘要时使用
    APP_ENV: str = "development"               # development / production

    # ── CORS 跨域配置 ─────────────────────────────────────────
    # 默认值仅用于本地开发，生产环境在 Railway Variables 里覆盖
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """
        解析 CORS_ORIGINS 为列表，支持两种格式：
          1. JSON 数组：["https://xxx.vercel.app","https://yyy.com"]
          2. 逗号分隔：https://xxx.vercel.app,https://yyy.com

        末尾斜杠自动去掉，避免 https://xxx.com/ 匹配失败
        解析失败时降级返回 localhost，不会让服务崩溃
        """
        value = self.CORS_ORIGINS.strip()
        try:
            if value.startswith("["):
                origins = json.loads(value)
            else:
                origins = [o.strip() for o in value.split(",") if o.strip()]
            return [o.rstrip("/") for o in origins]
        except Exception:
            return ["http://localhost:5173"]

    @property
    def async_database_url(self) -> str:
        """
        将 Railway 提供的 postgresql:// 自动转为 postgresql+asyncpg://
        以支持 SQLAlchemy 异步驱动，调用方无需关心格式差异
        """
        url = self.DATABASE_URL
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://",   "postgresql+asyncpg://", 1)
        return url

    class Config:
        env_file = ".env"   # 本地开发时从 backend/.env 读取
        extra = "ignore"    # 忽略 .env 里多余的变量，不报错


settings = Settings()

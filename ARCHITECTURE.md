# AI投资助手 — 代码架构说明（V1.1）

> 专为 AI Coding 设计。下次把代码交给 AI 时，附上本文件，AI 可立刻
> 定位"改哪个文件、改什么位置"，无需重新理解整个项目。

---

## 目录结构

```
ai-investor/
├── backend/
│   ├── app/
│   │   ├── main.py                   ★ 所有 API 路由（改接口先看这里）
│   │   ├── core/
│   │   │   ├── config.py             环境变量（改配置项）
│   │   │   └── scheduler.py         定时任务（改刷新频率/结算时间）
│   │   ├── models/
│   │   │   └── db_models.py          ★ 数据库表（加字段/改表结构）
│   │   ├── db/session.py             数据库连接（一般不改）
│   │   └── services/
│   │       ├── data_fetcher.py       ★ 行情抓取（改数据源/加接口）
│   │       ├── quant_engine.py       ★★ 量化引擎核心（改因子/权重/模型）
│   │       └── prediction_service.py 预测结算+准确率统计
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/src/
│   ├── App.tsx                       路由+侧边栏（加新页面）
│   ├── lib/api.ts                    ★ 所有后端接口调用（改路径/加请求）
│   ├── index.css                     全局 CSS 变量（改颜色/字体）
│   └── pages/
│       ├── Login.tsx                 登录/注册
│       ├── Dashboard.tsx             ★ 仪表盘+组合管理（V1.1 合并）
│       ├── StockDetail.tsx           ★ 股票详情+K线+评分+预测
│       └── Accuracy.tsx              准确率（全局+个股）
│
├── tests/test_all.py                 61个单元测试
├── docker-compose.yml                一键部署
├── ARCHITECTURE.md                   本文件
└── README.md
```

---

## 页面关系图

```
/login  (Login.tsx)
  ↓ 登录成功
  ↓
/ (Dashboard.tsx)   ←── 侧边栏"仪表盘"
  │  内含：组合标签切换 / 新建组合 / 删除组合
  │         添加股票弹窗 / 移除股票
  │
  │ 点击股票行 / 点击"详情"按钮
  ↓
/stock/:market/:code  (StockDetail.tsx)
  │ 点击"← 返回"  →  navigate(-1) 回 Dashboard
  │
  └─ 侧边栏"预测准确率"
     ↓
  /accuracy  (Accuracy.tsx)
     内含：全局准确率 / 个股明细（点击展开）
```

---

## 数据流

```
前端页面
  └→ api.ts (axios, 自动带 Bearer token)
       └→ FastAPI main.py 路由
            ├→ services/data_fetcher.py   → 新浪/腾讯财经 / AKShare
            ├→ services/quant_engine.py   → 纯计算，无外部依赖
            └→ services/prediction_service.py → PostgreSQL
```

---

## 最常见修改场景

| 目标 | 改哪里 |
|------|--------|
| 改仪表盘股票列表的列 | `Dashboard.tsx` → `COL` 变量和对应 JSX |
| 改组合标签样式 | `Dashboard.tsx` → portfolios.map 那段 |
| 改 K 线图配置 | `StockDetail.tsx` → `klineOpt` 对象 |
| 改准确率页面指标 | `Accuracy.tsx` → StatCard 和 trendOpt |
| 加新的后端接口 | `main.py` 加路由 → `api.ts` 加函数 |
| 改因子权重 | `quant_engine.py` → `FACTOR_IC_WEIGHTS` |
| 改维度权重 | `quant_engine.py` → `DIMENSION_WEIGHTS`（必须合计1.00）|
| 换实时行情数据源 | `data_fetcher.py` → `fetch_realtime_quotes()` |
| 改定时任务时间 | `scheduler.py` → `CronTrigger` 参数 |
| 加数据库字段 | `db_models.py` 加 Column，重启自动建表 |

---

## V1.1 变更记录

- `Portfolio.tsx` 已删除，组合管理逻辑合并进 `Dashboard.tsx`
- 侧边栏从3项（仪表盘/我的组合/准确率）缩减为2项（仪表盘/准确率）
- 组合标签 × 按钮：点击弹确认框，确认后真实删除
- 移除股票按钮：弹确认框，确认后立即从列表移除
- App.tsx 路由去掉 `/portfolio` 路径

---

## 测试覆盖（61个，全部通过）

| 模块 | 数量 | 覆盖 |
|------|------|------|
| 因子计算 | 9 | 值域、边界、除零保护 |
| 评分计算 | 8 | 范围、信号、港股差异 |
| 行情解析 | 10 | 新浪A股/港股、代码转换、网络失败 |
| 预测逻辑 | 9 | 方向分类、准确率、月度分组 |
| 信号标签 | 5 | 中文标签、建议文字 |
| 数据库模型 | 7 | 所有表字段、表名 |
| 配置验证 | 5 | 权重之和、因子数、基准值 |
| 端到端 | 5 | 完整流水线、A股+港股、截面归一化 |

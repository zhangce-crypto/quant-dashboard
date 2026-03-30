FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 启动：使用 shell 形式以正确解析 $PORT 环境变量（Railway 会注入 PORT）
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

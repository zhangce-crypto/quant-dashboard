FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 使用 Python 脚本启动，通过 os.environ.get("PORT") 正确读取 Railway 注入的端口
CMD ["python", "run.py"]

FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 赋予启动脚本执行权限
RUN chmod +x start.sh

# 使用 start.sh 启动，正确读取 Railway 注入的 $PORT 环境变量
CMD ["/bin/sh", "start.sh"]

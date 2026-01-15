# Dockerfile for Gemini Business API（带注册功能）
# 使用 uv 管理依赖，包含 Chrome + Xvfb 支持注册功能
FROM python:3.11-slim

WORKDIR /app

# 先安装基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 添加 Google Chrome 源
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list

# 安装 Chrome、Xvfb 和必要的依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    xvfb \
    x11-utils \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制依赖配置文件
COPY pyproject.toml uv.lock ./

# 使用 uv 同步依赖
RUN uv sync --frozen --no-dev

# 复制项目文件
COPY main.py .
COPY core ./core
COPY util ./util
COPY templates ./templates
COPY static ./static

# 创建数据目录
RUN mkdir -p ./data/images

# 声明数据卷
VOLUME ["/app/data"]

# 创建 Xvfb 启动脚本
RUN printf '#!/bin/bash\n\
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null\n\
Xvfb :99 -screen 0 1920x1080x24 &\n\
sleep 1\n\
export DISPLAY=:99\n\
echo "Xvfb started on :99"\n\
exec "$@"\n' > /app/start-xvfb.sh && chmod +x /app/start-xvfb.sh

# 设置环境变量
ENV DISPLAY=:99
# 设置时区为东八区（北京时间）
ENV TZ=Asia/Shanghai
# 🔥 艹，明确指定Chrome路径，避免"Binary Location Must be a String"错误
ENV CHROME_BIN=/usr/bin/google-chrome-stable

# 使用 Xvfb 启动脚本作为 entrypoint
ENTRYPOINT ["/app/start-xvfb.sh"]

# 启动主服务
CMD ["uv", "run", "python", "-u", "main.py"]

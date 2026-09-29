FROM python:3.11-slim

WORKDIR /app

# ── 复制全部源码并安装 ───────────────────────────────────────────
COPY . .

# 使用根 pyproject.toml 安装全部依赖 + 注册 mud 入口点
RUN pip install --no-cache-dir -e .

EXPOSE 5100 8000

CMD ["mud", "unified"]

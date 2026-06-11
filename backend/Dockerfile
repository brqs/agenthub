# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS base

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG http_proxy
ARG https_proxy
ARG all_proxy
ARG NODE_MAJOR=22
ARG OPENCODE_VERSION=latest
ARG CLAUDE_CODE_VERSION=latest
ARG CODEX_VERSION=latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PATH="/root/.local/bin:/usr/local/bin:${PATH}"

WORKDIR /app

# 系统依赖（asyncpg 编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    docker-cli \
    docker.io \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# External runtimes. Keep these CLIs in the backend image because B2 invokes them
# via subprocess inside the AgentHub workspace container.
RUN HTTP_PROXY="${HTTP_PROXY:-$http_proxy}" \
    HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}" \
    ALL_PROXY="${ALL_PROXY:-$all_proxy}" \
    http_proxy="${http_proxy:-$HTTP_PROXY}" \
    https_proxy="${https_proxy:-$HTTPS_PROXY}" \
    all_proxy="${all_proxy:-$ALL_PROXY}" \
    install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key" \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm install -g "@openai/codex@${CODEX_VERSION}" \
    && npm install -g "opencode-ai@${OPENCODE_VERSION}" \
    && claude --version \
    && codex --version \
    && opencode --version \
    && rm -rf /var/lib/apt/lists/* /root/.npm

# 安装 Python 依赖
COPY pyproject.toml ./
RUN HTTP_PROXY="${HTTP_PROXY:-$http_proxy}" \
    HTTPS_PROXY="${HTTPS_PROXY:-$https_proxy}" \
    ALL_PROXY="${ALL_PROXY:-$all_proxy}" \
    http_proxy="${http_proxy:-$HTTP_PROXY}" \
    https_proxy="${https_proxy:-$HTTPS_PROXY}" \
    all_proxy="${all_proxy:-$ALL_PROXY}" \
    pip install --upgrade pip && pip install -e ".[dev]" \
    && pip install 'bcrypt>=4.0.0,<5.0.0'

# 复制源代码
# Browser preview verification needs Chromium and its system libraries.
RUN python -m playwright install-deps chromium \
    && python -m playwright install chromium \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

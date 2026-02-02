FROM node:20-slim AS codex
RUN npm install -g @openai/codex

FROM python:3.9-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends git ripgrep && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY --from=codex /usr/local/bin/codex /usr/local/bin/codex
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/bin/npm /usr/local/bin/npm
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN mkdir -p /usr/local/vendor
COPY --from=codex /usr/local/lib/node_modules/@openai/codex/vendor /usr/local/vendor
ENV CODEX_CLI_PATH=/usr/local/bin/codex

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

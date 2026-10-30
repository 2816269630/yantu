FROM node:22-bookworm-slim AS codex-runtime
RUN npm install --global @openai/codex@0.166.0

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend

COPY --from=codex-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=codex-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/yantu /app/backend/yantu
COPY frontend /app/frontend

RUN useradd --uid 10001 --create-home yantu && mkdir -p /app/uploads \
    && chown -R yantu:yantu /app/uploads
USER yantu

EXPOSE 8000
CMD ["uvicorn", "yantu.app:app", "--host", "0.0.0.0", "--port", "8000"]

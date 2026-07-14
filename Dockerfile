FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Chromium do Playwright, usado pelo captcha_relay.py. --with-deps instala as
# bibliotecas de sistema que o Chromium precisa (senão falha silenciosamente
# em produção). Isso aumenta a imagem em ~300-400MB.
RUN playwright install --with-deps chromium
COPY . .
EXPOSE 8000
# v36: roda as migrations do Alembic ANTES de subir o servidor — garante que
# o schema (tenant/user/buyerradar) esteja atualizado a cada deploy, sem
# passo manual. Em DATABASE_URL sqlite (dev local), isso é rápido e seguro;
# em produção (Postgres), é o mecanismo real de versionamento de schema.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

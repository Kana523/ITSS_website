FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system industry && adduser --system --ingroup industry industry

COPY pyproject.toml uv.lock ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN python -m pip install --no-cache-dir .

USER industry

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]

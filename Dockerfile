# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY app ./app
COPY transfermarkt_api ./transfermarkt_api
COPY README.md LICENSE ./

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra server --no-editable

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

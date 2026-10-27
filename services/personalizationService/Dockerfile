FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.13.5
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY test ./test
RUN uv sync --locked --no-editable
RUN uv run --locked --no-editable ruff check . \
    && uv run --locked --no-editable ruff format --check . \
    && uv run --locked --no-editable mypy \
    && uv run --locked --no-editable pytest --cov --cov-fail-under=70 \
    && uv build --no-sources

FROM build AS integration
CMD ["uv", "run", "--locked", "--no-editable", "pytest", "test/integration", "-v"]

FROM build AS production-dependencies
RUN uv sync --locked --no-dev --no-editable

FROM python:3.14.9-slim-bookworm@sha256:945c2676dc2b18e0c1f16879244122c57c0ffede60006bf3df159c507a31bcae AS runtime

ARG VCS_REF=local
LABEL org.opencontainers.image.title="Cluster JAM Personalization Service" \
    org.opencontainers.image.version="0.1.0" \
    org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --gid 10001 personalization \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --shell /usr/sbin/nologin personalization
WORKDIR /app
COPY --from=production-dependencies /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8080 50051
CMD ["python", "-m", "personalization.main"]

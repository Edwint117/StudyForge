FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.12.14-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY engine ./engine
COPY prompts ./prompts
# Public Supabase CA (copy of /certificates; a test keeps them identical). libpq verify-full needs it on disk.
COPY certs ./certs
RUN uv sync --frozen --no-dev && groupadd --gid 10001 engine && useradd --uid 10001 --gid engine --no-create-home engine
USER 10001:10001
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "engine.runtime:build_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]

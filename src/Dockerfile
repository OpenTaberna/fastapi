############################################
# 1) uv installer stage
############################################
FROM python:3.12-slim AS uv-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_INSTALL_DIR=/usr/local/bin

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh

############################################
# 2) deps stage: build a self-contained venv
############################################
FROM python:3.12-slim AS deps

# Bring uv from the previous stage
COPY --from=uv-base /usr/local/bin/uv /usr/local/bin/uv

# Create a dedicated virtualenv for runtime deps
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

# Copy dependency manifest to leverage Docker layer cache
# Note: build context is project root, so pyproject.toml is at root level
COPY pyproject.toml /build/

# Install deps into the venv using uv (supports pyproject.toml directly)
RUN uv pip install --python /opt/venv/bin/python --no-cache -r pyproject.toml

############################################
# 3) final stage: copy venv + app code
############################################
FROM python:3.12-slim AS runtime

# Copy the prebuilt venv from the deps stage
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
 && apt-get install -y --no-install-recommends wireguard-tools \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Copy the application code
# Note: build context is project root, so app is at src/app/
# We copy it as 'app' so Python imports work correctly (from app.services...)
COPY src/app /code/app

# Optional: run as non-root
# RUN useradd -m appuser && chown -R appuser:appuser /code
# USER appuser

EXPOSE 8000

# The app module is now at /code/app/, so uvicorn can find app.main:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
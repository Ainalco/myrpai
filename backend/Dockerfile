# ── Builder stage: compile C extensions, then discard gcc ──────────
FROM mirror.gcr.io/library/python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Runtime stage: slim image, no compiler toolchain ──────────────
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 9000

CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "9000"]

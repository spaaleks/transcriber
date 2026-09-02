# syntax=docker/dockerfile:1.6

FROM --platform=$TARGETPLATFORM python:3.12-slim AS builder
ARG TARGETPLATFORM
WORKDIR /build
RUN apt-get update \
 && apt-get install -y --no-install-recommends binutils curl \
 && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"
COPY requirements.txt ./
COPY lib ./lib
COPY routes ./routes
COPY static ./static
COPY templates ./templates
COPY app.py ./app.py
RUN uv run --no-project --with-requirements requirements.txt --with pyinstaller \
      pyinstaller --onefile --name transcriber \
      --add-data "templates:templates" \
      --add-data "static:static" \
      --collect-all faster_whisper \
      --collect-all ctranslate2 \
      --collect-all onnxruntime \
      --collect-all tokenizers \
      --collect-all huggingface_hub \
      --collect-all av \
      --collect-all yt_dlp \
      app.py

FROM debian:trixie-slim AS runtime
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /build/dist/transcriber /usr/local/bin/transcriber

ENV APP_DATA_DIR=/app/data \
    RECIPIENTS_DIR=/app/config \
    APP_HOST=0.0.0.0 \
    PORT=15551 \
    PATH=/usr/local/bin:$PATH
EXPOSE 15551
ENTRYPOINT ["/usr/local/bin/transcriber"]

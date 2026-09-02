#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

uv run --no-project --with-requirements requirements.txt --with pyinstaller \
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

platform_tag="$(python3 - <<'PY'
import platform
system = platform.system().lower()
arch = platform.machine().lower()
print(f"{system}-{arch}")
PY
)"

mkdir -p dist
cp dist/transcriber "dist/transcriber.${platform_tag}"
echo "Built binary available at dist/transcriber and dist/transcriber.${platform_tag}"

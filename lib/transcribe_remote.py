from pathlib import Path
from typing import Optional, Callable
import mimetypes
import re
import threading
import time
import requests
from .utils import media_duration_seconds, hhmmss

class RemoteTranscriptionError(RuntimeError):
    pass

_SENTENCE_END = (".", "!", "?", "…")
_HEARTBEAT_SECONDS = 15.0

def _run_with_heartbeat(do_call, progress_cb: Callable[[float], None], log_cb: Callable[[str], None]):
    result: dict = {}

    def run():
        try:
            result["value"] = do_call()
        except BaseException as e:
            result["error"] = e

    t = threading.Thread(target=run, daemon=True)
    start = time.monotonic()
    t.start()
    nudge = 0.05
    while True:
        t.join(timeout=_HEARTBEAT_SECONDS)
        if not t.is_alive():
            break
        log_cb(f"Still transcribing remotely… elapsed {int(time.monotonic() - start)}s")
        try:
            progress_cb(min(nudge, 0.3))
        except Exception:
            pass
        nudge += 0.02
    if "error" in result:
        raise result["error"]
    return result.get("value")

def _words_to_segments(words) -> list[dict]:
    if not words:
        return []
    segs: list[dict] = []
    cur: list[str] = []
    cur_start = None
    last_end = None

    def flush():
        nonlocal cur, cur_start
        if cur:
            text = re.sub(r"\s+([,.!?;:…])", r"\1", " ".join(cur)).strip()
            if text:
                segs.append({"text": text, "start": cur_start or 0.0, "end": last_end or cur_start or 0.0})
        cur = []
        cur_start = None

    for w in words:
        if not isinstance(w, dict):
            continue
        if w.get("type") in ("spacing", "audio_event"):
            continue
        token = (w.get("word") or w.get("text") or "").strip()
        if not token:
            continue
        start = w.get("start")
        end = w.get("end")
        if cur and start is not None and last_end is not None and start - last_end > 1.5:
            flush()
        if cur_start is None:
            cur_start = start if start is not None else last_end
        cur.append(token)
        if end is not None:
            last_end = end
        joined = " ".join(cur)
        if token.endswith(_SENTENCE_END) or len(joined) >= 180:
            flush()
    flush()
    return segs

def _endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/audio/transcriptions"):
        return base
    return f"{base}/audio/transcriptions"

def _post(url: str, api_key: Optional[str], media_path: Path, model: str,
          language: Optional[str], response_format: str, timeout: int, verify: bool):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = {"model": model, "response_format": response_format}
    if language:
        data["language"] = language
    content_type = mimetypes.guess_type(media_path.name)[0] or "application/octet-stream"
    with open(media_path, "rb") as fh:
        files = {"file": (media_path.name, fh, content_type)}
        return requests.post(url, headers=headers, data=data, files=files,
                             timeout=timeout, verify=verify)

def transcribe_to_txt_remote(media_path: Path, txt_path: Path,
                             settings,
                             progress_cb: Callable[[float], None],
                             log_cb: Callable[[str], None],
                             lang_hint: Optional[str] = None,
                             allowed_languages: Optional[list[str]] = None):
    if not settings.transcribe_api_base:
        raise RemoteTranscriptionError("TRANSCRIBE_API_BASE is not set for remote backend")

    url = _endpoint(settings.transcribe_api_base)
    model = settings.transcribe_model
    timeout = settings.transcribe_timeout
    verify = settings.transcribe_verify

    allowed_list = [l.strip().lower() for l in (allowed_languages or []) if l.strip()]
    allowed = set(allowed_list) if allowed_list else None
    if allowed_list:
        log_cb(f"Language allowlist active: {', '.join(allowed_list)}")

    language = lang_hint
    if allowed and len(allowed) == 1 and not lang_hint:
        language = allowed_list[0]
        log_cb(f"Using enforced language from allowlist: {language}")

    log_cb(f"Sending media to remote transcription endpoint: {url} (model={model})")
    progress_cb(0.0)

    def _call(lang: Optional[str]):
        resp = _post(url, settings.transcribe_api_key, media_path, model, lang,
                     "verbose_json", timeout, verify)
        if resp.status_code >= 400:
            raise RemoteTranscriptionError(
                f"Remote endpoint returned {resp.status_code}: {resp.text[:500]}"
            )
        try:
            return resp.json()
        except ValueError:
            return {"text": resp.text}

    payload = _run_with_heartbeat(lambda: _call(language), progress_cb, log_cb)
    detected_language = (payload.get("language") or "").lower() or None
    if allowed and detected_language and detected_language not in allowed:
        fallback_language = allowed_list[0]
        log_cb(f"Detected language '{detected_language}' not in allowlist {sorted(allowed)}. Retrying with '{fallback_language}'.")
        payload = _run_with_heartbeat(lambda: _call(fallback_language), progress_cb, log_cb)
        detected_language = (payload.get("language") or fallback_language).lower()

    if detected_language:
        log_cb(f"Detected language: {detected_language}")

    segments = payload.get("segments") or _words_to_segments(payload.get("words"))
    dur = media_duration_seconds(media_path) or payload.get("duration") or None

    with open(txt_path, "w", encoding="utf-8") as txt_f:
        if segments:
            seen_end = 0.0
            for seg in segments:
                line = (seg.get("text") or "").strip()
                if not line:
                    continue
                txt_f.write(line + "\n")
                end = seg.get("end")
                if dur and end:
                    pct = min(100.0, float(end) / float(dur) * 100.0)
                    progress_cb(pct / 100.0)
                    if end - seen_end >= 2.0:
                        start = seg.get("start") or 0.0
                        log_cb(f"{pct:5.1f}% [{hhmmss(start)} → {hhmmss(end)}] {line}")
                        seen_end = end
        else:
            text = (payload.get("text") or "").strip()
            txt_f.write(text + ("\n" if text else ""))
            log_cb("Remote endpoint returned plain text (no segments).")

    progress_cb(1.0)
    log_cb("Transcription completed. Writing finalized outputs.")

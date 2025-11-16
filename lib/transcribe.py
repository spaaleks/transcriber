from pathlib import Path
from typing import Optional, Callable
from faster_whisper import WhisperModel
from .utils import media_duration_seconds, hhmmss

def transcribe_to_txt(media_path: Path, txt_path: Path,
                      model_size: str, device: str, compute_type: str, cpu_threads: int,
                      progress_cb: Callable[[float], None], log_cb: Callable[[str], None],
                      lang_hint: Optional[str] = None, allowed_languages: Optional[list[str]] = None):
    model = WhisperModel(model_size, device=device, compute_type=compute_type, cpu_threads=cpu_threads)
    allowed_list = [l.strip().lower() for l in (allowed_languages or []) if l.strip()]
    allowed = set(allowed_list) if allowed_list else None
    if allowed_list:
        log_cb(f"Language allowlist active: {', '.join(allowed_list)}")

    def _transcribe(language: Optional[str]):
        return model.transcribe(
            str(media_path),
            language=language,
            task="transcribe",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
            word_timestamps=False,
        )

    language_for_first_pass = lang_hint
    if allowed and len(allowed) == 1 and not lang_hint:
        language_for_first_pass = allowed_list[0]
        log_cb(f"Using enforced language from allowlist: {language_for_first_pass}")

    segments, info = _transcribe(language_for_first_pass)
    detected_language = getattr(info, "language", None)
    if allowed and detected_language and detected_language.lower() not in allowed:
        fallback_language = allowed_list[0]
        log_cb(f"Detected language '{detected_language}' not in allowlist {sorted(allowed)}. Retrying with '{fallback_language}'.")
        segments, info = _transcribe(fallback_language)
        detected_language = getattr(info, "language", None) or fallback_language

    dur = media_duration_seconds(media_path) or getattr(info, "duration", None) or None

    with open(txt_path, "w", encoding="utf-8") as txt_f:
        if detected_language is not None:
            log_cb(f"Detected language: {detected_language} (p={getattr(info,'language_probability',None)})")
        seen_end = 0.0
        for seg in segments:
            line = seg.text.strip()
            txt_f.write(line + "\n")
            if dur and seg.end:
                pct = min(100.0, float(seg.end) / float(dur) * 100.0)
                progress_cb(pct / 100.0)
                if seg.end - seen_end >= 2.0:
                    log_cb(f"{pct:5.1f}% [{hhmmss(seg.start)} → {hhmmss(seg.end)}] {line}")
                    seen_end = seg.end
    progress_cb(1.0)
    log_cb("Transcription completed. Writing finalized outputs.")

from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

def _unescape(s: str | None) -> str | None:
    if s is None:
        return None
    return s.replace(r"\n", "\n").replace(r"\t", "\t")

def discover_recipient_groups(rec_dir: Path) -> list[str]:
    groups = set()
    if rec_dir.exists():
        for p in rec_dir.glob("recipients_*.txt"):
            g = p.stem.removeprefix("recipients_")
            if g:
                groups.add(g)
    return sorted(groups)

def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")

def _resolve_backend(raw: str | None, api_base: str | None) -> str:
    if raw:
        v = raw.strip().lower()
        if v in ("remote", "openai", "external", "litellm"):
            return "remote"
        return "local"
    return "remote" if api_base else "local"

def _parse_allowed_languages(raw: str | None) -> list[str] | None:
    """Parse comma-separated allowlist. Returns None for '*' or empty."""
    if not raw:
        return None
    raw = raw.strip()
    if raw == "*":
        return None
    langs = [p.strip().lower() for p in raw.split(",") if p.strip()]
    return langs or None

@dataclass
class Settings:
    # app
    data_dir: Path
    db_path: Path
    model_size: str
    device: str
    allowed_languages: list[str] | None
    compute_type: str
    cpu_threads: int
    transcribe_backend: str
    transcribe_api_base: str | None
    transcribe_api_key: str | None
    transcribe_model: str
    transcribe_timeout: int
    transcribe_verify: bool
    web_server: str
    web_threads: int
    host: str
    port: int
    recipients_dir: Path
    available_groups: list[str]
    # email
    auto_send_email: bool
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_pass: str | None
    smtp_sender: str | None
    smtp_sender_name: str | None
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_ca_file: str | None
    smtp_verify: bool
    recipients_file: Path
    mail_subject: str
    mail_body: str
    mail_body_file: Path | None = None
    mail_body_html: str | None = None,
    mail_body_html_file: Path | None = None
    upload_max_mb: int = 2048,
    # webhook
    webhook_url: str | None = None
    webhook_bearer: str | None = None
    webhook_timeout: int = 15
    webhook_verify: bool = True
    # incoming webhook
    incoming_webhook_token: str | None = None

    @property
    def use_remote_transcription(self) -> bool:
        return self.transcribe_backend == "remote"

    @property
    def smtp_from_header(self) -> str | None:
        """Return proper From header value."""
        if not self.smtp_sender:
            return None
        if self.smtp_sender_name:
            return f'{self.smtp_sender_name} <{self.smtp_sender}>'
        return self.smtp_sender

    @staticmethod
    def from_env() -> "Settings":
        data_dir = Path(os.environ.get("APP_DATA_DIR", "./data")).resolve()
        recipients_dir = Path(os.environ.get("RECIPIENTS_DIR", "./config")).resolve()
        recipients_file = Path(os.environ.get("RECIPIENTS_FILE", str(recipients_dir / "recipients.txt")))

        transcribe_api_base = os.environ.get("TRANSCRIBE_API_BASE") or None
        transcribe_backend = _resolve_backend(os.environ.get("TRANSCRIBE_BACKEND"), transcribe_api_base)

        s = Settings(
            # app
            data_dir=data_dir,
            db_path=data_dir / "jobs.db",
            model_size=os.environ.get("WHISPER_MODEL", "small"),
            device=os.environ.get("WHISPER_DEVICE", "cpu"),
            allowed_languages=_parse_allowed_languages(os.environ.get("WHISPER_ALLOWED_LANGUAGES")),
            compute_type=os.environ.get("WHISPER_COMPUTE", "int8"),
            cpu_threads=int(os.environ.get("WHISPER_THREADS", "8")),
            transcribe_backend=transcribe_backend,
            transcribe_api_base=transcribe_api_base,
            transcribe_api_key=os.environ.get("TRANSCRIBE_API_KEY") or None,
            transcribe_model=os.environ.get("TRANSCRIBE_MODEL", "whisper-1"),
            transcribe_timeout=int(os.environ.get("TRANSCRIBE_TIMEOUT", "600")),
            transcribe_verify=_env_bool("TRANSCRIBE_VERIFY", True),
            web_server=os.environ.get("WEB_SERVER", "waitress").strip().lower(),
            web_threads=int(os.environ.get("WEB_THREADS", "8")),
            host=os.environ.get("APP_HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", "15551")),
            upload_max_mb = int(os.environ.get("UPLOAD_MAX_MB", "2048")),
            # email
            auto_send_email=os.environ.get("AUTO_SEND_EMAIL", "0") not in ("0","false","False"),
            smtp_host=os.environ.get("SMTP_HOST"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER"),
            smtp_pass=os.environ.get("SMTP_PASS"),
            smtp_sender=os.environ.get("SMTP_SENDER"),
            smtp_sender_name=os.environ.get("SMTP_SENDER_NAME"),
            smtp_use_tls=os.environ.get("SMTP_USE_TLS", "1") not in ("0", "false", "False"),
            smtp_use_ssl=os.environ.get("SMTP_USE_SSL", "0") in ("1", "true", "True"),
            smtp_ca_file=os.environ.get("SMTP_CA_FILE"),
            smtp_verify=os.environ.get("SMTP_VERIFY", "1") not in ("0", "false", "False"),
            recipients_dir=recipients_dir,
            recipients_file=recipients_file,
            mail_subject=_unescape(os.environ.get("MAIL_SUBJECT", "Transcript: {name}")) or "",
            mail_body=_unescape(os.environ.get("MAIL_BODY", "Please find the transcript attached.\n\nJob: {name}\nSlug: {slug}\n")) or "",
            mail_body_file=None,
            mail_body_html=_unescape(os.environ.get("MAIL_BODY_HTML")),
            mail_body_html_file=None,
            available_groups=[],
            webhook_url=os.environ.get("WEBHOOK_URL"),
            webhook_bearer=os.environ.get("WEBHOOK_BEARER"),
            webhook_timeout=int(os.environ.get("WEBHOOK_TIMEOUT", "15")),
            webhook_verify=os.environ.get("WEBHOOK_VERIFY", "1") not in ("0","false","False"),
            incoming_webhook_token=os.environ.get("INCOMING_WEBHOOK_TOKEN"),
        )
        mbf = os.environ.get("MAIL_BODY_FILE")
        if mbf and Path(mbf).exists():
            s.mail_body = Path(mbf).read_text(encoding="utf-8")
            s.mail_body_file = Path(mbf)

        s.available_groups = discover_recipient_groups(s.recipients_dir)
        return s

from flask import Blueprint, request, jsonify, abort
from werkzeug.utils import secure_filename
from lib.db import db_conn, ensure_unique_slug
from lib.utils import slugify, now_iso


def incoming_bp(worker, settings):
    bp = Blueprint("incoming", __name__, url_prefix="/api/incoming")

    def _check_token():
        token = settings.incoming_webhook_token
        if not token:
            abort(403, "Incoming webhook not configured")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:] == token:
            return
        abort(401, "Invalid or missing token")

    @bp.before_request
    def verify_token():
        _check_token()

    @bp.get("/groups")
    def list_groups():
        return jsonify({"groups": settings.available_groups})

    @bp.post("/job")
    def create_job():
        # Accept JSON or multipart/form-data
        if request.content_type and "json" in request.content_type:
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            group = (data.get("group") or "").strip()
            url = (data.get("url") or "").strip()
            uploaded_file = None
        else:
            name = (request.form.get("name") or "").strip()
            group = (request.form.get("group") or "").strip()
            url = (request.form.get("url") or "").strip()
            uploaded_file = request.files.get("file")

        if not name:
            abort(400, "name is required")
        if not url and not uploaded_file:
            abort(400, "url or file is required")

        base = slugify(name)
        with db_conn(settings.db_path) as con:
            slug = ensure_unique_slug(con, base, settings.data_dir)
            d = settings.data_dir / slug
            d.mkdir(parents=True, exist_ok=True)

            media_path_str = ""
            if uploaded_file:
                filename = secure_filename(uploaded_file.filename or "media.bin")
                if "." not in filename:
                    filename += ".bin"
                media_path = d / filename
                uploaded_file.save(media_path)
                media_path_str = str(media_path)
                url = ""

            created = now_iso()
            con.execute(
                "INSERT INTO jobs (name, slug, url, status, progress, log, media_path, created_at, updated_at, recipient_group) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (name, slug, url, "queued", 0, "", media_path_str or None, created, created, group or None),
            )
            con.commit()
            job = con.execute("SELECT id, slug, status FROM jobs WHERE slug=?", (slug,)).fetchone()

        worker.ensure()
        return jsonify({"ok": True, "job_id": job["id"], "slug": job["slug"], "status": job["status"]}), 201

    return bp

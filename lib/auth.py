from functools import wraps
from flask import request, Response
import os

# Load credentials from environment
AUTH_USER = os.environ.get("APP_AUTH_USER")
AUTH_PASS = os.environ.get("APP_AUTH_PASS")
INCOMING_TOKEN = os.environ.get("INCOMING_WEBHOOK_TOKEN")

def check_auth(username: str, password: str) -> bool:
    return username == AUTH_USER and password == AUTH_PASS

def check_bearer_token() -> bool:
    if not INCOMING_TOKEN:
        return False
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == INCOMING_TOKEN
    return False

def authenticate() -> Response:
    return Response(
        "Authentication required.\n",
        401,
        {"WWW-Authenticate": 'Basic realm="Spal.Transcriber"'},
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not AUTH_USER or not AUTH_PASS:
            return f(*args, **kwargs)

        # Allow Bearer token to bypass Basic Auth (for incoming webhooks)
        if check_bearer_token():
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

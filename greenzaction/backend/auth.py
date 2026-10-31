import base64
import hashlib
import hmac
import json
import os
import time
from functools import wraps
from flask import request, jsonify, g


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(user):
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps({"sub": user["id"], "email": user["email"], "role": user.get("role", "user"), "exp": int(time.time()) + 60 * 60 * 24 * 7}, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    secret = os.getenv("JWT_SECRET", "greenzaction-local-secret").encode()
    signature = _b64(hmac.new(secret, signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def decode_token(token):
    header, payload, signature = token.split(".")
    secret = os.getenv("JWT_SECRET", "greenzaction-local-secret").encode()
    expected = _b64(hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected): raise ValueError("Invalid token signature")
    data = json.loads(_unb64(payload))
    if data.get("exp", 0) < time.time(): raise ValueError("Token expired")
    return data


def jwt_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        try:
            claims = decode_token(header.split(" ", 1)[1])
            user = g.store.find_one("users", {"id": claims["sub"]})
            if not user: raise ValueError("User not found")
            g.user = user
        except Exception as exc:
            return jsonify({"error": str(exc) or "Invalid token"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    @jwt_required
    def wrapper(*args, **kwargs):
        if g.user.get("role") != "admin": return jsonify({"error": "Admin authorization required"}), 403
        return fn(*args, **kwargs)
    return wrapper

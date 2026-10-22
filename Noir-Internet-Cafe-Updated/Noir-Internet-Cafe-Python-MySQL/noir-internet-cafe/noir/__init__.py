"""NOIR Internet Café application factory."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session
from pymysql import IntegrityError, OperationalError, ProgrammingError
from werkzeug.exceptions import HTTPException

from .db import close_db
from .domain import Problem

ROOT = Path(__file__).resolve().parent.parent


def create_app(overrides=None):
    load_dotenv(ROOT / ".env")
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", ""),
        DB_HOST=os.getenv("DB_HOST", "127.0.0.1"), DB_PORT=int(os.getenv("DB_PORT", "3306")),
        DB_USER=os.getenv("DB_USER", "noir_app"), DB_PASSWORD=os.getenv("DB_PASSWORD", ""),
        DB_NAME=os.getenv("DB_NAME", "noir"),
        CAFE_TIMEZONE=os.getenv("CAFE_TIMEZONE", "Asia/Manila"),
        ALLOW_REGISTRATION=os.getenv("ALLOW_REGISTRATION", "true").lower() == "true",
        SESSION_COOKIE_NAME="noir_session", SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=32 * 1024,
        TRUSTED_HOSTS=[v.strip() for v in os.getenv("TRUSTED_HOSTS", "").split(",") if v.strip()] or None,
    )
    if overrides:
        app.config.update(overrides)
    secret = app.config["SECRET_KEY"]
    if len(secret) < 40 or secret.startswith("REPLACE_"):
        raise RuntimeError("Set a unique SECRET_KEY in .env. Run python scripts/configure.py first.")
    from zoneinfo import ZoneInfo
    ZoneInfo(app.config["CAFE_TIMEZONE"])
    app.teardown_appcontext(close_db)

    @app.before_request
    def csrf_protection():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        if request.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
            token = request.headers.get("X-CSRF-Token", "")
            if not token or not secrets.compare_digest(token, session["csrf"]):
                raise Problem("Your session changed. Refresh the page and try again.", 403)
            if not request.is_json:
                raise Problem("Send JSON data.", 415)

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'; object-src 'none'"
        )
        if request.path.startswith("/api/") or request.path == "/":
            response.headers["Cache-Control"] = "no-store"
        if app.config["SESSION_COOKIE_SECURE"]:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(Problem)
    def problem(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        if error.args[0] == 1062:
            return jsonify(error="This email, station name, asset tag, IP, MAC, station link, or operation already exists. Refresh and try again."), 409
        app.logger.exception("Database constraint failed")
        return jsonify(error="The record could not be saved. Refresh and check the details."), 409

    @app.errorhandler(OperationalError)
    @app.errorhandler(ProgrammingError)
    def database_error(error):
        app.logger.exception("Database operation failed")
        if error.args[0] in (1205, 1213):
            return jsonify(error="Another request changed this record. Refresh and try again."), 409
        return jsonify(error="The database is unavailable. Contact the Administrator."), 503

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unexpected request failure")
        return jsonify(error="The request could not be completed. Please try again."), 500

    from .api import api
    from .cli import register_commands
    from .platform import platform
    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(platform, url_prefix="/api")
    register_commands(app)
    return app

"""Create local configuration with unique secrets; no third-party packages needed."""
from pathlib import Path
import os
import secrets

ROOT = Path(__file__).resolve().parent.parent
target = ROOT / ".env"
if target.exists():
    raise SystemExit(".env already exists. Edit it directly; existing secrets were not changed.")

settings = f"""# Generated locally. Keep this file private and retain it when upgrading.
SECRET_KEY={secrets.token_urlsafe(48)}
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=noir
DB_USER=noir_app
DB_PASSWORD={secrets.token_urlsafe(32)}
MYSQL_ROOT_PASSWORD={secrets.token_urlsafe(40)}
CAFE_TIMEZONE=Asia/Manila
ALLOW_REGISTRATION=true
COOKIE_SECURE=false
TRUSTED_HOSTS=
HOST=127.0.0.1
PORT=8000
"""
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w") as handle:
    handle.write(settings)
print("Created .env with unique secrets.")
print("Docker: run docker compose up --build -d, then create your Administrator account.")
print("Existing MySQL: set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env first.")

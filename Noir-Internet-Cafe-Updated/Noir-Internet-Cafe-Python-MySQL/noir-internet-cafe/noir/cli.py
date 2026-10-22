"""Explicit setup and recovery commands; no default account is shipped."""
from pathlib import Path
import click
from werkzeug.security import generate_password_hash
from .db import db, execute, query, transaction
from .migrations import migrate
from .domain import Problem, email, password, text, utcnow


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Apply the initial schema without creating any business data."""
        script = (Path(__file__).resolve().parent.parent / "database" / "schema.sql").read_text()
        script = "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("--"))
        with db().cursor() as cursor:
            for statement in script.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        migrate()
        click.echo("MySQL tables are ready. No accounts or sample data were created.")

    @app.cli.command("migrate-db")
    def migrate_db():
        """Upgrade existing tables without removing accounts or billing history."""
        migrate()
        click.echo("Database updated. Existing records are preserved.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Administrator name")
    @click.option("--email", "address", prompt="Administrator email")
    @click.password_option(confirmation_prompt=True)
    def create_admin(name, address, password):
        """Create an Administrator using credentials you choose."""
        try:
            name, address, secret = text(name, "name", 2, 80), email(address), validate_password(password)
            if query("SELECT id FROM users WHERE email=%s", (address,), one=True):
                raise click.ClickException("That email already exists. Choose a different Administrator email.")
            with transaction():
                uid = execute("INSERT INTO users (name,email,password_hash,role) VALUES (%s,%s,%s,'administrator')",
                              (name, address, generate_password_hash(secret)))
                execute("INSERT INTO audit_log (actor_id,action,detail) VALUES (%s,'account.bootstrap',%s)",
                        (uid, f"Created Administrator #{uid} from server console"))
            click.echo(f"Administrator created: {address}")
        except Problem as error:
            raise click.ClickException(error.message)

    @app.cli.command("reset-password")
    @click.option("--email", "address", prompt="Account email")
    @click.password_option(confirmation_prompt=True)
    def reset_password(address, password):
        """Reset an existing account password from the trusted server console."""
        try:
            address, secret = email(address), validate_password(password)
            with transaction():
                user = query("SELECT id FROM users WHERE email=%s FOR UPDATE", (address,), one=True)
                if not user:
                    raise click.ClickException("Account not found.")
                execute("UPDATE users SET password_hash=%s WHERE id=%s", (generate_password_hash(secret), user["id"]))
                execute("DELETE FROM auth_sessions WHERE user_id=%s", (user["id"],))
                execute("INSERT INTO audit_log (actor_id,action,detail) VALUES (NULL,'account.recovery',%s)",
                        (f"Password reset from server console for account #{user['id']}",))
            click.echo("Password updated. Existing logins were revoked.")
        except Problem as error:
            raise click.ClickException(error.message)

    @app.cli.command("cleanup-auth")
    def cleanup_auth():
        """Remove expired login sessions and rate-limit buckets."""
        with transaction():
            execute("DELETE FROM auth_sessions WHERE expires_at<%s", (utcnow(),))
            execute("DELETE FROM rate_limits WHERE expires_at<%s", (utcnow(),))
        click.echo("Expired authentication records removed.")


validate_password = password

"""One MySQL connection per Flask request, with explicit transaction boundaries."""
from contextlib import contextmanager
from flask import current_app, g
import pymysql


def db():
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config["DB_HOST"], port=current_app.config["DB_PORT"],
            user=current_app.config["DB_USER"], password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"], charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, autocommit=True,
            connect_timeout=5, read_timeout=15, write_timeout=15,
            init_command="SET time_zone = '+00:00'",
        )
    return g.db


def query(sql, args=(), one=False):
    with db().cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone() if one else cursor.fetchall()


def execute(sql, args=()):
    with db().cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.lastrowid


@contextmanager
def transaction():
    connection = db()
    connection.begin()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection:
        connection.close()

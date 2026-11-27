import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

BASE_DIR = Path(__file__).resolve().parent.parent
ALLOWED_ENVIRONMENTS = {"development", "testing", "production"}
ALLOWED_DB_DRIVERS = {"sqlite", "mysql", "mysql+pymysql", "postgresql", "postgresql+psycopg2", "postgresql+psycopg"}
PLACEHOLDER_SECRETS = {"", "replace-with-a-long-random-secret", "changeme", "secret"}


class ConfigError(RuntimeError):
    """Raised when required environment configuration is invalid."""


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as error:
        raise ConfigError(f"Environment variable {name} must be an integer.") from error
    if value < minimum:
        raise ConfigError(f"Environment variable {name} must be at least {minimum}.")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    lowered = raw.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise ConfigError(f"Environment variable {name} must be 'true' or 'false'.")


def redact_database_uri(uri: str | None) -> str:
    """Return a sanitized database URI without exposing credentials."""
    if not uri:
        return "<unconfigured>"
    try:
        return make_url(uri).render_as_string(hide_password=True)
    except Exception:
        return "<invalid-database-uri>"


def resolve_database_uri() -> str:
    """Resolve the database connection URI from environment variables or SQLite fallback."""
    explicit_url = (os.getenv("DATABASE_URL") or "").strip()
    if explicit_url:
        try:
            parsed = make_url(explicit_url)
        except ArgumentError as error:
            raise ConfigError("DATABASE_URL is malformed.") from error
        if parsed.drivername not in ALLOWED_DB_DRIVERS:
            raise ConfigError(
                f"Unsupported database driver '{parsed.drivername}' in DATABASE_URL."
            )
        if parsed.drivername == "mysql":
            parsed = parsed.set(drivername="mysql+pymysql")
            return parsed.render_as_string(hide_password=False)
        return explicit_url

    mysql_markers = ("MYSQL_HOST", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PORT")
    if any((os.getenv(key) or "").strip() for key in mysql_markers):
        user = (os.getenv("MYSQL_USER") or "root").strip()
        password = os.getenv("MYSQL_PASSWORD") or ""
        host = (os.getenv("MYSQL_HOST") or "localhost").strip()
        port = _env_int("MYSQL_PORT", 3306, minimum=1)
        database = (os.getenv("MYSQL_DATABASE") or "satya_db").strip()
        if not host or not database or not user:
            raise ConfigError("MYSQL_USER, MYSQL_HOST, and MYSQL_DATABASE must be non-empty.")
        return (
            f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}"
            f"@{host}:{port}/{quote_plus(database)}?charset=utf8mb4"
        )

    return "sqlite:///" + str(BASE_DIR / "instance" / "satya.sqlite")


def build_engine_options(database_uri: str) -> dict:
    """Return SQLAlchemy engine options appropriate for the configured backend."""
    if not database_uri or database_uri.startswith("sqlite:"):
        return {}

    options = {
        "pool_pre_ping": True,
        "pool_recycle": _env_int("DB_POOL_RECYCLE", 1800, minimum=30),
        "pool_size": _env_int("DB_POOL_SIZE", 5, minimum=1),
        "max_overflow": _env_int("DB_MAX_OVERFLOW", 10, minimum=0),
        "pool_timeout": _env_int("DB_POOL_TIMEOUT", 30, minimum=1),
    }
    if database_uri.startswith("mysql"):
        options["connect_args"] = {
            "connect_timeout": _env_int("DB_CONNECT_TIMEOUT", 10, minimum=1),
            "charset": "utf8mb4",
        }
    return options


def load_config() -> dict:
    """Build and validate runtime configuration from environment variables."""
    satya_env = (os.getenv("SATYA_ENV") or "development").strip().lower()
    if satya_env not in ALLOWED_ENVIRONMENTS:
        raise ConfigError(
            f"SATYA_ENV must be one of: {', '.join(sorted(ALLOWED_ENVIRONMENTS))}."
        )

    secret_key = (os.getenv("SECRET_KEY") or "").strip()
    if satya_env == "production" and (secret_key in PLACEHOLDER_SECRETS or len(secret_key) < 32):
        raise ConfigError(
            "SECRET_KEY must be set to a unique random value of at least 32 characters in production."
        )

    max_upload_bytes = _env_int("MAX_UPLOAD_BYTES", 16 * 1024 * 1024, minimum=1024)
    session_secure = _env_bool("SESSION_COOKIE_SECURE", default=(satya_env == "production"))
    session_lifetime_hours = _env_int("SESSION_LIFETIME_HOURS", 12, minimum=1)
    database_uri = resolve_database_uri()
    engine_options = build_engine_options(database_uri)

    raw_upload_folder = (os.getenv("UPLOAD_FOLDER") or str(BASE_DIR / "uploads")).strip()
    upload_path = Path(raw_upload_folder)
    if not upload_path.is_absolute():
        upload_path = BASE_DIR / upload_path

    return {
        "SATYA_ENV": satya_env,
        "DEBUG": satya_env == "development" and _env_bool("FLASK_DEBUG", False),
        "SECRET_KEY": secret_key or None,
        "MAX_UPLOAD_BYTES": max_upload_bytes,
        "SQLALCHEMY_DATABASE_URI": database_uri,
        "SQLALCHEMY_ENGINE_OPTIONS": engine_options,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "MAX_CONTENT_LENGTH": max_upload_bytes + 64 * 1024,
        "UPLOAD_FOLDER": str(upload_path),
        "ALLOWED_UPLOAD_EXTENSIONS": {"pdf"},
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": session_secure,
        "SESSION_REFRESH_EACH_REQUEST": True,
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=session_lifetime_hours),
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_SECURE": session_secure,
        "AI_PROVIDER": (os.getenv("AI_PROVIDER") or "none").strip(),
        "AI_API_KEY": os.getenv("AI_API_KEY", ""),
        "AI_API_URL": os.getenv("AI_API_URL", ""),
        "AI_MODEL": os.getenv("AI_MODEL", ""),
        "AI_TIMEOUT_SECONDS": _env_int("AI_TIMEOUT_SECONDS", 30, minimum=1),
    }


class Config:
    """Default configuration container populated from environment variables."""

    SECRET_KEY = os.getenv("SECRET_KEY")
    MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(16 * 1024 * 1024)))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + str(BASE_DIR / "instance" / "satya.sqlite"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 64 * 1024
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    ALLOWED_UPLOAD_EXTENSIONS = {"pdf"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    AI_PROVIDER = os.getenv("AI_PROVIDER", "none")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_API_URL = os.getenv("AI_API_URL", "")
    AI_MODEL = os.getenv("AI_MODEL", "")
    AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))

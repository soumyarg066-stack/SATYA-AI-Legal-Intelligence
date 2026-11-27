import logging
import os
import secrets
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, g, jsonify, redirect, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend.config import ConfigError, build_engine_options, load_config, redact_database_uri
from backend.extensions import csrf, db, login_manager, migrate
from backend.services.language_service import get_language_messages, resolve_request_language


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder="../frontend/templates",
        static_folder="../frontend/static",
        instance_relative_config=True,
    )
    runtime_config = load_config()
    app.config.from_mapping(runtime_config)
    if not app.config.get("SECRET_KEY"):
        if app.config.get("SATYA_ENV") == "production":
            raise ConfigError("SECRET_KEY must be configured in production.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)

    if test_config:
        app.config.update(test_config)
        if "SQLALCHEMY_DATABASE_URI" in test_config and "SQLALCHEMY_ENGINE_OPTIONS" not in test_config:
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = build_engine_options(
                app.config["SQLALCHEMY_DATABASE_URI"]
            )

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.session_protection = "strong"
    login_manager.login_view = "pages.login"
    login_manager.login_message_category = "info"

    from backend.models import (
        AuditLog,
        ContactMessage,
        Conversation,
        Document,
        EvidenceChunk,
        LegalSourceDocument,
        Message,
        User,
    )
    from backend.routes.api import api_bp
    from backend.routes.auth import auth_bp
    from backend.routes.pages import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(api_bp, url_prefix="/api")

    @login_manager.user_loader
    def load_user(user_id):
        if getattr(g, "_handling_db_error", False):
            return None
        try:
            parsed_id = int(user_id)
        except (TypeError, ValueError):
            return None
        return db.session.get(User, parsed_id)

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_auth_required"]), 401
        return redirect(url_for("pages.login", next=request.full_path))

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_csrf_invalid"]), 400
        return render_template_error(error.description, 400)

    @app.errorhandler(413)
    def request_too_large(_error):
        message = "The uploaded file exceeds the maximum allowed size."
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_request_too_large"]), 413
        return render_template_error(message, 413)

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_not_found"]), 404
        return render_template_error("The page you requested could not be found.", 404)

    @app.errorhandler(OperationalError)
    def database_unavailable(_error):
        g._handling_db_error = True
        db.session.rollback()
        current_app.logger.error(
            "Database connection unavailable (%s).",
            redact_database_uri(current_app.config.get("SQLALCHEMY_DATABASE_URI")),
        )
        message = "Database service is temporarily unavailable. Please try again shortly."
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_db_unavailable"]), 503
        return render_template_error(message, 503)

    @app.errorhandler(SQLAlchemyError)
    def database_error(_error):
        g._handling_db_error = True
        db.session.rollback()
        current_app.logger.error("A database operation failed.")
        message = "A database error occurred while processing your request."
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_db_generic"]), 500
        return render_template_error(message, 500)

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        current_app.logger.exception("Unhandled application error.")
        if request.path.startswith("/api/"):
            msgs = get_language_messages(resolve_request_language(request))
            return jsonify(error=msgs["error_server_unexpected"]), 500
        return render_template_error("An unexpected server error occurred.", 500)

    @app.context_processor
    def inject_navigation_state():
        is_admin = False
        if not getattr(g, "_handling_db_error", False):
            try:
                is_admin = bool(current_user.is_authenticated and current_user.role == "admin")
            except SQLAlchemyError:
                db.session.rollback()
                g._handling_db_error = True
        return {
            "is_admin": is_admin,
            "current_year": datetime.now().year,
        }

    auto_create = os.getenv("SATYA_AUTO_CREATE_DB", "").strip().lower() == "true"
    is_sqlite = app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:")
    if (is_sqlite and not app.config.get("TESTING")) or auto_create:
        with app.app_context():
            try:
                db.create_all()
            except SQLAlchemyError as error:
                db.session.rollback()
                safe_uri = redact_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
                app.logger.error("Failed to initialize database schema for %s.", safe_uri)
                raise RuntimeError(
                    f"Unable to connect to or initialize the configured database ({safe_uri})."
                ) from error

    return app


def render_template_error(message, status):
    from flask import render_template

    return render_template("error.html", message=message, status=status), status

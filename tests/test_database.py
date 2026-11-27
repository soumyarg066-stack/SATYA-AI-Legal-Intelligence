import io
import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from backend import create_app
from backend.config import (
    ConfigError,
    build_engine_options,
    load_config,
    redact_database_uri,
    resolve_database_uri,
)
from backend.extensions import db
from backend.models import AuditLog, Conversation, Document, Message, User


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "db_test.sqlite"),
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "WTF_CSRF_ENABLED": False,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_config_uri_resolution_redaction_and_validation(monkeypatch):
    assert (
        redact_database_uri("mysql+pymysql://satya_user:SuperSecret123@localhost:3306/satya_db")
        == "mysql+pymysql://satya_user:***@localhost:3306/satya_db"
    )

    monkeypatch.setenv("DATABASE_URL", "mysql://satya:secret@localhost:3306/satya_db")
    resolved = resolve_database_uri()
    assert resolved.startswith("mysql+pymysql://")
    assert build_engine_options(resolved)["pool_pre_ping"] is True
    assert build_engine_options(resolved)["connect_args"]["charset"] == "utf8mb4"

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("MYSQL_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_USER", "root")
    monkeypatch.setenv("MYSQL_PASSWORD", "p@ss:word")
    monkeypatch.setenv("MYSQL_DATABASE", "satya_db")
    built = resolve_database_uri()
    assert built.startswith("mysql+pymysql://root:p%40ss%3Aword@127.0.0.1:3306/satya_db")

    for var in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"):
        monkeypatch.delenv(var, raising=False)
    assert resolve_database_uri().startswith("sqlite:///")
    assert build_engine_options("sqlite:///satya.sqlite") == {}

    monkeypatch.setenv("SATYA_ENV", "invalid-env")
    with pytest.raises(ConfigError):
        load_config()

    monkeypatch.setenv("SATYA_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "replace-with-a-long-random-secret")
    with pytest.raises(ConfigError):
        load_config()


def test_health_endpoint_reports_connected(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "database": "connected"}


def test_database_relationships_and_cascades(app, tmp_path):
    with app.app_context():
        user = User(username="Alice", email="alice@example.com", role="user")
        user.set_password("strong-password-1")
        db.session.add(user)
        db.session.flush()

        conversation = Conversation(user_id=user.id, title="RTI Timeline")
        db.session.add(conversation)
        db.session.flush()

        m1 = Message(conversation_id=conversation.id, sender="user", message="Question?")
        m2 = Message(conversation_id=conversation.id, sender="assistant", message="No evidence.")
        doc = Document(
            filename="act.pdf",
            document_type="PDF",
            processing_status="uploaded",
            file_path=str(tmp_path / "act.pdf"),
            uploaded_by=user.id,
        )
        audit = AuditLog(user_id=user.id, action="auth.login", status="success")
        db.session.add_all([m1, m2, doc, audit])
        db.session.commit()

        assert len(user.conversations) == 1
        assert len(user.conversations[0].messages) == 2
        assert user.documents[0].uploader.email == "alice@example.com"
        assert user.audit_logs[0].action == "auth.login"

        db.session.delete(conversation)
        db.session.commit()
        assert Message.query.count() == 0

        db.session.delete(user)
        db.session.commit()
        assert Conversation.query.count() == 0
        assert Document.query.count() == 0


def test_auth_audit_logs_and_conversation_isolation(client, app):
    res = client.post(
        "/api/auth/register",
        json={"username": "User One", "email": "one@example.com", "password": "strong-password-1"},
    )
    assert res.status_code == 201

    dup = client.post(
        "/api/auth/register",
        json={"username": "User One", "email": "one@example.com", "password": "strong-password-1"},
    )
    assert dup.status_code == 409

    conv_res = client.post("/api/conversations", json={})
    assert conv_res.status_code == 201
    conv_id = conv_res.json["conversation"]["id"]

    chat_res = client.post(
        "/api/chat",
        json={"message": "What is Section 6?", "conversation_id": conv_id},
    )
    assert chat_res.status_code == 200

    assert client.post("/api/chat", json={"message": "Hi", "conversation_id": "bad"}).status_code == 400
    assert client.post("/api/chat", json={"message": "Hi", "conversation_id": True}).status_code == 400

    assert client.post("/api/auth/logout").status_code == 200
    bad_login = client.post(
        "/api/auth/login",
        json={"email": "one@example.com", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401

    # Second user cannot access or delete first user's conversation
    client.post(
        "/api/auth/register",
        json={"username": "User Two", "email": "two@example.com", "password": "strong-password-2"},
    )
    assert client.get(f"/api/conversations/{conv_id}").status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 404

    with app.app_context():
        logs = AuditLog.query.all()
        actions = [(entry.action, entry.status) for entry in logs]
        assert ("auth.register", "success") in actions
        assert ("auth.register", "failure") in actions
        assert ("auth.logout", "success") in actions
        assert ("auth.login", "failure") in actions
        assert ("conversation.create", "success") in actions
        assert all("strong-password" not in (entry.details or "") for entry in logs)


def test_transaction_rollback_cleans_up_failed_commit(client, app, tmp_path):
    client.post(
        "/api/auth/register",
        json={"username": "Admin", "email": "admin@example.com", "password": "strong-password-1"},
    )
    with app.app_context():
        user = User.query.filter_by(email="admin@example.com").one()
        user.role = "admin"
        db.session.commit()

    with patch.object(db.session, "commit", side_effect=SQLAlchemyError("simulated failure")):
        response = client.post(
            "/api/documents",
            data={"file": (io.BytesIO(b"Rule 1: test document content."), "test.txt")},
            content_type="multipart/form-data",
        )
    assert response.status_code == 500
    assert "simulated failure" not in response.json["error"]
    assert list((tmp_path / "uploads").glob("*.txt")) == []


def test_invalid_database_credentials_fail_safely_without_exposing_secrets(tmp_path):
    bad_secret = "never_leak_this_mysql_password"
    bad_uri = f"mysql+pymysql://bad_satya_user:{bad_secret}@127.0.0.1:3306/nonexistent_satya_db"
    bad_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": bad_uri,
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"connect_timeout": 2}},
            "UPLOAD_FOLDER": str(tmp_path / "bad_uploads"),
            "WTF_CSRF_ENABLED": False,
        }
    )
    bad_client = bad_app.test_client()

    health_res = bad_client.get("/api/health")
    assert health_res.status_code == 503
    assert health_res.json == {"status": "error", "database": "unavailable"}
    assert bad_secret not in health_res.get_data(as_text=True)

    login_res = bad_client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "strong-password-1"},
    )
    assert login_res.status_code == 503
    assert bad_secret not in login_res.get_data(as_text=True)
    assert "bad_satya_user" not in login_res.get_data(as_text=True)

    page_res = bad_client.post(
        "/login",
        data={"email": "user@example.com", "password": "strong-password-1"},
    )
    assert page_res.status_code == 503
    assert bad_secret not in page_res.get_data(as_text=True)


def _mysql_available() -> bool:
    test_admin_url = os.getenv("SATYA_TEST_MYSQL_ADMIN_URL", "mysql+pymysql://root:@127.0.0.1:3306")
    try:
        engine = create_engine(test_admin_url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except OperationalError:
        return False


@pytest.mark.skipif(not _mysql_available(), reason="XAMPP MySQL server is not running on localhost:3306")
def test_mysql_end_to_end_on_isolated_test_database(tmp_path):
    """Verify full SATYA workflows against a disposable satya_test_db (never touches satya_db)."""
    admin_url = os.getenv("SATYA_TEST_MYSQL_ADMIN_URL", "mysql+pymysql://root:@127.0.0.1:3306")
    test_db_name = "satya_test_db"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS `{test_db_name}`"))
        conn.execute(
            text(
                f"CREATE DATABASE `{test_db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    mysql_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "mysql-test-secret-key",
            "SQLALCHEMY_DATABASE_URI": f"{admin_url}/{test_db_name}?charset=utf8mb4",
            "UPLOAD_FOLDER": str(tmp_path / "mysql_uploads"),
            "WTF_CSRF_ENABLED": False,
        }
    )
    try:
        with mysql_app.app_context():
            db.create_all()

        mysql_client = mysql_app.test_client()
        assert mysql_client.get("/api/health").json == {"status": "ok", "database": "connected"}

        # Registration & duplicate check
        reg = mysql_client.post(
            "/api/auth/register",
            json={
                "username": "MySQL Tester",
                "email": "mysql.user@example.com",
                "password": "mysql-strong-password",
            },
        )
        assert reg.status_code == 201
        assert (
            mysql_client.post(
                "/api/auth/register",
                json={
                    "username": "MySQL Tester",
                    "email": "mysql.user@example.com",
                    "password": "mysql-strong-password",
                },
            ).status_code
            == 409
        )

        # Conversation creation, message persistence, and retrieval
        conv = mysql_client.post("/api/conversations", json={})
        assert conv.status_code == 201
        conv_id = conv.json["conversation"]["id"]
        chat = mysql_client.post(
            "/api/chat",
            json={"message": "Explain RTI Section 6", "conversation_id": conv_id},
        )
        assert chat.status_code == 200
        assert chat.json["verified"] is False

        detail = mysql_client.get(f"/api/conversations/{conv_id}")
        assert detail.status_code == 200
        assert len(detail.json["conversation"]["messages"]) == 2

        # Profile update
        profile = mysql_client.patch("/api/profile", json={"username": "Updated Tester"})
        assert profile.status_code == 200
        assert profile.json["user"]["username"] == "Updated Tester"

        # Role enforcement
        assert mysql_client.get("/api/admin/stats").status_code == 403

        # Logout & invalid login & valid login
        assert mysql_client.post("/api/auth/logout").status_code == 200
        assert (
            mysql_client.post(
                "/api/auth/login",
                json={"email": "mysql.user@example.com", "password": "wrong"},
            ).status_code
            == 401
        )
        login = mysql_client.post(
            "/api/auth/login",
            json={"email": "mysql.user@example.com", "password": "mysql-strong-password"},
        )
        assert login.status_code == 200

        # Promote to admin and verify admin stats & PDF metadata storage
        with mysql_app.app_context():
            user = User.query.filter_by(email="mysql.user@example.com").one()
            user.role = "admin"
            db.session.commit()

        upload = mysql_client.post(
            "/api/documents",
            data={"file": (io.BytesIO(b"Rule 1: MySQL test source."), "mysql-doc.txt")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 201
        stats = mysql_client.get("/api/admin/stats")
        assert stats.status_code == 200
        assert stats.json["database"] == "connected"
        assert stats.json["total_users"] == 1
        assert stats.json["total_documents"] == 1

        with mysql_app.app_context():
            assert AuditLog.query.count() >= 5
            assert Conversation.query.count() == 1
            assert Message.query.count() == 2
            assert Document.query.count() == 1
    finally:
        with mysql_app.app_context():
            db.session.remove()
            db.engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS `{test_db_name}`"))
        admin_engine.dispose()

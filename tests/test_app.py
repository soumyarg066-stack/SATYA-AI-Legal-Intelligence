import io
import json
import csv
from datetime import date
from unittest.mock import Mock

import pytest

from backend import create_app
from backend.extensions import db
from backend.models import Document, EvidenceChunk, LegalSourceDocument, User


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.sqlite"),
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


def register(client, email="user@example.com", password="a-strong-password"):
    return client.post(
        "/api/auth/register",
        json={"username": "Test User", "email": email, "password": password},
    )


def test_registration_hashes_password_and_login_works(client, app):
    response = register(client)
    assert response.status_code == 201
    with app.app_context():
        user = User.query.filter_by(email="user@example.com").one()
        assert user.password_hash != "a-strong-password"
        assert user.check_password("a-strong-password")

    client.post("/api/auth/logout")
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 200
    assert response.json["user"]["role"] == "user"


def test_html_registration_login_and_logout_flow(client):
    registration = client.post(
        "/register",
        data={
            "username": "Browser User",
            "email": "browser@example.com",
            "password": "a-strong-password",
            "confirm_password": "a-strong-password",
        },
    )
    assert registration.status_code == 302
    assert registration.headers["Location"].endswith("/dashboard")
    assert client.post("/logout").status_code == 302
    login = client.post(
        "/login",
        data={"email": "browser@example.com", "password": "a-strong-password"},
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/dashboard")
    assert client.get("/api/auth/me").status_code == 200


def test_registration_validates_email_and_password(client):
    assert client.post("/api/auth/register", json=["not", "an", "object"]).status_code == 400
    assert client.post(
        "/api/auth/register",
        json={"username": "A", "email": "bad", "password": "short"},
    ).status_code == 400
    register(client)
    assert register(client).status_code == 409


def test_protected_routes_require_login(client):
    assert client.get("/api/profile").status_code == 401
    assert client.post("/api/chat", json={"message": "Question"}).status_code == 401
    assert client.get("/api/admin/stats").status_code == 401


def test_admin_routes_enforce_roles_and_report_database_values(client, app):
    register(client)
    assert client.get("/admin").status_code == 302
    assert client.get("/api/admin/stats").status_code == 403
    with app.app_context():
        user = User.query.filter_by(email="user@example.com").one()
        user.role = "admin"
        db.session.commit()
    assert client.get("/admin").status_code == 200
    response = client.get("/api/admin/stats")
    assert response.status_code == 200
    assert response.json["total_users"] == 1
    assert response.json["total_documents"] == 0


def test_public_pages_render_and_dashboard_requires_login(client):
    home = client.get("/")
    assert home.status_code == 200
    assert b"Legal intelligence." in home.data
    assert b"ILLUSTRATIVE PREVIEW" in home.data
    assert b"Not assessed" in home.data
    for path in ("/login", "/register", "/knowledge", "/documents", "/about", "/contact"):
        assert client.get(path).status_code == 200
    assert b"No verified legal documents are available yet." in client.get("/knowledge").data
    assert b"Sign in to browse source files" in client.get("/documents").data
    assert client.get("/dashboard").status_code == 302
    register(client)
    assert client.get("/dashboard").status_code == 200
    chat_page = client.get("/chat")
    assert chat_page.status_code == 200
    assert b"INSUFFICIENT EVIDENCE" in chat_page.data
    assert b"No verified legal documents are available yet." in chat_page.data
    assert client.get("/profile").status_code == 200


def test_chat_says_no_verified_documents_and_persists_history(client):
    register(client)
    response = client.post("/api/chat", json={"message": "What does this law say?"})
    assert response.status_code == 200
    assert response.json["verified"] is False
    assert response.json["evidence_status"] == "insufficient_evidence"
    assert response.json["citations"] == []
    assert response.json["sources"] == []
    assert "No verified legal source documents are available" in response.json["answer"]
    history = client.get("/api/conversations").json["conversations"]
    assert len(history) == 1
    detail = client.get(f"/api/conversations/{history[0]['id']}").json
    assert len(detail["conversation"]["messages"]) == 2


def add_verified_evidence(app):
    with app.app_context():
        document = LegalSourceDocument(
            title="Verified source record",
            document_type="Test fixture",
            act_or_rule_name="Test fixture only",
            original_filename="source-original.pdf",
            source_url="javascript:alert(1)",
            verification_status="verified",
        )
        document.chunks.append(
            EvidenceChunk(
                section_number="section-recorded-in-source",
                paragraph_number="paragraph-recorded-in-source",
                page_number=12,
                extracted_text=(
                    "The public authority shall provide information within thirty "
                    "days of receipt of an application."
                ),
                content_hash="a" * 64,
                verification_status="verified",
            )
        )
        db.session.add(document)
        db.session.commit()
        return document.id, document.chunks[0].id


class EvidenceMockProvider:
    def __init__(self, claim_text=None, malformed=False):
        self.claim_text = claim_text or (
            "The public authority shall provide information within thirty days of an application."
        )
        self.malformed = malformed
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        if self.malformed:
            return "not a claims list"
        request_payload = json.loads(messages[-1]["content"])
        evidence_id = request_payload["evidence_records"][0]["id"]
        return [{"text": self.claim_text, "evidence_ids": [evidence_id]}]


def test_chat_generates_only_cited_claims_from_verified_records(client, app, monkeypatch):
    document_id, chunk_id = add_verified_evidence(app)
    provider = EvidenceMockProvider()
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["verified"] is True
    assert response.json["evidence_status"] == "supported"
    assert response.json["citations"] == response.json["sources"]
    assert response.json["citations"][0]["id"] == chunk_id
    assert response.json["citations"][0]["document_id"] == document_id
    assert response.json["citations"][0]["filename"] == "source-original.pdf"
    assert response.json["citations"][0]["page"] == 12
    assert response.json["citations"][0]["section"] == "section-recorded-in-source"
    assert response.json["citations"][0]["source_url"] is None
    assert "[1]" in response.json["answer"]


def test_ingestion_records_are_unverified_and_excluded_from_retrieval(client, app):
    register(client)
    with app.app_context():
        from backend.services.ingestion_service import create_unverified_records
        from backend.services.retrieval_service import retrieve_evidence

        source = create_unverified_records(
            {"title": "Unverified source", "document_type": "Unknown"},
            [
                {
                    "page_number": 1,
                    "extracted_text": "The authority shall provide information within thirty days.",
                }
            ],
        )
        db.session.commit()
        assert source.verification_status == "unverified"
        assert source.chunks[0].verification_status == "unverified"
        assert retrieve_evidence("authority provide information within thirty days") == []
    response = client.post("/api/chat", json={"message": "authority provide information within thirty days"})
    assert response.json["evidence_status"] == "insufficient_evidence"


def test_unsupported_claim_is_withheld(client, app, monkeypatch):
    add_verified_evidence(app)
    provider = EvidenceMockProvider("Applicants receive automatic approval within three days.")
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["verified"] is False
    assert response.json["evidence_status"] == "unsupported_claims"
    assert response.json["citations"] == []
    assert "could not find sufficient supporting information" in response.json["answer"]


def test_contradictory_negation_is_not_presented_as_supported(client, app, monkeypatch):
    add_verified_evidence(app)
    provider = EvidenceMockProvider(
        "The public authority shall not provide information within thirty days of an application."
    )
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["verified"] is False
    assert response.json["evidence_status"] == "unsupported_claims"


def test_missing_provider_uses_exact_retrieved_passage(client, app, monkeypatch):
    add_verified_evidence(app)
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=None))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["evidence_status"] == "supported"
    assert response.json["verified"] is True
    assert "[1]" in response.json["answer"]
    assert "within thirty days" in response.json["answer"]
    assert len(response.json["citations"]) == 1
    assert len(response.json["sources"]) == 1


def test_malformed_provider_response_fails_closed(client, app, monkeypatch):
    add_verified_evidence(app)
    provider = EvidenceMockProvider(malformed=True)
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["evidence_status"] == "generation_error"
    assert response.json["verified"] is False
    assert response.json["citations"] == []


def test_currentness_question_abstains_without_effective_status_metadata(client, app, monkeypatch):
    add_verified_evidence(app)
    with app.app_context():
        document = LegalSourceDocument.query.one()
        document.commencement_date = date(2020, 1, 1)
        document.amendment_status = "unknown"
        db.session.commit()
    provider = EvidenceMockProvider()
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "Is this authority information time limit currently in force?"},
    )
    assert response.status_code == 200
    assert response.json["verified"] is False
    assert response.json["evidence_status"] == "currentness_unverified"


def test_conflicting_verified_sources_cause_abstention(client, app, monkeypatch):
    add_verified_evidence(app)
    with app.app_context():
        conflicting_document = LegalSourceDocument(
            title="Another test fixture",
            document_type="Test fixture",
            act_or_rule_name="Test fixture only",
            original_filename="another-source.pdf",
            verification_status="verified",
        )
        conflicting_document.chunks.append(
            EvidenceChunk(
                section_number="section-recorded-in-source",
                paragraph_number="different-test-paragraph",
                page_number=12,
                extracted_text=(
                    "The public authority shall provide information within "
                    "forty days of receipt of an application."
                ),
                content_hash="b" * 64,
                verification_status="verified",
            )
        )
        db.session.add(conflicting_document)
        db.session.commit()
    provider = Mock()
    monkeypatch.setattr("backend.services.ai_service.get_provider", provider)
    register(client)
    response = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    assert response.status_code == 200
    assert response.json["verified"] is False
    assert response.json["evidence_status"] == "conflicting_sources"
    assert len(response.json["sources"]) == 2
    provider.assert_not_called()


def test_follow_up_context_is_sent_to_the_provider(client, app, monkeypatch):
    add_verified_evidence(app)
    register(client)
    first = client.post(
        "/api/chat",
        json={"message": "What information time limit does the authority provide?"},
    )
    provider = EvidenceMockProvider()
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=provider))
    client.post(
        "/api/chat",
        json={
            "message": "Please explain that further.",
            "conversation_id": first.json["conversation_id"],
        },
    )
    history_text = "\n".join(message["content"] for message in provider.messages[:-1])
    assert "What information time limit does the authority provide?" in history_text


def test_question_context_detects_named_state_scope():
    from backend.services.context_service import classify_question

    assert classify_question("What does this rule say in Kerala?")["state_or_local_scope_specified"] is True
    assert classify_question("What does this rule say?")["state_or_local_scope_specified"] is False


def test_provider_configuration_rejects_bad_endpoint_and_timeout():
    from backend.services.llm_provider import ProviderError, get_provider

    base_config = {
        "AI_PROVIDER": "openai_compatible",
        "AI_API_KEY": "test-key",
        "AI_API_URL": "not-a-url",
        "AI_MODEL": "test-model",
        "AI_TIMEOUT_SECONDS": 30,
    }
    with pytest.raises(ProviderError):
        get_provider(base_config)
    base_config["AI_API_URL"] = "https://provider.example/v1/chat/completions"
    base_config["AI_TIMEOUT_SECONDS"] = "not-a-number"
    with pytest.raises(ProviderError):
        get_provider(base_config)


def test_chat_rejects_empty_question(client):
    register(client)
    assert client.post("/api/chat", json={"message": "  "}).status_code == 400


def test_document_upload_extracts_csv_then_requires_admin_verification(client, app, monkeypatch):
    register(client)
    payload = {"file": (io.BytesIO(b"Rule 1: direct selling applies."), "source.txt")}
    assert client.post("/api/documents", data=payload).status_code == 403

    with app.app_context():
        admin_user = User.query.filter_by(email="user@example.com").one()
        admin_user.role = "admin"
        db.session.commit()

    assert client.post(
        "/api/documents",
        data={"file": (io.BytesIO(b"not a PDF"), "broken.pdf")},
        content_type="multipart/form-data",
    ).status_code == 400

    content = io.StringIO()
    writer = csv.writer(content, delimiter="\t")
    writer.writerow(
        [
            "document_id",
            "domain",
            "document_name",
            "page_number",
            "content",
            "source_authority",
            "source_file_path",
            "extraction_method",
            "verification_status",
            "page_type",
        ]
    )
    passage = "Rule 1: These rules apply to direct selling entities."
    writer.writerow(
        [
            "DOC_001",
            "Consumer Protection",
            "Consumer_Direct_Selling_Rules_2021.pdf",
            "1",
            passage,
            "",
            "",
            "text",
            "Pending review",
            "Text",
        ]
    )
    response = client.post(
        "/api/documents",
        data={"file": (io.BytesIO(content.getvalue().encode("utf-8")), "legal.csv.xls")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    document_id = response.json["document"]["id"]
    assert response.json["document"]["processing_status"] == "processed"
    assert response.json["document"]["source_count"] == 1
    assert response.json["document"]["chunk_count"] == 1
    assert "remain unverified" in response.json["message"]
    assert client.get("/api/knowledge/status").json["available"] is False
    listed = client.get("/api/documents").json["documents"]
    assert listed[0]["filename"] == "legal.csv.xls"
    source = listed[0]["sources"][0]
    assert source["verification_status"] == "unverified"
    assert source["preview"] == passage
    assert source["file_url"] == f"/api/documents/{document_id}/file"

    with app.app_context():
        legal_source = LegalSourceDocument.query.one()
        source_id = legal_source.id
        assert legal_source.chunks[0].verification_status == "unverified"
        uploaded_document = Document.query.one()
        assert uploaded_document.file_data == content.getvalue().encode("utf-8")
    file_response = client.get(f"/api/documents/{document_id}/file")
    assert file_response.status_code == 200
    assert file_response.data == content.getvalue().encode("utf-8")
    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=None))
    unavailable = client.post(
        "/api/chat",
        json={"message": "What do the direct selling rules apply to?"},
    )
    assert unavailable.json["evidence_status"] == "insufficient_evidence"

    rejected = client.post(f"/api/legal-sources/{source_id}/reject", json={})
    assert rejected.status_code == 200
    assert rejected.json["verification_status"] == "rejected"
    assert client.get("/api/knowledge/status").json["pending_sources"] == 0
    rejected_source = client.get("/api/documents").json["documents"][0]["sources"][0]
    assert rejected_source["verification_status"] == "rejected"
    rejected_chat = client.post(
        "/api/chat",
        json={"message": "What do the direct selling rules apply to?"},
    )
    assert rejected_chat.json["evidence_status"] == "insufficient_evidence"
    assert rejected_chat.json["sources"] == []

    verified = client.post(f"/api/legal-sources/{source_id}/verify", json={})
    assert verified.status_code == 200
    assert client.get("/api/knowledge/status").json["available"] is True
    answer = client.post(
        "/api/chat",
        json={"message": "What do the direct selling rules apply to?"},
    )
    assert answer.status_code == 200
    assert answer.json["verified"] is True
    assert passage in answer.json["answer"]
    assert answer.json["citations"][0]["filename"] == "Consumer_Direct_Selling_Rules_2021.pdf"
    assert answer.json["citations"][0]["page"] == 1
    assert answer.json["citations"][0]["file_url"] == f"/api/documents/{document_id}/file"
    app.config["MAX_UPLOAD_BYTES"] = 10
    oversized = client.post(
        "/api/documents",
        data={"file": (io.BytesIO(b"this file is too large"), "large.txt")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413
    with app.app_context():
        assert Document.query.count() == 1


def test_pdf_upload_chunks_pages_and_retrieves_exact_cited_evidence(client, app, monkeypatch):
    register(client)
    with app.app_context():
        user = User.query.filter_by(email="user@example.com").one()
        user.role = "admin"
        db.session.commit()

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    for text in (
        "Rule 1 applies to direct selling. " + "Supporting passage content. " * 120,
        "Rule 2 requires a seller to provide a receipt within 10 days.",
    ):
        page = writer.add_blank_page(width=300, height=300)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(
            f"BT /F1 12 Tf 30 200 Td ({text}) Tj ET".encode("ascii")
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)

    response = client.post(
        "/api/documents",
        data={"file": (io.BytesIO(pdf.getvalue()), "rules.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    assert response.json["document"]["chunk_count"] >= 3
    with app.app_context():
        source = LegalSourceDocument.query.one()
        source_id = source.id
        chunks = source.chunks
        assert {chunk.page_number for chunk in chunks} == {1, 2}
        assert sum(chunk.page_number == 1 for chunk in chunks) >= 2
        assert any(chunk.page_number == 2 and chunk.section_number == "2" for chunk in chunks)
        assert all(chunk.verification_status == "unverified" for chunk in chunks)

    monkeypatch.setattr("backend.services.ai_service.get_provider", Mock(return_value=None))
    verified = client.post(f"/api/legal-sources/{source_id}/verify", json={})
    assert verified.status_code == 200
    answer = client.post(
        "/api/chat",
        json={"message": "Rule 2"},
    )
    assert answer.status_code == 200
    assert answer.json["verified"] is True
    assert "Rule 2 requires a seller to provide a receipt within 10 days." in answer.json["answer"]
    assert answer.json["citations"][0]["page"] == 2
    assert answer.json["citations"][0]["section"] == "2"
    assert answer.json["citations"][0]["filename"] == "rules.pdf"


def test_csrf_protects_state_changing_json_requests(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "csrf-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "csrf.sqlite"),
            "UPLOAD_FOLDER": str(tmp_path / "csrf-uploads"),
        }
    )
    with app.app_context():
        db.create_all()
    response = app.test_client().post(
        "/api/auth/register",
        json={"username": "Test User", "email": "user@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 400

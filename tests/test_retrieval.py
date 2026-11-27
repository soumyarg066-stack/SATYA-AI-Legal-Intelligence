import pytest

from backend import create_app
from backend.extensions import db
from backend.models import EvidenceChunk, LegalSourceDocument
from backend.services.retrieval_service import retrieve_evidence


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "retrieval_test.sqlite"),
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


def _register_and_login(client):
    res = client.post(
        "/api/auth/register",
        json={
            "username": "Legal Researcher",
            "email": "researcher@example.com",
            "password": "strong-password-1",
        },
    )
    assert res.status_code == 201


def _seed_legal_documents(app):
    with app.app_context():
        verified_doc = LegalSourceDocument(
            title="Consumer Protection (Direct Selling) Rules, 2021",
            document_type="Legal source",
            act_or_rule_name="Consumer Protection (Direct Selling) Rules, 2021",
            original_filename="Consumer_Direct_Selling_Rules_2021.pdf",
            domain="Consumer Protection",
            verification_status="verified",
        )
        verified_doc.chunks.extend(
            [
                EvidenceChunk(
                    section_number="10",
                    section_title="Prohibition of Pyramid Scheme",
                    page_number=15,
                    extracted_text=(
                        "10. Prohibition of Pyramid Scheme and money circulation scheme. "
                        "No direct selling entity or direct seller shall promote a Pyramid Scheme "
                        "or participate in money circulation scheme."
                    ),
                    content_hash="1" * 64,
                    verification_status="verified",
                ),
                EvidenceChunk(
                    section_number="5",
                    section_title="Obligations of direct selling entity",
                    page_number=12,
                    extracted_text=(
                        "Every direct selling entity shall appoint a grievance redressal officer "
                        "who acknowledges any consumer complaint within forty-eight working hours."
                    ),
                    content_hash="2" * 64,
                    verification_status="verified",
                ),
                EvidenceChunk(
                    section_number="10",
                    section_title="Prohibition of Pyramid Scheme (Hindi)",
                    page_number=8,
                    extracted_text=(
                        "10. पिरामिड स्कीम और धन परिचालन स्कीम का प्रतिषेध: "
                        "कोई भी प्रत्यक्ष बिक्री इकाई पिरामिड स्कीम को बढ़ावा नहीं देगी।"
                    ),
                    content_hash="3" * 64,
                    verification_status="verified",
                ),
            ]
        )

        unverified_doc = LegalSourceDocument(
            title="Draft Unverified Rules",
            document_type="Legal source",
            original_filename="Draft_Unverified_Rules.pdf",
            verification_status="unverified",
        )
        unverified_doc.chunks.append(
            EvidenceChunk(
                section_number="99",
                page_number=4,
                extracted_text=(
                    "Unverified draft pyramid scheme grievance redressal officer forty-eight hours."
                ),
                content_hash="4" * 64,
                verification_status="unverified",
            )
        )

        rejected_doc = LegalSourceDocument(
            title="Rejected Source",
            document_type="Legal source",
            original_filename="Rejected_Source.pdf",
            verification_status="rejected",
        )
        rejected_doc.chunks.append(
            EvidenceChunk(
                section_number="88",
                page_number=2,
                extracted_text="Rejected pyramid scheme text that must never be returned.",
                content_hash="5" * 64,
                verification_status="rejected",
            )
        )

        db.session.add_all([verified_doc, unverified_doc, rejected_doc])
        db.session.commit()


def test_keyword_retrieval_returns_only_verified_passages_with_provenance(app):
    _seed_legal_documents(app)
    with app.app_context():
        results = retrieve_evidence("What is the prohibition on Pyramid Scheme?")
        assert len(results) >= 1
        top = results[0]
        assert top["document_name"] == "Consumer_Direct_Selling_Rules_2021.pdf"
        assert top["page_number"] == 15
        assert "Prohibition of Pyramid Scheme" in top["passage"]
        assert "pyramid" in top["matched_keywords"]
        assert all(
            item["document_name"] == "Consumer_Direct_Selling_Rules_2021.pdf"
            for item in results
        )


def test_keyword_retrieval_excludes_unverified_chunks_even_on_verified_doc(app):
    _seed_legal_documents(app)
    with app.app_context():
        doc = LegalSourceDocument.query.filter_by(verification_status="verified").one()
        doc.chunks.append(
            EvidenceChunk(
                section_number="77",
                page_number=99,
                extracted_text="Unique unverified keyword xylophone_clause inside verified doc.",
                content_hash="6" * 64,
                verification_status="unverified",
            )
        )
        db.session.commit()
        assert retrieve_evidence("xylophone_clause") == []


def test_keyword_retrieval_supports_unicode_and_deduplicates(app):
    _seed_legal_documents(app)
    with app.app_context():
        # Add an exact duplicate verified chunk on the same document/page
        doc = LegalSourceDocument.query.filter_by(verification_status="verified").one()
        doc.chunks.append(
            EvidenceChunk(
                section_number="10",
                page_number=15,
                extracted_text=(
                    "10. Prohibition of Pyramid Scheme and money circulation scheme. "
                    "No direct selling entity or direct seller shall promote a Pyramid Scheme "
                    "or participate in money circulation scheme."
                ),
                content_hash="7" * 64,
                verification_status="verified",
            )
        )
        db.session.commit()

        results = retrieve_evidence("Prohibition of Pyramid Scheme")
        pages_and_passages = [(item["page_number"], item["passage"]) for item in results]
        assert len(pages_and_passages) == len(set(pages_and_passages))

        hindi_results = retrieve_evidence("पिरामिड स्कीम")
        assert len(hindi_results) == 1
        assert hindi_results[0]["page_number"] == 8
        assert hindi_results[0]["document_name"] == "Consumer_Direct_Selling_Rules_2021.pdf"


def test_retrieval_endpoint_and_chat_integration(client, app):
    assert client.get("/api/retrieval?q=pyramid").status_code == 401
    _seed_legal_documents(app)
    _register_and_login(client)

    assert client.get("/api/retrieval").status_code == 400
    assert client.post("/api/retrieval", json={"query": "pyramid", "limit": 99}).status_code == 400

    res = client.get("/api/retrieval?q=grievance+redressal+officer+hours")
    assert res.status_code == 200
    data = res.get_json()
    assert data["verified_only"] is True
    assert data["count"] == 1
    match = data["results"][0]
    assert match["document_name"] == "Consumer_Direct_Selling_Rules_2021.pdf"
    assert match["page_number"] == 12
    assert "grievance redressal officer" in match["passage"]

    empty_res = client.post("/api/retrieval", json={"query": "nonexistent_statute_xyz"})
    assert empty_res.status_code == 200
    assert empty_res.get_json()["count"] == 0
    assert "No matching passages" in empty_res.get_json()["message"]

    chat_res = client.post(
        "/api/chat",
        json={"message": "What is the grievance redressal officer timeline?"},
    )
    assert chat_res.status_code == 200
    chat_json = chat_res.get_json()
    assert chat_json["verified"] is True
    assert len(chat_json["matches"]) == 1
    assert chat_json["matches"][0]["document_name"] == "Consumer_Direct_Selling_Rules_2021.pdf"
    assert chat_json["matches"][0]["page_number"] == 12
    assert "forty-eight working hours" in chat_json["matches"][0]["passage"]
    assert chat_json["citations"][0]["act_name"] == "Consumer Protection (Direct Selling) Rules, 2021"
    assert chat_json["citations"][0]["section"] == "5"
    assert chat_json["citations"][0]["page"] == 12

    # Switching topics in the same conversation still retrieves the new topic cleanly
    topic_b = client.post(
        "/api/chat",
        json={
            "message": "Pyramid Scheme prohibition",
            "conversation_id": chat_json["conversation_id"],
        },
    )
    assert topic_b.status_code == 200
    topic_b_json = topic_b.get_json()
    assert topic_b_json["verified"] is True
    assert topic_b_json["citations"][0]["section"] == "10"
    assert topic_b_json["citations"][0]["page"] == 15

    # Missing evidence abstains cleanly without fabricating citations (even if generic terms like 'regulations' appear)
    abstain = client.post(
        "/api/chat",
        json={
            "message": "What are the maritime spaceport regulations?",
            "conversation_id": chat_json["conversation_id"],
        },
    )
    assert abstain.status_code == 200
    abstain_json = abstain.get_json()
    assert abstain_json["verified"] is False
    assert abstain_json["evidence_status"] == "insufficient_evidence"
    assert abstain_json["citations"] == []
    assert abstain_json["sources"] == []
    assert abstain_json["matches"] == []


def test_gazette_legal_reference_extraction_and_non_fabrication(app):
    from backend.services.legal_reference_service import extract_legal_references

    gazette_text = (
        "2. Definitions. — (1) In these rules, unless the context otherwise requires, –\n"
        "(a) “Act” means the Digital Personal Data Protection Act, 2023 (22 of 2023);\n"
        "(b) “techno-legal measures” means as referred to under rules 20 and 22;\n"
        "(2) The words and expressions used in these rules and not defined...\n"
        "3. Notice given by Data Fiduciary to Data Principal. —The notice given..."
    )
    refs = extract_legal_references(gazette_text)
    assert refs["section_number"] == "2, 3"
    assert "Definitions" in refs["section_title"]
    assert "Notice given by Data Fiduciary" in refs["section_title"]
    assert refs["subsection"] == "(1), (2)"
    assert refs["paragraph_number"] == "(a), (b)"

    plain_chunk = "employees of the Board and their eligible dependants."
    empty_refs = extract_legal_references(plain_chunk)
    assert empty_refs == {
        "section_number": None,
        "section_title": None,
        "subsection": None,
        "paragraph_number": None,
    }

    with app.app_context():
        doc = LegalSourceDocument(
            title="Digital_Personal_Data_Protection_Rules_2025.pdf",
            document_type="Legal source",
            act_or_rule_name="Digital Personal Data Protection Rules 2025",
            original_filename="Digital_Personal_Data_Protection_Rules_2025.pdf",
            verification_status="verified",
        )
        doc.chunks.append(
            EvidenceChunk(
                page_number=24,
                extracted_text=gazette_text,
                content_hash="9" * 64,
                verification_status="verified",
            )
        )
        db.session.add(doc)
        db.session.commit()

        results = retrieve_evidence("What is the notice given by Data Fiduciary?")
        assert len(results) == 1
        assert results[0]["page_number"] == 24
        assert results[0]["section"] == "2, 3"
        assert results[0]["subsection"] == "(1), (2)"
        assert results[0]["paragraph"] == "(a), (b)"

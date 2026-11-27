import json
import pytest

from backend import create_app
from backend.extensions import db
from backend.models import EvidenceChunk, LegalSourceDocument
from backend.services.ai_service import answer_question
from backend.services.language_service import normalize_language
from backend.services.prompt_service import build_provider_messages


@pytest.fixture
def app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key-not-for-production",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "language_test.sqlite"),
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
            "username": "Multilingual Researcher",
            "email": "multilingual@example.com",
            "password": "strong-password-1",
        },
    )
    assert res.status_code == 201


def _seed_verified_rule(app):
    with app.app_context():
        doc = LegalSourceDocument(
            title="Consumer Protection (Direct Selling) Rules, 2021",
            document_type="Legal source",
            act_or_rule_name="Consumer Protection (Direct Selling) Rules, 2021",
            original_filename="Consumer_Direct_Selling_Rules_2021.pdf",
            domain="Consumer Protection",
            verification_status="verified",
        )
        doc.chunks.append(
            EvidenceChunk(
                section_number="10",
                section_title="Prohibition of Pyramid Scheme",
                paragraph_number="(1)",
                page_number=15,
                extracted_text=(
                    "10. Prohibition of Pyramid Scheme and money circulation scheme. "
                    "No direct selling entity or direct seller shall promote a Pyramid Scheme "
                    "or participate in money circulation scheme."
                ),
                content_hash="a" * 64,
                verification_status="verified",
            )
        )
        db.session.add(doc)
        db.session.commit()


def test_normalize_language_accepts_supported_values_and_rejects_others():
    assert normalize_language(None) == "en"
    assert normalize_language("") == "en"
    assert normalize_language("en") == "en"
    assert normalize_language("kn") == "kn"
    assert normalize_language("Kannada") == "kn"
    assert normalize_language("ಕನ್ನಡ") == "kn"
    assert normalize_language("hi") == "hi"
    assert normalize_language("Hindi") == "hi"
    assert normalize_language("हिन्दी") == "hi"

    with pytest.raises(ValueError):
        normalize_language("fr")
    with pytest.raises(ValueError):
        normalize_language(123)


def test_chatbot_renders_language_selector_and_api_validates_language(app, client):
    _register_and_login(client)
    page = client.get("/chat")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="chatLanguage"' in html
    assert 'value="en"' in html
    assert 'value="kn"' in html
    assert 'value="hi"' in html

    bad = client.post("/api/chat", json={"message": "Pyramid Scheme?", "language": "es"})
    assert bad.status_code == 400
    assert "Unsupported language" in bad.json["error"]


def test_chat_abstains_in_selected_language_when_no_documents_or_missing_evidence(app, client):
    _register_and_login(client)

    kn_no_docs = client.post(
        "/api/chat",
        json={"message": "What does Rule 10 say about Pyramid Scheme?", "language": "kn"},
    )
    assert kn_no_docs.status_code == 200
    assert kn_no_docs.json["language"] == "kn"
    assert kn_no_docs.json["verified"] is False
    assert "ಜ್ಞಾನಕೋಶದಲ್ಲಿ" in kn_no_docs.json["answer"]

    hi_no_docs = client.post(
        "/api/chat",
        json={"message": "What does Rule 10 say about Pyramid Scheme?", "language": "hi"},
    )
    assert hi_no_docs.status_code == 200
    assert hi_no_docs.json["language"] == "hi"
    assert hi_no_docs.json["verified"] is False
    assert "ज्ञानकोष में" in hi_no_docs.json["answer"]

    _seed_verified_rule(app)

    kn_missing = client.post(
        "/api/chat",
        json={"message": "cryptocurrency mining tax slab 999", "language": "kn"},
    )
    assert kn_missing.status_code == 200
    assert kn_missing.json["evidence_status"] == "insufficient_evidence"
    assert "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳಲ್ಲಿ" in kn_missing.json["answer"]

    hi_missing = client.post(
        "/api/chat",
        json={"message": "cryptocurrency mining tax slab 999", "language": "hi"},
    )
    assert hi_missing.status_code == 200
    assert hi_missing.json["evidence_status"] == "insufficient_evidence"
    assert "सत्यापित कानूनी दस्तावेज़ों में" in hi_missing.json["answer"]


def test_chat_verbatim_multilingual_keeps_citations_and_evidence_panel_intact(app, client):
    _register_and_login(client)
    _seed_verified_rule(app)

    for lang, expected_marker in [
        ("en", "Consumer Protection (Direct Selling) Rules, 2021"),
        ("kn", "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು"),
        ("hi", "सत्यापित कानूनी"),
    ]:
        res = client.post(
            "/api/chat",
            json={"message": "Rule 10 Prohibition of Pyramid Scheme", "language": lang},
        )
        assert res.status_code == 200
        data = res.json
        assert data["verified"] is True
        assert data["language"] == lang
        assert expected_marker in data["answer"]
        assert "Consumer Protection (Direct Selling) Rules, 2021" in data["answer"]
        assert "No direct selling entity or direct seller shall promote a Pyramid Scheme" in data["answer"]
        assert len(data["sources"]) == 1
        source = data["sources"][0]
        assert source["filename"] == "Consumer_Direct_Selling_Rules_2021.pdf"
        assert source["act_name"] == "Consumer Protection (Direct Selling) Rules, 2021"
        assert source["section"] == "10"
        assert source["paragraph"] == "(1)"
        assert source["page"] == 15
        assert "Prohibition of Pyramid Scheme" in source["excerpt"]


class _CapturingProvider:
    def __init__(self, claims):
        self._claims = claims
        self.messages = None

    def generate(self, messages):
        self.messages = messages
        return self._claims


def test_prompt_and_ai_service_verify_kannada_and_hindi_claims_preserving_citations(app):
    _seed_verified_rule(app)
    with app.app_context():
        evidence_msgs = build_provider_messages(
            "What does Rule 10 say?",
            evidence=[
                {
                    "id": "chunk-10",
                    "document_title": "Consumer Protection (Direct Selling) Rules, 2021",
                    "document_name": "Consumer_Direct_Selling_Rules_2021.pdf",
                    "act_name": "Consumer Protection (Direct Selling) Rules, 2021",
                    "section": "10",
                    "subsection": None,
                    "paragraph": "(1)",
                    "page": 15,
                    "excerpt": "10. Prohibition of Pyramid Scheme.",
                    "publication_date": None,
                    "commencement_date": None,
                    "amendment_status": "unknown",
                }
            ],
            language="kn",
        )
        assert "Kannada (ಕನ್ನಡ)" in evidence_msgs[0]["content"]
        assert json.loads(evidence_msgs[-1]["content"])["response_language"]["code"] == "kn"

        en_first = answer_question("What does Rule 10 say about Pyramid Scheme?")
        ev_id = en_first["sources"][0]["id"]

        kn_provider = _CapturingProvider(
            [
                {
                    "text": (
                        "Consumer Protection (Direct Selling) Rules, 2021 ರ Rule 10 ರ ಪ್ರಕಾರ, "
                        "ಯಾವುದೇ ನೇರ ಮಾರಾಟ ಸಂಸ್ಥೆಯು Pyramid Scheme ಅನ್ನು ಪ್ರಚಾರ ಮಾಡಬಾರದು."
                    ),
                    "source_claim": (
                        "Under Rule 10, no direct selling entity shall promote a Pyramid Scheme."
                    ),
                    "evidence_ids": [ev_id],
                }
            ]
        )
        kn_result = answer_question(
            "What does Rule 10 say about Pyramid Scheme?",
            provider=kn_provider,
            language="kn",
        )
        assert kn_result["verified"] is True
        assert kn_result["language"] == "kn"
        assert "Consumer Protection (Direct Selling) Rules, 2021" in kn_result["answer"]
        assert "Rule 10" in kn_result["answer"]
        assert "ಯಾವುದೇ ನೇರ ಮಾರಾಟ ಸಂಸ್ಥೆಯು" in kn_result["answer"]
        assert kn_result["sources"][0]["filename"] == "Consumer_Direct_Selling_Rules_2021.pdf"

        hi_provider = _CapturingProvider(
            [
                {
                    "text": (
                        "Consumer Protection (Direct Selling) Rules, 2021 के Rule 10 के अनुसार, "
                        "कोई भी प्रत्यक्ष बिक्री इकाई Pyramid Scheme को बढ़ावा नहीं देगी।"
                    ),
                    "evidence_ids": [ev_id],
                }
            ]
        )
        hi_result = answer_question(
            "What does Rule 10 say about Pyramid Scheme?",
            provider=hi_provider,
            language="hi",
        )
        assert hi_result["verified"] is True
        assert hi_result["language"] == "hi"
        assert "Consumer Protection (Direct Selling) Rules, 2021" in hi_result["answer"]
        assert "Rule 10" in hi_result["answer"]
        assert "प्रत्यक्ष बिक्री इकाई" in hi_result["answer"]

        bad_num_provider = _CapturingProvider(
            [
                {
                    "text": "Rule 999 के अनुसार यह नियम लागू है।",
                    "evidence_ids": [ev_id],
                }
            ]
        )
        rejected = answer_question(
            "What does Rule 10 say about Pyramid Scheme?",
            provider=bad_num_provider,
            language="hi",
        )
        assert rejected["verified"] is False
        assert rejected["evidence_status"] == "unsupported_claims"
        assert "सत्यापित कानूनी दस्तावेज़ों में" in rejected["answer"]


def test_localized_api_errors_and_native_script_missing_evidence_refusal(app, client):
    unauth_kn = client.post(
        "/api/chat",
        headers={"X-Satya-Language": "kn"},
        json={"message": "test"},
    )
    assert unauth_kn.status_code == 401
    assert "ಲಾಗಿನ್" in unauth_kn.json["error"]

    unauth_hi = client.post(
        "/api/chat",
        headers={"X-Satya-Language": "hi"},
        json={"message": "test"},
    )
    assert unauth_hi.status_code == 401
    assert "लॉगिन" in unauth_hi.json["error"]

    _register_and_login(client)
    _seed_verified_rule(app)

    kn_native_missing = client.post(
        "/api/chat",
        json={"message": "ಮಕ್ಕಳ ವೈಯಕ್ತಿಕ ದತ್ತಾಂಶಕ್ಕೆ ಸಂಬಂಧಿಸಿದ ನಿಯಮಗಳು ಯಾವುವು?", "language": "kn"},
    )
    assert kn_native_missing.status_code == 200
    assert kn_native_missing.json["verified"] is False
    assert kn_native_missing.json["evidence_status"] == "insufficient_evidence"
    assert kn_native_missing.json["language"] == "kn"
    assert "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳಲ್ಲಿ" in kn_native_missing.json["answer"]
    assert "I could not find" not in kn_native_missing.json["answer"]

    hi_native_missing = client.post(
        "/api/chat",
        json={"message": "डेटा सुरक्षा बोर्ड के बारे में नियम क्या हैं?", "language": "hi"},
    )
    assert hi_native_missing.status_code == 200
    assert hi_native_missing.json["verified"] is False
    assert hi_native_missing.json["evidence_status"] == "insufficient_evidence"
    assert hi_native_missing.json["language"] == "hi"
    assert "सत्यापित कानूनी दस्तावेज़ों में" in hi_native_missing.json["answer"]
    assert "I could not find" not in hi_native_missing.json["answer"]

    empty_kn = client.post("/api/chat", json={"message": "   ", "language": "kn"})
    assert empty_kn.status_code == 400
    assert "ಪ್ರಶ್ನೆ" in empty_kn.json["error"]

    missing_conv_hi = client.post(
        "/api/chat",
        json={"message": "Pyramid Scheme", "conversation_id": 99999, "language": "hi"},
    )
    assert missing_conv_hi.status_code == 404
    assert "संवाद नहीं मिला" in missing_conv_hi.json["error"]

    bad_lang_kn = client.post(
        "/api/chat",
        headers={"X-Satya-Language": "kn"},
        json={"message": "Pyramid Scheme", "language": "fr"},
    )
    assert bad_lang_kn.status_code == 400
    assert "ಬೆಂಬಲಿತವಲ್ಲದ ಭಾಷೆ" in bad_lang_kn.json["error"]


def test_auto_responds_in_question_language_even_when_selector_is_english(app, client):
    _register_and_login(client)
    with app.app_context():
        dpdp_doc = LegalSourceDocument(
            title="Digital Personal Data Protection Rules 2025",
            document_type="Legal source",
            act_or_rule_name="Digital Personal Data Protection Rules, 2025",
            original_filename="Digital_Personal_Data_Protection_Rules_2025.pdf",
            domain="Digital Privacy",
            verification_status="verified",
        )
        dpdp_doc.chunks.append(
            EvidenceChunk(
                section_number="14",
                section_title="Rights of Data Principal",
                paragraph_number="(1)",
                page_number=31,
                extracted_text=(
                    "14. Rights of Data Principal. A Data Principal may make a request to a "
                    "Data Fiduciary to obtain information, correction, completion, updating or "
                    "erasure of personal data under the Digital Personal Data Protection Rules 2025."
                ),
                content_hash="b" * 64,
                verification_status="verified",
            )
        )
        db.session.add(dpdp_doc)
        db.session.commit()

    kn_res = client.post(
        "/api/chat",
        json={
            "message": (
                "ಡಿಜಿಟಲ್ ವೈಯಕ್ತಿಕ ಡೇಟಾ ಸಂರಕ್ಷಣಾ ನಿಯಮಗಳು, 2025 ರ ಪ್ರಕಾರ ವ್ಯಕ್ತಿಯ ಹಕ್ಕುಗಳು ಯಾವುವು? "
                "ಪರಿಶೀಲಿಸಲಾದ ಕಾನೂನು ಮೂಲಗಳನ್ನು ಮಾತ್ರ ಆಧರಿಸಿ ವಿವರಿಸಿ."
            ),
            "language": "en",
        },
    )
    assert kn_res.status_code == 200
    assert kn_res.json["language"] == "kn"
    assert kn_res.json["verified"] is True
    assert "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು" in kn_res.json["answer"]
    assert "Rights of Data Principal" in kn_res.json["answer"]
    assert kn_res.json["sources"][0]["filename"] == "Digital_Personal_Data_Protection_Rules_2025.pdf"
    assert kn_res.json["sources"][0]["section"] == "14"

    kn_unmatched = client.post(
        "/api/chat",
        json={
            "message": "ಅನಿಯಂತ್ರಿತ ಬಾಹ್ಯಾಕಾಶ ಗಣಿಗಾರಿಕೆ ನಿಯಮಗಳು ಯಾವುವು?",
            "language": "en",
        },
    )
    assert kn_unmatched.status_code == 200
    assert kn_unmatched.json["language"] == "kn"
    assert kn_unmatched.json["verified"] is False
    assert kn_unmatched.json["evidence_status"] == "insufficient_evidence"
    assert "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳಲ್ಲಿ" in kn_unmatched.json["answer"]
    assert "I could not find" not in kn_unmatched.json["answer"]

    hi_res = client.post(
        "/api/chat",
        json={
            "message": "डिजिटल व्यक्तिगत डेटा संरक्षण नियम 2025 के तहत अधिकार क्या हैं?",
            "language": "en",
        },
    )
    assert hi_res.status_code == 200
    assert hi_res.json["language"] == "hi"
    assert hi_res.json["verified"] is True
    assert "सत्यापित कानूनी" in hi_res.json["answer"]
    assert hi_res.json["sources"][0]["filename"] == "Digital_Personal_Data_Protection_Rules_2025.pdf"


def test_cross_page_rule14_assembly_polluted_ref_cleanup_and_local_llm(app, client):
    from backend.services.legal_reference_service import enrich_chunk_references, extract_legal_references
    from backend.services.llm_provider import OpenAICompatibleProvider, ProviderError, get_provider

    dirty_prose = "clause (b) of sub-\nsection 7 and for processing of personal data necessary for the purposes"
    clean_refs = extract_legal_references(dirty_prose)
    assert clean_refs["section_number"] is None
    assert clean_refs["section_title"] is None

    repaired = enrich_chunk_references(
        {
            "section": "7",
            "section_title": "and for processing of personal data",
            "paragraph": None,
            "excerpt": "26 THE GAZETTE OF INDIA [PART II—SEC. 3(i)] 6. Reasonable security safeguards. — (1) A Data Fiduciary shall protect personal data.",
        }
    )
    assert repaired["section"] == "6"
    assert repaired["section_title"] == "Reasonable security safeguards"

    local_provider = get_provider(
        {
            "AI_PROVIDER": "openai_compatible",
            "AI_API_KEY": "",
            "AI_API_URL": "http://127.0.0.1:11434/v1/chat/completions",
            "AI_MODEL": "llama3",
            "AI_TIMEOUT_SECONDS": 15,
        }
    )
    assert isinstance(local_provider, OpenAICompatibleProvider)
    with pytest.raises(ProviderError):
        get_provider(
            {
                "AI_PROVIDER": "openai_compatible",
                "AI_API_KEY": "",
                "AI_API_URL": "https://api.example.com/v1/chat/completions",
                "AI_MODEL": "gpt-4o-mini",
            }
        )

    _register_and_login(client)
    with app.app_context():
        doc = LegalSourceDocument(
            title="Digital Personal Data Protection Rules 2025",
            document_type="Legal source",
            act_or_rule_name="Digital Personal Data Protection Rules 2025",
            original_filename="Digital_Personal_Data_Protection_Rules_2025.pdf",
            verification_status="verified",
        )
        doc.chunks.extend(
            [
                EvidenceChunk(
                    page_number=24,
                    extracted_text=(
                        "1. Short title and commencement.—(1) These rules may be called the "
                        "Digital Personal Data Protection Rules, 2025."
                    ),
                    content_hash="d" * 64,
                    verification_status="verified",
                ),
                EvidenceChunk(
                    page_number=29,
                    extracted_text=(
                        "14. Rights of Data Principals. — (1) For enabling Data Principals to exercise "
                        "their rights under the Act, the Data Fiduciary and, where applicable, the Consent "
                        "Manager, shall prominently publish on its website or app, or both, as the case may be, —"
                    ),
                    content_hash="e" * 64,
                    verification_status="verified",
                ),
                EvidenceChunk(
                    page_number=30,
                    extracted_text=(
                        "30\nTHE GAZETTE OF INDIA : EXTRAORDINARY\n[PART II—SEC. 3(i)]\n"
                        "(a) the details of the means using which a Data Principal may make a request for "
                        "the exercise of such rights; and\n"
                        "(b) the particulars, if any, such as the username or other identifier.\n"
                        "(2) To exercise the rights of the Data Principal under the Act, she may make a "
                        "request to the Data Fiduciary to whom she has previously given consent.\n"
                        "(3) Every Data Fiduciary and Consent Manager shall prominently publish on its website "
                        "or app within a reasonable period not exceeding ninety days under its grievance redressal system.\n"
                        "(4) To exercise the rights of the Data Principal under the Act, she may nominate one or more individuals.\n"
                        "15. Transfer of personal data outside the territory of India.— Any personal data..."
                    ),
                    content_hash="f" * 64,
                    verification_status="verified",
                ),
            ]
        )
        db.session.add(doc)
        db.session.commit()

    kn_res = client.post(
        "/api/chat",
        json={
            "message": "ಡಿಜಿಟಲ್ ವೈಯಕ್ತಿಕ ಡೇಟಾ ಸಂರಕ್ಷಣಾ ನಿಯಮಗಳು, 2025 ರ ಪ್ರಕಾರ ವ್ಯಕ್ತಿಯ ಹಕ್ಕುಗಳು ಯಾವುವು?",
            "language": "en",
        },
    )
    assert kn_res.status_code == 200
    data = kn_res.json
    assert data["verified"] is True
    assert data["language"] == "kn"
    assert data["sources"][0]["section"] == "14"
    assert data["sources"][0]["section_title"] == "Rights of Data Principals"
    assert data["sources"][0]["page_range"] == "29–30"
    assert "90 ದಿನ" in data["answer"]
    assert "Rule 14" in data["answer"]
    assert "Digital_Personal_Data_Protection_Rules_2025.pdf" in data["answer"]
    assert "15. Transfer of personal data" not in data["sources"][0]["excerpt"]

    hi_res = client.post(
        "/api/chat",
        json={
            "message": "What are the rights of a Data Principal under DPDP Rules 2025?",
            "language": "hi",
        },
    )
    assert hi_res.status_code == 200
    assert hi_res.json["language"] == "hi"
    assert "90 दिनों" in hi_res.json["answer"]
    assert hi_res.json["sources"][0]["section"] == "14"

    en_res = client.post(
        "/api/chat",
        json={
            "message": "What are the rights of a Data Principal under DPDP Rules 2025?",
            "language": "en",
        },
    )
    assert en_res.status_code == 200
    assert en_res.json["language"] == "en"
    assert "90 days" in en_res.json["answer"]
    assert en_res.json["sources"][0]["section"] == "14"


def test_admin_stats_and_admin_js_no_document_shadowing(app, client):
    from backend.extensions import db
    from backend.models import User

    res = client.post(
        "/api/auth/register",
        json={
            "username": "Admin Tester",
            "email": "admintester@example.com",
            "password": "strong-password-1",
        },
    )
    assert res.status_code == 201
    with app.app_context():
        user = User.query.filter_by(email="admintester@example.com").one()
        user.role = "admin"
        db.session.commit()

    stats = client.get("/api/admin/stats")
    assert stats.status_code == 200
    assert stats.json["extraction_enabled"] is True
    assert stats.json["monitoring_configured"] is True

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    html = admin_page.get_data(as_text=True)
    assert "admin.js?v=4" in html
    assert "Not enabled" not in html
    assert "Not configured" not in html

    admin_js = client.get("/static/js/admin.js").get_data(as_text=True)
    assert "documents.forEach((document)" not in admin_js
    assert "documents.forEach((docItem)" in admin_js


def test_dashboard_rag_activation_green_status_when_verified_sources_exist(app, client):
    _register_and_login(client)
    before = client.get("/dashboard")
    assert before.status_code == 200
    before_html = before.get_data(as_text=True)
    assert "workspace-status-ready" not in before_html
    assert 'data-rag-status="unavailable"' in before_html
    assert "Knowledge base not connected" in before_html

    _seed_verified_rule(app)
    after = client.get("/dashboard")
    assert after.status_code == 200
    after_html = after.get_data(as_text=True)
    assert "workspace-status-ready" in after_html
    assert 'data-rag-status="active"' in after_html
    assert "RAG Active" in after_html
    assert "search-hint-ready" in after_html

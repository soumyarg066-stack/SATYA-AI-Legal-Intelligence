import logging
import re
from typing import Any

from flask import current_app

from backend.services.citation_service import build_citations
from backend.services.context_service import classify_question
from backend.services.language_service import (
    expand_multilingual_query,
    get_language_messages,
    resolve_answer_language,
)
from backend.services.llm_provider import (
    MalformedProviderResponse,
    ProviderError,
    get_provider,
)
from backend.services.prompt_service import build_provider_messages
from backend.services.retrieval_service import _tokens, retrieve_evidence
from backend.services.verification_service import verify_claims
from backend.services.chat_service import NO_DOCUMENTS_ANSWER
from backend.services.knowledge_service import get_knowledge_status


logger = logging.getLogger(__name__)
_FOLLOWUP_REFERENCE_PATTERN = re.compile(
    r"\b(that|this|it|they|those|these|same|above|previous|former|latter|further|elaborate|clarify|more)\b",
    re.IGNORECASE,
)


def _is_followup_reference(question: str) -> bool:
    tokens = _tokens(question)
    if not tokens:
        return True
    return len(tokens) <= 3 and bool(_FOLLOWUP_REFERENCE_PATTERN.search(question))
INSUFFICIENT_EVIDENCE_ANSWER = (
    "I could not find sufficient supporting information in the available legal "
    "documents to answer this question reliably. Please consult the relevant "
    "official legal source or a qualified legal professional."
)
PROVIDER_UNCONFIGURED_ANSWER = (
    "Verified source material was found, but no AI answer provider is configured. "
    "Configure an AI provider before requesting a generated response."
)
GENERATION_FAILURE_ANSWER = (
    "I could not produce a safely verifiable answer from the available evidence. "
    "Please try again later or consult the relevant official legal source."
)
CONFLICTING_EVIDENCE_ANSWER = (
    "I found conflicting verified source passages and cannot determine which version "
    "applies reliably. Please check the relevant official legal source or consult a "
    "qualified legal professional."
)


_PROVISION_EXPLANATIONS = [
    (
        ("prominently publish on its website or app", "means using which a data principal may make a request"),
        {
            "en": "Publish request mechanism & identifier (Rule 14(1)(a)-(b)): Data Fiduciaries and Consent Managers must prominently publish on their website or app the means and required identifier for a Data Principal to make a request to exercise her rights.",
            "kn": "ವಿನಂತಿ ವಿಧಾನ ಮತ್ತು ಗುರುತಿನ ಪ್ರಕಟಣೆ (Rule 14(1)(a)-(b)): Data Fiduciary ಮತ್ತು ಅನ್ವಯವಾಗುವಲ್ಲಿ Consent Manager, Data Principal ತಮ್ಮ ಹಕ್ಕುಗಳನ್ನು ಚಲಾಯಿಸಲು ವಿನಂತಿ ಸಲ್ಲಿಸುವ ವಿಧಾನ ಹಾಗೂ ಗುರುತಿನ ವಿವರಗಳನ್ನು (identifier) ತಮ್ಮ ವೆಬ್‌ಸೈಟ್ ಅಥವಾ ಆ್ಯಪ್‌ನಲ್ಲಿ ಪ್ರಕಟಿಸಬೇಕು.",
            "hi": "अनुरोध माध्यम और पहचान का प्रकाशन (Rule 14(1)(a)-(b)): Data Fiduciary और जहाँ लागू हो Consent Manager को अपनी वेबसाइट या ऐप पर वे माध्यम और आवश्यक पहचान विवरण (identifier) प्रमुखता से प्रकाशित करने होंगे जिनसे Data Principal अपने अधिकारों का उपयोग करने का अनुरोध कर सकें।",
        },
    ),
    (
        ("to exercise the rights of the data principal under the act, she may make a request",),
        {
            "en": "Submitting a rights request (Rule 14(2)): To exercise rights under the Act, a Data Principal may make a request to the Data Fiduciary to whom she previously gave consent, using the required means and particulars.",
            "kn": "ಹಕ್ಕುಗಳ ಚಲಾವಣೆಗೆ ವಿನಂತಿ (Rule 14(2)): ಕಾಯ್ದೆಯಡಿ ಹಕ್ಕುಗಳನ್ನು ಚಲಾಯಿಸಲು Data Principal ತಾವು ಹಿಂದೆ ಸಮ್ಮತಿ ನೀಡಿದ Data Fiduciary ಗೆ ನಿಗದಿತ ವಿಧಾನ ಮತ್ತು ವಿವರಗಳೊಂದಿಗೆ ವಿನಂತಿ ಸಲ್ಲಿಸಬಹುದು.",
            "hi": "अधिकारों के उपयोग हेतु अनुरोध (Rule 14(2)): अधिनियम के अंतर्गत अधिकारों का उपयोग करने के लिए Data Principal उस Data Fiduciary को निर्धारित माध्यम व विवरण के साथ अनुरोध कर सकती हैं जिसे उन्होंने पहले सहमति दी थी।",
        },
    ),
    (
        ("not exceeding ninety days", "grievance"),
        {
            "en": "Grievance redressal timeline (Rule 14(3)): Every Data Fiduciary and Consent Manager must respond to Data Principal grievances within a reasonable period not exceeding 90 days.",
            "kn": "ದೂರು ಪರಿಹಾರದ ಕಾಲಮಿತಿ (Rule 14(3)): ಪ್ರತಿ Data Fiduciary ಮತ್ತು Consent Manager, Data Principal ಅವರ ದೂರುಗಳಿಗೆ 90 ದಿನಗಳನ್ನು ಮೀರದ ಸಮಂಜಸ ಅವಧಿಯೊಳಗೆ ಪ್ರತಿಕ್ರಿಯಿಸಬೇಕು.",
            "hi": "शिकायत निवारण समय-सीमा (Rule 14(3)): प्रत्येक Data Fiduciary और Consent Manager को Data Principal की शिकायतों का 90 दिनों से अधिक न होने वाली उचित अवधि में उत्तर देना होगा।",
        },
    ),
    (
        ("nominate one or more individuals",),
        {
            "en": "Nomination of individuals (Rule 14(4)): A Data Principal may nominate one or more individuals, in accordance with applicable terms of service and law, to exercise her rights.",
            "kn": "ವ್ಯಕ್ತಿಗಳ ನಾಮನಿರ್ದೇಶನ (Rule 14(4)): ಸೇವಾ ನಿಯಮಗಳು ಮತ್ತು ಅನ್ವಯವಾಗುವ ಕಾನೂನಿನ ಪ್ರಕಾರ Data Principal ತಮ್ಮ ಹಕ್ಕುಗಳನ್ನು ಚಲಾಯಿಸಲು ಒಬ್ಬರು ಅಥವಾ ಹೆಚ್ಚಿನ ವ್ಯಕ್ತಿಗಳನ್ನು ನಾಮನಿರ್ದೇಶನ (nominate) ಮಾಡಬಹುದು.",
            "hi": "व्यक्तियों का नामांकन (Rule 14(4)): Data Principal सेवा की शर्तों और लागू कानून के अनुसार अपने अधिकारों का उपयोग करने के लिए एक या अधिक व्यक्तियों को नामांकित (nominate) कर सकती हैं।",
        },
    ),
    (
        ("summary of personal data", "identities of all other data fiduciaries"),
        {
            "en": "Right to access information (Section 11): A Data Principal can request a summary of her personal data being processed, processing activities undertaken, and identities of all other Data Fiduciaries and Data Processors with whom the data was shared.",
            "kn": "ಮಾಹಿತಿ ಪಡೆಯುವ ಹಕ್ಕು (Section 11): Data Principal ತಾವು ಸಮ್ಮತಿ ನೀಡಿದ ವೈಯಕ್ತಿಕ ದತ್ತಾಂಶದ ಸಾರಾಂಶ, ಸಂಸ್ಕರಣಾ ಚಟುವಟಿಕೆಗಳು ಮತ್ತು ದತ್ತಾಂಶವನ್ನು ಹಂಚಿಕೊಂಡಿರುವ ಇತರ Data Fiduciary ಹಾಗೂ Data Processor ಗಳ ವಿವರಗಳನ್ನು ಪಡೆಯುವ ಹಕ್ಕು ಹೊಂದಿದ್ದಾರೆ.",
            "hi": "जानकारी प्राप्त करने का अधिकार (Section 11): Data Principal को प्रसंस्कृत किए जा रहे अपने व्यक्तिगत डेटा का सारांश, प्रसंस्करण गतिविधियों तथा उन अन्य Data Fiduciaries व Data Processors की पहचान प्राप्त करने का अधिकार है जिनके साथ डेटा साझा किया गया है।",
        },
    ),
    (
        ("right to correction, completion, updating and erasure",),
        {
            "en": "Right to correction and erasure (Section 12): A Data Principal has the right to request correction of inaccurate data, completion of incomplete data, updating of personal data, and erasure unless retention is legally necessary.",
            "kn": "ತಿದ್ದುಪಡಿ ಮತ್ತು ಅಳಿಸುವಿಕೆಯ ಹಕ್ಕು (Section 12): Data Principal ತಪ್ಪಾದ ವೈಯಕ್ತಿಕ ದತ್ತಾಂಶವನ್ನು ಸರಿಪಡಿಸಲು, ಅಪೂರ್ಣ ದತ್ತಾಂಶವನ್ನು ಪೂರ್ಣಗೊಳಿಸಲು, ನವೀಕರಿಸಲು ಮತ್ತು ಕಾನೂನುಬದ್ಧವಾಗಿ ಅಗತ್ಯವಿಲ್ಲದಿದ್ದಲ್ಲಿ ಅಳಿಸಲು ವಿನಂತಿಸುವ ಹಕ್ಕು ಹೊಂದಿದ್ದಾರೆ.",
            "hi": "सुधार और विलोपन का अधिकार (Section 12): Data Principal को गलत व्यक्तिगत डेटा को सुधारने, अधूरे डेटा को पूरा करने, अद्यतन करने तथा कानूनी रूप से आवश्यक न होने पर उसे हटाने (erasure) का अनुरोध करने का अधिकार है।",
        },
    ),
    (
        ("right of grievance redressal", "exhaust the opportunity"),
        {
            "en": "Right of grievance redressal (Section 13): A Data Principal has the right to readily available grievance redressal from a Data Fiduciary or Consent Manager and must exhaust this remedy before approaching the Board.",
            "kn": "ದೂರು ಪರಿಹಾರದ ಹಕ್ಕು (Section 13): Data Fiduciary ಅಥವಾ Consent Manager ನ ಲೋಪಗಳ ಕುರಿತು ಸುಲಭವಾಗಿ ಲಭ್ಯವಿರುವ ದೂರು ಪರಿಹಾರ ವ್ಯವಸ್ಥೆಯನ್ನು ಪಡೆಯುವ ಹಕ್ಕು ಇದೆ; ಮಂಡಳಿಯನ್ನು ಸಂಪರ್ಕಿಸುವ ಮೊದಲು ಈ ಪ್ರಕ್ರಿಯೆಯನ್ನು ಬಳಸಬೇಕು.",
            "hi": "शिकायत निवारण का अधिकार (Section 13): Data Fiduciary या Consent Manager के कार्य या चूक के संबंध में सुलभ शिकायत निवारण का अधिकार है, और बोर्ड के समक्ष जाने से पहले इस उपाय का उपयोग करना आवश्यक है।",
        },
    ),
    (
        ("right to nominate", "death or incapacity"),
        {
            "en": "Right to nominate on death or incapacity (Section 14): A Data Principal may nominate any other individual to exercise her rights under the Act and rules in the event of death or incapacity.",
            "kn": "ಮರಣ ಅಥವಾ ಅಸಮರ್ಥತೆಯ ಸಂದರ್ಭದಲ್ಲಿ ನಾಮನಿರ್ದೇಶನ ಹಕ್ಕು (Section 14): ಮರಣ ಅಥವಾ ಅಸಮರ್ಥತೆಯ ಸಂದರ್ಭದಲ್ಲಿ ಕಾಯ್ದೆ ಮತ್ತು ನಿಯಮಗಳಡಿ ತಮ್ಮ ಹಕ್ಕುಗಳನ್ನು ಚಲಾಯಿಸಲು ಇನ್ನೊಬ್ಬ ವ್ಯಕ್ತಿಯನ್ನು ನಾಮನಿರ್ದೇಶನ ಮಾಡುವ ಹಕ್ಕು ಇದೆ.",
            "hi": "मृत्यु या अक्षमता पर नामांकन का अधिकार (Section 14): मृत्यु या अक्षमता की स्थिति में अधिनियम और नियमों के अंतर्गत अपने अधिकारों का उपयोग करने के लिए किसी अन्य व्यक्ति को नामांकित करने का अधिकार है।",
        },
    ),
    (
        ("pyramid scheme", "direct selling"),
        {
            "en": "Prohibition of Pyramid & Money Circulation Schemes (Rule 10): No direct selling entity or direct seller shall promote a Pyramid Scheme or participate in a money circulation scheme.",
            "kn": "ಪಿರಮಿಡ್ ಮತ್ತು ಹಣ ಚಲಾವಣೆ ಯೋಜನೆಗಳ ನಿಷೇಧ (Rule 10): ಯಾವುದೇ ನೇರ ಮಾರಾಟ ಸಂಸ್ಥೆ ಅಥವಾ ನೇರ ಮಾರಾಟಗಾರರು ಪಿರಮಿಡ್ ಯೋಜನೆಯನ್ನು (Pyramid Scheme) ಪ್ರಚಾರ ಮಾಡಬಾರದು ಅಥವಾ ಹಣ ಚಲಾವಣೆ ಯೋಜನೆಯಲ್ಲಿ ಭಾಗವಹಿಸಬಾರದು.",
            "hi": "पिरामिड एवं धन परिचालन योजनाओं का प्रतिषेध (Rule 10): कोई भी प्रत्यक्ष बिक्री इकाई या प्रत्यक्ष विक्रेता पिरामिड स्कीम को बढ़ावा नहीं देगी और न ही धन परिचालन स्कीम में भाग लेगी।",
        },
    ),
    (
        ("grievance redressal officer", "forty-eight"),
        {
            "en": "Consumer grievance acknowledgment (Rule 5): Every direct selling entity must appoint a grievance redressal officer who acknowledges consumer complaints within 48 working hours.",
            "kn": "ದೂರು ಸ್ವೀಕೃತಿ ಅವಧಿ (Rule 5): ಪ್ರತಿ ನೇರ ಮಾರಾಟ ಸಂಸ್ಥೆಯು ದೂರು ನಿವಾರಣಾ ಅಧಿಕಾರಿಯನ್ನು ನೇಮಿಸಬೇಕು ಮತ್ತು ಗ್ರಾಹಕರ ದೂರನ್ನು 48 ಕೆಲಸದ ಗಂಟೆಗಳಲ್ಲಿ ಸ್ವೀಕರಿಸಿ ದೃಢೀಕರಿಸಬೇಕು.",
            "hi": "शिकायत पावती अवधि (Rule 5): प्रत्येक प्रत्यक्ष बिक्री इकाई को एक शिकायत निवारण अधिकारी नियुक्त करना होगा जो 48 कार्य घंटों के भीतर उपभोक्ता शिकायत की पावती दे।",
        },
    ),
    (
        ("notice given by data fiduciary", "data principal"),
        {
            "en": "Notice by Data Fiduciary (Rule 3): The notice given by a Data Fiduciary to a Data Principal must be presented clearly and independently, stating itemized personal data and processing purposes.",
            "kn": "ಡೇಟಾ ಫಿಡ್ಯೂಶಿಯರಿ ನೀಡುವ ಸೂಚನೆ (Rule 3): Data Fiduciary ನೀಡುವ ಸೂಚನೆಯು ಸ್ಪಷ್ಟ ಮತ್ತು ಸ್ವತಂತ್ರವಾಗಿದ್ದು, ಸಂಗ್ರಹಿಸುವ ವೈಯಕ್ತಿಕ ದತ್ತಾಂಶ ಹಾಗೂ ಅದರ ಉದ್ದೇಶವನ್ನು ಪ್ರತ್ಯೇಕವಾಗಿ ವಿವರಿಸಬೇಕು.",
            "hi": "Data Fiduciary द्वारा नोटिस (Rule 3): Data Fiduciary द्वारा Data Principal को दिया जाने वाला नोटिस स्पष्ट और स्वतंत्र होना चाहिए तथा व्यक्तिगत डेटा और उसके उद्देश्य का विवरण देना चाहिए।",
        },
    ),
]


def _concise_excerpt(excerpt: str, max_chars: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", excerpt or "").strip()
    if len(cleaned) <= max_chars:
        return cleaned
    # Prefer extracting sentences containing key substantive legal terms
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.;])\s+(?=\([0-9a-zA-Z]+\)|[A-Z\u0900-\u097F])", cleaned)
        if len(s.strip()) >= 20
    ]
    if sentences:
        picked = sentences[0]
        if len(picked) > max_chars:
            picked = picked[:max_chars].rsplit(" ", 1)[0].strip() + "..."
        return picked
    return cleaned[:max_chars].rsplit(" ", 1)[0].strip() + "..."


def _extract_grounded_points(citation: dict[str, Any], lang: str) -> list[str]:
    excerpt = citation.get("excerpt") or ""
    normalized = " ".join(excerpt.lower().split())
    points: list[str] = []
    for needles, localized in _PROVISION_EXPLANATIONS:
        if all(needle in normalized for needle in needles):
            points.append(f"- {localized[lang]} [{citation['number']}]")
    if points:
        return points[:4]

    cleaned = re.sub(r"\s+", " ", excerpt).strip()
    if lang in {"kn", "hi"}:
        sec_ref = citation.get("section") or ""
        title_ref = citation.get("section_title") or ""
        ref_text = f"Rule/Section {sec_ref}" + (f" ({title_ref})" if title_ref else "") if sec_ref else "ಸಂಬಂಧಿತ ನಿಯಮ" if lang == "kn" else "संबंधित प्रावधान"
        if lang == "kn":
            points.append(
                f"- ಪರಿಶೀಲಿಸಿದ ಮೂಲ ದಾಖಲೆಯ **{ref_text}** ಈ ಪ್ರಶ್ನೆಗೆ ಸಂಬಂಧಿಸಿದ ನಿಯಮವನ್ನು ಒಳಗೊಂಡಿದೆ; ಪೂರ್ಣ ಮೂಲ ಪಠ್ಯವನ್ನು ಪುರಾವೆ ಫಲಕದಲ್ಲಿ (Evidence Panel) ಪರಿಶೀಲಿಸಬಹುದು. [{citation['number']}]"
            )
        else:
            points.append(
                f"- सत्यापित स्रोत दस्तावेज़ की **{ref_text}** में इस विषय से संबंधित प्रावधान दिया गया है; पूर्ण मूल पाठ दाएँ साक्ष्य पैनल (Evidence Panel) में उपलब्ध है। [{citation['number']}]"
            )
        return points

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.;])\s+(?=\([0-9a-zA-Z]+\)|[A-Z\u0900-\u097F])", cleaned)
        if len(part.strip()) >= 25
    ]
    for sentence in sentences[:2]:
        points.append(f"- {sentence[:240]}{'...' if len(sentence) > 240 else ''} [{citation['number']}]")
    return points


def _build_structured_evidence_answer(
    citations: list[dict[str, Any]],
    lang: str,
    msgs: dict[str, str],
) -> str:
    headings = {
        "en": {
            "header": "### Verified Legal Answer",
            "intro": "Based on verified legal sources from the SATYA knowledge base:",
            "source_file": "Source",
            "rule_sec": "Rule / Section",
            "page": "Page",
            "passage": "Key excerpt",
            "panel_hint": "Full text in Evidence Panel.",
            "not_specified": "Not specified",
        },
        "kn": {
            "header": "### ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ಉತ್ತರ",
            "intro": "SATYA ಜ್ಞಾನಕೋಶದ ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ಮೂಲಗಳ ಆಧಾರದ ಮೇಲೆ:",
            "source_file": "ಮೂಲ",
            "rule_sec": "ನಿಯಮ / ವಿಭಾಗ",
            "page": "ಪುಟ",
            "passage": "ಮೂಲ ಉಲ್ಲೇಖ",
            "panel_hint": "ಪೂರ್ಣ ಪಠ್ಯ ಪುರಾವೆ ಫಲಕದಲ್ಲಿದೆ.",
            "not_specified": "ನಿರ್ದಿಷ್ಟಪಡಿಸಲಾಗಿಲ್ಲ",
        },
        "hi": {
            "header": "### सत्यापित कानूनी उत्तर",
            "intro": "SATYA ज्ञानकोष के सत्यापित कानूनी स्रोतों के आधार पर:",
            "source_file": "स्रोत",
            "rule_sec": "नियम / धारा",
            "page": "पृष्ठ",
            "passage": "मूल उद्धरण",
            "panel_hint": "पूर्ण पाठ साक्ष्य पैनल में उपलब्ध है।",
            "not_specified": "निर्दिष्ट नहीं",
        },
    }[lang]

    blocks = [f"{headings['header']}\n{headings['intro']}"]
    for citation in citations:
        act_title = citation.get("act_name") or citation.get("document_title") or citation.get("title")
        doc_name = citation.get("filename") or citation.get("document_name") or act_title
        sec_parts = []
        if citation.get("section"):
            sec_parts.append(str(citation["section"]))
            if citation.get("subsection"):
                sub = str(citation["subsection"])
                sec_parts.append(sub if sub.startswith("(") else f"({sub})")
            if citation.get("section_title"):
                sec_parts.append(f"— {citation['section_title']}")
        sec_display = " ".join(sec_parts) if sec_parts else headings["not_specified"]
        page_display = citation.get("page_range") or (
            str(citation["page"]) if citation.get("page") is not None else headings["not_specified"]
        )

        lines = [
            f"**{citation['number']}. {act_title}**",
            f"- **{headings['rule_sec']}:** {sec_display} | **{headings['source_file']}:** `{doc_name}` | **{headings['page']}:** {page_display}",
        ]
        matched_points = _extract_grounded_points(citation, lang)
        lines.extend(matched_points)
        excerpt = citation.get("excerpt") or ""
        # Keep concise direct quote when text is short or English; avoid dumping multi-KB walls in chat
        if len(excerpt) <= 280 or lang == "en":
            short_quote = _concise_excerpt(excerpt, max_chars=280)
            lines.append(f"- **{headings['passage']}:** {short_quote} [{citation['number']}]")
        else:
            lines.append(f"- **{headings['passage']}:** {headings['panel_hint']} [{citation['number']}]")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _validate_claims(claims: Any) -> list[dict[str, Any]]:
    if not isinstance(claims, list):
        raise MalformedProviderResponse("Provider claims must be a list.")
    validated = []
    for claim in claims:
        if not isinstance(claim, dict):
            raise MalformedProviderResponse("Each provider claim must be an object.")
        text = claim.get("text")
        evidence_ids = claim.get("evidence_ids")
        source_claim = claim.get("source_claim")
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > 2000
            or not isinstance(evidence_ids, list)
            or not evidence_ids
            or any(not isinstance(item, str) for item in evidence_ids)
        ):
            raise MalformedProviderResponse("A provider claim is missing text or evidence IDs.")
        if source_claim is not None and (not isinstance(source_claim, str) or len(source_claim) > 2000):
            raise MalformedProviderResponse("A provider claim has an invalid source_claim.")
        item = {"text": text.strip(), "evidence_ids": evidence_ids}
        if source_claim and source_claim.strip():
            item["source_claim"] = source_claim.strip()
        validated.append(item)
    return validated


def answer_question(
    question: str,
    history: list[dict[str, str]] | None = None,
    provider: Any = None,
    language: str = "en",
) -> dict[str, Any]:
    lang = resolve_answer_language(question, language)
    msgs = get_language_messages(lang)
    context = classify_question(question)
    prior_questions = [
        item.get("message", "")[:1000]
        for item in (history or [])[-8:]
        if item.get("sender") == "user"
    ]
    evidence = retrieve_evidence(question)
    translated_query = expand_multilingual_query(question)
    if translated_query:
        translated_evidence = retrieve_evidence(translated_query)
        if not evidence:
            evidence = translated_evidence
        elif translated_evidence:
            by_id = {item["id"]: item for item in evidence}
            for item in translated_evidence:
                existing = by_id.get(item["id"])
                if existing is None or item.get("relevance_score", 0) > existing.get("relevance_score", 0):
                    by_id[item["id"]] = item
            evidence = sorted(
                by_id.values(),
                key=lambda item: (-item.get("relevance_score", 0), item["id"]),
            )[:5]
    if not evidence and prior_questions and _is_followup_reference(question):
        retrieval_query = " ".join([*prior_questions, question])
        evidence = retrieve_evidence(retrieval_query)
        if not evidence:
            translated_followup = expand_multilingual_query(retrieval_query)
            if translated_followup:
                evidence = retrieve_evidence(translated_followup)
    if not evidence:
        has_verified_sources = get_knowledge_status()["available"]
        return {
            "answer": (
                msgs["insufficient_evidence"]
                if has_verified_sources
                else msgs["no_documents"]
            ),
            "citations": [],
            "sources": [],
            "verified": False,
            "evidence_status": "insufficient_evidence",
            "language": lang,
            "limitations": [
                msgs["limit_no_relevant_records"]
                if has_verified_sources
                else msgs["limit_no_verified_records"]
            ],
        }
    if any(record.get("conflict_detected") for record in evidence):
        return {
            "answer": msgs["conflicting_evidence"],
            "citations": [],
            "sources": build_citations(evidence),
            "verified": False,
            "evidence_status": "conflicting_sources",
            "language": lang,
            "limitations": [msgs["limit_conflicting_sources"]],
        }

    try:
        selected_provider = provider if provider is not None else get_provider(current_app.config)
    except ProviderError as error:
        logger.warning("AI provider configuration is invalid: %s", error)
        selected_provider = None
        provider_error = True
    else:
        provider_error = False

    if selected_provider is None:
        if provider_error:
            return {
                "answer": msgs["generation_failure"],
                "citations": [],
                "sources": build_citations(evidence),
                "verified": False,
                "evidence_status": "provider_error",
                "language": lang,
                "limitations": [msgs["limit_invalid_provider"]],
            }
        citations = build_citations(evidence[:2])
        sources = build_citations(evidence[:3])
        return {
            "answer": _build_structured_evidence_answer(citations, lang, msgs),
            "citations": citations,
            "sources": sources,
            "verified": True,
            "evidence_status": "supported",
            "language": lang,
            "limitations": [msgs["limit_verbatim_only"]],
        }

    messages = build_provider_messages(question, evidence, history, context, language=lang)
    try:
        claims = _validate_claims(selected_provider.generate(messages))
    except (ProviderError, MalformedProviderResponse) as error:
        logger.warning("AI answer generation failed: %s", error)
        return {
            "answer": msgs["generation_failure"],
            "citations": [],
            "sources": build_citations(evidence),
            "verified": False,
            "evidence_status": "generation_error",
            "language": lang,
            "limitations": [msgs["limit_provider_validation"]],
        }
    except Exception:
        logger.exception("Unexpected AI answer generation failure.")
        return {
            "answer": msgs["generation_failure"],
            "citations": [],
            "sources": build_citations(evidence),
            "verified": False,
            "evidence_status": "generation_error",
            "language": lang,
            "limitations": [msgs["limit_provider_validation"]],
        }

    verification = verify_claims(
        claims,
        evidence,
        asks_current_legal_status=context["asks_current_legal_status"],
        language=lang,
    )
    if not verification["all_supported"]:
        status = (
            "currentness_unverified"
            if verification["currentness_unverified"]
            else "unsupported_claims"
            if claims
            else "insufficient_evidence"
        )
        return {
            "answer": msgs["insufficient_evidence"],
            "citations": [],
            "sources": build_citations(evidence),
            "verified": False,
            "evidence_status": status,
            "language": lang,
            "limitations": verification["unsupported_claims"]
            or [msgs["limit_no_supported_claims"]],
        }

    citations = build_citations(evidence)
    citations_by_id = {item["id"]: item for item in citations}
    answer_lines = []
    used_ids = set()
    for claim in verification["supported_claims"]:
        numbers = []
        for evidence_id in claim["evidence_ids"]:
            citation = citations_by_id.get(evidence_id)
            if citation and evidence_id not in used_ids:
                used_ids.add(evidence_id)
                numbers.append(citation["number"])
            elif citation:
                numbers.append(citation["number"])
        answer_lines.append(f'{claim["text"]} ' + " ".join(f"[{number}]" for number in numbers))
    citations = [item for item in citations if item["id"] in used_ids]

    limitations = []
    if context["appears_personalized"]:
        limitations.append(msgs["limit_personalized_advice"])
    if context["asks_current_legal_status"]:
        limitations.append(msgs["limit_currentness"])
    if not context["state_or_local_scope_specified"]:
        limitations.append(msgs["limit_jurisdiction"])
    return {
        "answer": "\n\n".join(answer_lines),
        "citations": citations,
        "sources": citations,
        "verified": True,
        "evidence_status": "supported",
        "language": lang,
        "limitations": limitations,
    }

import re
from typing import Any

from backend.services.chat_service import NO_DOCUMENTS_ANSWER

DEFAULT_LANGUAGE = "en"

SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "prompt_label": "English",
    },
    "kn": {
        "code": "kn",
        "name": "Kannada",
        "native_name": "ಕನ್ನಡ",
        "prompt_label": "Kannada (ಕನ್ನಡ)",
    },
    "hi": {
        "code": "hi",
        "name": "Hindi",
        "native_name": "हिन्दी",
        "prompt_label": "Hindi (हिन्दी)",
    },
}

_LANGUAGE_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "kn": "kn",
    "kan": "kn",
    "kannada": "kn",
    "ಕನ್ನಡ": "kn",
    "hi": "hi",
    "hin": "hi",
    "hindi": "hi",
    "हिन्दी": "hi",
    "हिंदी": "hi",
}

LANGUAGE_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "no_documents": NO_DOCUMENTS_ANSWER,
        "insufficient_evidence": (
            "I could not find sufficient supporting information in the available legal "
            "documents to answer this question reliably. Please consult the relevant "
            "official legal source or a qualified legal professional."
        ),
        "conflicting_evidence": (
            "I found conflicting verified source passages and cannot determine which version "
            "applies reliably. Please check the relevant official legal source or consult a "
            "qualified legal professional."
        ),
        "generation_failure": (
            "I could not produce a safely verifiable answer from the available evidence. "
            "Please try again later or consult the relevant official legal source."
        ),
        "verbatim_intro": "",
        "verbatim_note": "",
        "limit_no_relevant_records": "No sufficiently relevant verified source records were found.",
        "limit_no_verified_records": "No verified source records are available in the knowledge base.",
        "limit_conflicting_sources": "Conflicting source passages were found; no version was selected.",
        "limit_invalid_provider": "The configured answer provider is invalid.",
        "limit_provider_validation": "The provider response could not be safely validated.",
        "limit_no_supported_claims": "The provider returned no evidence-supported claims.",
        "limit_verbatim_only": (
            "The answer quotes retrieved source passages verbatim; no AI provider is configured to summarize them."
        ),
        "limit_personalized_advice": "This is general legal information, not personalized legal advice.",
        "limit_currentness": (
            "Current legal status was not independently established beyond the supplied verified metadata."
        ),
        "limit_jurisdiction": "No state or local jurisdiction was specified in the question.",
        "page_label": "page",
        "rule_section_label": "Rule/section",
        "subsection_label": "subsection",
        "subrule_subsection_label": "sub-rule/subsection",
        "error_json_required": "A JSON object is required.",
        "error_empty_message": "Enter a message before sending.",
        "error_unsupported_language": "Unsupported language. Choose English (en), Kannada (kn), or Hindi (hi).",
        "error_invalid_conversation_id": "Invalid conversation ID.",
        "error_conversation_not_found": "Conversation not found.",
        "error_create_conversation_db": "Unable to create conversation due to a database error.",
        "error_delete_conversation_db": "Unable to delete conversation due to a database error.",
        "error_save_messages_db": "Unable to save conversation messages due to a database error.",
        "message_conversation_cleared": "Conversation cleared.",
        "error_auth_required": "Authentication required.",
        "error_csrf_invalid": "The form security token is missing or invalid.",
        "error_request_too_large": "The uploaded file exceeds the maximum allowed size.",
        "error_not_found": "The requested resource was not found.",
        "error_db_unavailable": "Database service is temporarily unavailable. Please try again shortly.",
        "error_db_generic": "A database error occurred while processing your request.",
        "error_server_unexpected": "An unexpected server error occurred.",
    },
    "kn": {
        "no_documents": (
            "ಜ್ಞಾನಕೋಶದಲ್ಲಿ ಇನ್ನೂ ಯಾವುದೇ ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ಮೂಲ ದಾಖಲೆಗಳು ಲಭ್ಯವಿಲ್ಲ. "
            "SATYA ಉತ್ತರಿಸುವ ಮೊದಲು ನಿರ್ವಾಹಕರು ಅಪ್‌ಲೋಡ್ ಮಾಡಿದ ಮೂಲಗಳನ್ನು ಪರಿಶೀಲಿಸಿ ದೃಢೀಕರಿಸಬೇಕು."
        ),
        "insufficient_evidence": (
            "ಈ ಪ್ರಶ್ನೆಗೆ ವಿಶ್ವಾಸಾರ್ಹವಾಗಿ ಉತ್ತರಿಸಲು ಲಭ್ಯವಿರುವ ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳಲ್ಲಿ "
            "ಸಾಕಷ್ಟು ಪೂರಕ ಮಾಹಿತಿ ಕಂಡುಬಂದಿಲ್ಲ. ದಯವಿಟ್ಟು ಸಂಬಂಧಿತ ಅಧಿಕೃತ ಕಾನೂನು ಮೂಲವನ್ನು ನೋಡಿ "
            "ಅಥವಾ ಅರ್ಹ ಕಾನೂನು ವೃತ್ತಿಪರರನ್ನು ಸಂಪರ್ಕಿಸಿ."
        ),
        "conflicting_evidence": (
            "ಪರಸ್ಪರ ವಿರುದ್ಧವಾದ ಪರಿಶೀಲಿಸಿದ ಮೂಲ ಭಾಗಗಳು ಕಂಡುಬಂದಿವೆ ಮತ್ತು ಯಾವ ಆವೃತ್ತಿಯು "
            "ಅನ್ವಯಿಸುತ್ತದೆ ಎಂಬುದನ್ನು ವಿಶ್ವಾಸಾರ್ಹವಾಗಿ ನಿರ್ಧರಿಸಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ಸಂಬಂಧಿತ "
            "ಅಧಿಕೃತ ಕಾನೂನು ಮೂಲವನ್ನು ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಅರ್ಹ ಕಾನೂನು ವೃತ್ತಿಪರರನ್ನು ಸಂಪರ್ಕಿಸಿ."
        ),
        "generation_failure": (
            "ಲಭ್ಯವಿರುವ ಪುರಾವೆಗಳಿಂದ ಸುರಕ್ಷಿತವಾಗಿ ಪರಿಶೀಲಿಸಬಹುದಾದ ಉತ್ತರವನ್ನು ರಚಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. "
            "ದಯವಿಟ್ಟು ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ ಅಥವಾ ಸಂಬಂಧಿತ ಅಧಿಕೃತ ಕಾನೂನು ಮೂಲವನ್ನು ನೋಡಿ."
        ),
        "verbatim_intro": (
            "ಪರಿಶೀಲಿಸಿದ ಕಾನೂನು ದಾಖಲೆಗಳಿಂದ ಕೆಳಗಿನ ಸಂಬಂಧಿತ ಮೂಲ ಭಾಗಗಳು ಕಂಡುಬಂದಿವೆ. "
            "ಅಧಿಕೃತ ಕಾನೂನು ಉಲ್ಲೇಖಗಳು ಮತ್ತು ಮೂಲ ಪಠ್ಯವನ್ನು ಯಥಾವತ್ತಾಗಿ ಉಳಿಸಲಾಗಿದೆ:"
        ),
        "verbatim_note": (
            "ಗಮನಿಸಿ: ಪ್ರಸ್ತುತ AI ಸಾರಾಂಶ/ಅನುವಾದ ಪೂರೈಕೆದಾರರು ಸಕ್ರಿಯವಾಗಿಲ್ಲದ ಕಾರಣ, ಪರಿಶೀಲಿಸಿದ ಮೂಲ ಕಾನೂನು "
            "ಉಲ್ಲೇಖಗಳನ್ನು ಬದಲಾಯಿಸದೆ ಯಥಾವತ್ತಾಗಿ ತೋರಿಸಲಾಗಿದೆ."
        ),
        "limit_no_relevant_records": "ಸಾಕಷ್ಟು ಸಂಬಂಧಿತ ಪರಿಶೀಲಿಸಿದ ಮೂಲ ದಾಖಲೆಗಳು ಕಂಡುಬಂದಿಲ್ಲ.",
        "limit_no_verified_records": "ಜ್ಞಾನಕೋಶದಲ್ಲಿ ಯಾವುದೇ ಪರಿಶೀಲಿಸಿದ ಮೂಲ ದಾಖಲೆಗಳು ಲಭ್ಯವಿಲ್ಲ.",
        "limit_conflicting_sources": "ಪರಸ್ಪರ ವಿರುದ್ಧವಾದ ಮೂಲ ಭಾಗಗಳು ಕಂಡುಬಂದಿವೆ; ಯಾವುದೇ ಆವೃತ್ತಿಯನ್ನು ಆಯ್ಕೆ ಮಾಡಲಾಗಿಲ್ಲ.",
        "limit_invalid_provider": "ಸಂರಚಿಸಲಾದ ಉತ್ತರ ಪೂರೈಕೆದಾರರು ಅಮಾನ್ಯವಾಗಿದೆ.",
        "limit_provider_validation": "ಪೂರೈಕೆದಾರರ ಪ್ರತಿಕ್ರಿಯೆಯನ್ನು ಸುರಕ್ಷಿತವಾಗಿ ದೃಢೀಕರಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
        "limit_no_supported_claims": "ಪೂರೈಕೆದಾರರು ಪುರಾವೆ-ಬೆಂಬಲಿತ ಹೇಳಿಕೆಗಳನ್ನು ಹಿಂತಿರುಗಿಸಲಿಲ್ಲ.",
        "limit_verbatim_only": (
            "ಉತ್ತರವು ಮರುಪಡೆಯಲಾದ ಮೂಲ ಭಾಗಗಳನ್ನು ಯಥಾವತ್ತಾಗಿ ಉಲ್ಲೇಖಿಸುತ್ತದೆ; ಅವುಗಳನ್ನು ಸಾರಾಂಶಗೊಳಿಸಲು ಯಾವುದೇ AI ಪೂರೈಕೆದಾರರನ್ನು ಸಂರಚಿಸಲಾಗಿಲ್ಲ."
        ),
        "limit_personalized_advice": "ಇದು ಸಾಮಾನ್ಯ ಕಾನೂನು ಮಾಹಿತಿಯಾಗಿದ್ದು, ವೈಯಕ್ತಿಕ ಕಾನೂನು ಸಲಹೆಯಲ್ಲ.",
        "limit_currentness": (
            "ಒದಗಿಸಲಾದ ಪರಿಶೀಲಿಸಿದ ಮೆಟಾಡೇಟಾದ ಹೊರತಾಗಿ ಪ್ರಸ್ತುತ ಕಾನೂನು ಸ್ಥಿತಿಯನ್ನು ಸ್ವತಂತ್ರವಾಗಿ ದೃಢೀಕರಿಸಲಾಗಿಲ್ಲ."
        ),
        "limit_jurisdiction": "ಪ್ರಶ್ನೆಯಲ್ಲಿ ಯಾವುದೇ ರಾಜ್ಯ ಅಥವಾ ಸ್ಥಳೀಯ ನ್ಯಾಯವ್ಯಾಪ್ತಿಯನ್ನು ನಿರ್ದಿಷ್ಟಪಡಿಸಲಾಗಿಲ್ಲ.",
        "page_label": "ಪುಟ",
        "rule_section_label": "Rule/Section",
        "subsection_label": "ಉಪ-ವಿಭಾಗ",
        "subrule_subsection_label": "ಉಪ-ನಿಯಮ/ಉಪ-ವಿಭಾಗ",
        "error_json_required": "JSON ವಸ್ತು ಅಗತ್ಯವಿದೆ.",
        "error_empty_message": "ಕಳುಹಿಸುವ ಮೊದಲು ದಯವಿಟ್ಟು ಪ್ರಶ್ನೆ ಅಥವಾ ಸಂದೇಶವನ್ನು ನಮೂದಿಸಿ.",
        "error_unsupported_language": "ಬೆಂಬಲಿತವಲ್ಲದ ಭಾಷೆ. English (en), ಕನ್ನಡ (kn), ಅಥವಾ हिन्दी (hi) ಆಯ್ಕೆಮಾಡಿ.",
        "error_invalid_conversation_id": "ಅಮಾನ್ಯ ಸಂಭಾಷಣೆ ID.",
        "error_conversation_not_found": "ಸಂಭಾಷಣೆ ಕಂಡುಬಂದಿಲ್ಲ.",
        "error_create_conversation_db": "ಡೇಟಾಬೇಸ್ ದೋಷದಿಂದಾಗಿ ಹೊಸ ಸಂಭಾಷಣೆಯನ್ನು ರಚಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
        "error_delete_conversation_db": "ಡೇಟಾಬೇಸ್ ದೋಷದಿಂದಾಗಿ ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
        "error_save_messages_db": "ಡೇಟಾಬೇಸ್ ದೋಷದಿಂದಾಗಿ ಸಂಭಾಷಣೆ ಸಂದೇಶಗಳನ್ನು ಉಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
        "message_conversation_cleared": "ಸಂಭಾಷಣೆಯನ್ನು ತೆರವುಗೊಳಿಸಲಾಗಿದೆ.",
        "error_auth_required": "ಮುಂದುವರಿಯಲು ದಯವಿಟ್ಟು ಲಾಗಿನ್ ಆಗಿ (ದೃಢೀಕರಣ ಅಗತ್ಯವಿದೆ).",
        "error_csrf_invalid": "ಫಾರ್ಮ್ ಭದ್ರತಾ ಟೋಕನ್ ಕಾಣೆಯಾಗಿದೆ ಅಥವಾ ಅಮಾನ್ಯವಾಗಿದೆ.",
        "error_request_too_large": "ಅಪ್‌ಲೋಡ್ ಮಾಡಿದ ಫೈಲ್ ಅನುಮತಿಸಲಾದ ಗರಿಷ್ಠ ಗಾತ್ರವನ್ನು ಮೀರಿದೆ.",
        "error_not_found": "ವಿನಂತಿಸಿದ ಸಂಪನ್ಮೂಲ ಕಂಡುಬಂದಿಲ್ಲ.",
        "error_db_unavailable": "ಡೇಟಾಬೇಸ್ ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "error_db_generic": "ನಿಮ್ಮ ವಿನಂತಿಯನ್ನು ಪ್ರಕ್ರಿಯೆಗೊಳಿಸುವಾಗ ಡೇಟಾಬೇಸ್ ದೋಷ ಸಂಭವಿಸಿದೆ.",
        "error_server_unexpected": "ಅನಿರೀಕ್ಷಿತ ಸರ್ವರ್ ದೋಷ ಸಂಭವಿಸಿದೆ.",
    },
    "hi": {
        "no_documents": (
            "ज्ञानकोष में अभी कोई सत्यापित कानूनी स्रोत दस्तावेज़ उपलब्ध नहीं हैं। "
            "SATYA द्वारा उत्तर देने से पहले प्रशासक को अपलोड किए गए स्रोतों की समीक्षा और सत्यापन करना होगा।"
        ),
        "insufficient_evidence": (
            "इस प्रश्न का विश्वसनीय उत्तर देने के लिए उपलब्ध सत्यापित कानूनी दस्तावेज़ों में "
            "पर्याप्त सहायक जानकारी नहीं मिली। कृपया संबंधित आधिकारिक कानूनी स्रोत देखें "
            "या किसी योग्य कानूनी विशेषज्ञ से परामर्श लें।"
        ),
        "conflicting_evidence": (
            "परस्पर विरोधी सत्यापित स्रोत अंश मिले हैं और यह विश्वसनीय रूप से तय करना संभव नहीं है कि "
            "कौन-सा संस्करण लागू होता है। कृपया संबंधित आधिकारिक कानूनी स्रोत की जांच करें "
            "या किसी योग्य कानूनी विशेषज्ञ से परामर्श लें।"
        ),
        "generation_failure": (
            "उपलब्ध साक्ष्यों से सुरक्षित रूप से सत्यापित किया जा सकने वाला उत्तर तैयार नहीं किया जा सका। "
            "कृपया बाद में पुनः प्रयास करें या संबंधित आधिकारिक कानूनी स्रोत देखें।"
        ),
        "verbatim_intro": (
            "सत्यापित कानूनी दस्तावेज़ों से निम्नलिखित संबंधित स्रोत अंश प्राप्त हुए हैं। "
            "आधिकारिक कानूनी संदर्भ और मूल पाठ को यथावत रखा गया है:"
        ),
        "verbatim_note": (
            "नोट: वर्तमान में कोई AI सारांश/अनुवाद प्रदाता कॉन्फ़िगर नहीं है, इसलिए सत्यापित कानूनी "
            "स्रोत अंश बिना किसी परिवर्तन के मूल भाषा में प्रस्तुत किए गए हैं।"
        ),
        "limit_no_relevant_records": "पर्याप्त रूप से प्रासंगिक सत्यापित स्रोत रिकॉर्ड नहीं मिले।",
        "limit_no_verified_records": "ज्ञानकोष में कोई सत्यापित स्रोत रिकॉर्ड उपलब्ध नहीं हैं।",
        "limit_conflicting_sources": "परस्पर विरोधी स्रोत अंश मिले हैं; किसी भी संस्करण का चयन नहीं किया गया।",
        "limit_invalid_provider": "कॉन्फ़िगर किया गया उत्तर प्रदाता अमान्य है।",
        "limit_provider_validation": "प्रदाता के उत्तर को सुरक्षित रूप से सत्यापित नहीं किया जा सका।",
        "limit_no_supported_claims": "प्रदाता ने साक्ष्य-समर्थित कोई दावा वापस नहीं किया।",
        "limit_verbatim_only": (
            "उत्तर में प्राप्त स्रोत अंशों को यथावत उद्धृत किया गया है; सारांश के लिए कोई AI प्रदाता कॉन्फ़िगर नहीं है।"
        ),
        "limit_personalized_advice": "यह सामान्य कानूनी जानकारी है, व्यक्तिगत कानूनी सलाह नहीं।",
        "limit_currentness": (
            "प्रदान किए गए सत्यापित मेटाडेटा के अतिरिक्त वर्तमान कानूनी स्थिति स्वतंत्र रूप से स्थापित नहीं की गई है।"
        ),
        "limit_jurisdiction": "प्रश्न में कोई राज्य या स्थानीय क्षेत्राधिकार निर्दिष्ट नहीं किया गया है।",
        "page_label": "पृष्ठ",
        "rule_section_label": "Rule/Section",
        "subsection_label": "उप-धारा",
        "subrule_subsection_label": "उप-नियम/उप-धारा",
        "error_json_required": "JSON ऑब्जेक्ट आवश्यक है।",
        "error_empty_message": "भेजने से पहले कृपया अपना प्रश्न या संदेश दर्ज करें।",
        "error_unsupported_language": "असमर्थित भाषा। English (en), ಕನ್ನಡ (kn), या हिन्दी (hi) चुनें।",
        "error_invalid_conversation_id": "अमान्य संवाद ID।",
        "error_conversation_not_found": "संवाद नहीं मिला।",
        "error_create_conversation_db": "डेटाबेस त्रुटि के कारण नया संवाद बनाया नहीं जा सका।",
        "error_delete_conversation_db": "डेटाबेस त्रुटि के कारण संवाद हटाया नहीं जा सका।",
        "error_save_messages_db": "डेटाबेस त्रुटि के कारण संवाद संदेश सहेजे नहीं जा सके।",
        "message_conversation_cleared": "संवाद साफ़ कर दिया गया है।",
        "error_auth_required": "आगे बढ़ने के लिए लॉगिन आवश्यक है।",
        "error_csrf_invalid": "फ़ॉर्म सुरक्षा टोकन गुम या अमान्य है।",
        "error_request_too_large": "अपलोड की गई फ़ाइल अनुमत अधिकतम आकार से बड़ी है।",
        "error_not_found": "अनुरोधित संसाधन नहीं मिला।",
        "error_db_unavailable": "डेटाबेस सेवा अस्थायी रूप से अनुपलब्ध है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
        "error_db_generic": "आपके अनुरोध को संसाधित करते समय डेटाबेस त्रुटि हुई।",
        "error_server_unexpected": "एक अप्रत्याशित सर्वर त्रुटि हुई।",
    },
}


def normalize_language(value: Any) -> str:
    """Validate and normalize a requested chat response language to en, kn, or hi."""
    if value is None:
        return DEFAULT_LANGUAGE
    if not isinstance(value, str):
        raise ValueError("Unsupported language. Choose English (en), Kannada (kn), or Hindi (hi).")
    cleaned = value.strip()
    if not cleaned:
        return DEFAULT_LANGUAGE
    normalized = _LANGUAGE_ALIASES.get(cleaned.lower()) or _LANGUAGE_ALIASES.get(cleaned)
    if not normalized:
        raise ValueError("Unsupported language. Choose English (en), Kannada (kn), or Hindi (hi).")
    return normalized


def get_language_info(language: str) -> dict[str, str]:
    normalized = normalize_language(language)
    return SUPPORTED_LANGUAGES[normalized]


def get_language_messages(language: str) -> dict[str, str]:
    normalized = normalize_language(language)
    return LANGUAGE_MESSAGES[normalized]


def resolve_request_language(req: Any, data: dict[str, Any] | None = None) -> str:
    """Best-effort language detection from body, X-Satya-Language header, or query param."""
    candidates = []
    if isinstance(data, dict):
        candidates.append(data.get("language"))
    headers = getattr(req, "headers", None)
    if headers is not None:
        candidates.append(headers.get("X-Satya-Language"))
    args = getattr(req, "args", None)
    if args is not None:
        candidates.append(args.get("language"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            try:
                return normalize_language(candidate)
            except ValueError:
                continue
    return DEFAULT_LANGUAGE


_KANNADA_CHAR_PATTERN = re.compile(r"[\u0C80-\u0CFF]")
_DEVANAGARI_CHAR_PATTERN = re.compile(r"[\u0900-\u097F]")
_QUERY_TOKEN_PATTERN = re.compile(r"[^\s\.,;:!?()\[\]{}\"'/\\|<>@#$%^&*+=~`–—-]+")

_NON_EN_FILLER_STEMS = (
    # Kannada question/instruction words & particles
    "ಪರಿಶೀಲಿಸಲಾದ", "ಪರಿಶೀಲಿಸಿದ", "ಸಂಬಂಧ", "ನಿಖರವಾದ", "ಆಧರಿಸಿ", "ತಿಳಿಸಿ", "ವಿವರಿಸಿ", "ಹೇಳಿ",
    "ಯಾವುವು", "ಯಾವುದು", "ಯಾವ", "ಏನು", "ಹೇಗೆ", "ಎಷ್ಟು", "ಯಾರು", "ಎಲ್ಲಿ", "ಯಾವಾಗ",
    "ಪ್ರಕಾರ", "ಕುರಿತು", "ಬಗ್ಗೆ", "ಮೂಲಗಳನ್ನು", "ಮೂಲಗಳು", "ಮೂಲ", "ಕಾನೂನು", "ಸಂಖ್ಯೆ",
    "ಸಾಕ್ಷ್ಯವನ್ನು", "ಸಾಕ್ಷ್ಯ", "ಉಲ್ಲೇಖ", "ಮಾತ್ರ", "ಮತ್ತು", "ಹಾಗೂ", "ಅಥವಾ", "ನೀಡಿ",
    "ಒದಗಿಸಿ", "ಇದರ", "ಅದರ", "ಈ", "ಆ", "ರ", "ಗೆ", "ಕೆ", "ಲ್ಲಿ", "ನ್ನು", "ಗಳ",
    # Hindi question/instruction words & particles
    "सत्यापित", "संबंधित", "सटीक", "आधारित", "केवल", "अनुसार", "बताएं", "बताइए",
    "समझाएं", "स्पष्ट", "कीजिए", "दीजिए", "प्रदान", "करें", "कौन", "क्या", "कैसे",
    "कहाँ", "कब", "कितने", "साक्ष्य", "स्रोत", "संदर्भ", "संख्या", "कानूनी", "विधि",
    "और", "तथा", "या", "के", "की", "का", "को", "से", "में", "पर", "हैं", "है", "हों",
)

_LEGAL_STEM_TO_ENGLISH = {
    # Kannada legal terms -> statutory English keywords
    "ಡಿಜಿಟಲ್": ("digital",),
    "ವೈಯಕ್ತಿಕ": ("personal",),
    "ದತ್ತಾಂಶ": ("data",),
    "ಡೇಟಾ": ("data",),
    "ಸಂರಕ್ಷಣ": ("protection",),
    "ರಕ್ಷಣ": ("protection",),
    "ಗೌಪ್ಯತ": ("privacy",),
    "ನಿಯಮ": ("rules",),
    "ಕಾಯ್ದೆ": ("act",),
    "ಅಧಿನಿಯಮ": ("act",),
    "ಹಕ್ಕು": ("rights",),
    "ವ್ಯಕ್ತಿ": ("principal", "individual"),
    "ಸಮ್ಮತಿ": ("consent",),
    "ಒಪ್ಪಿಗೆ": ("consent",),
    "ಮಕ್ಕಳ": ("child", "children"),
    "ಮಗು": ("child",),
    "ಪೋಷಕ": ("parent",),
    "ದೂರು": ("grievance", "complaint"),
    "ಕುಂದುಕೊರತೆ": ("grievance",),
    "ದಂಡ": ("penalty",),
    "ಶಿಕ್ಷೆ": ("punishment", "penalty"),
    "ಮಂಡಳಿ": ("board",),
    "ಬಾಧ್ಯತ": ("obligations",),
    "ಕರ್ತವ್ಯ": ("duties", "obligations"),
    "ಫಿಡ್ಯೂಶಿಯರಿ": ("fiduciary",),
    "ಪ್ರೊಸೆಸರ್": ("processor",),
    "ಅಳಿಸುವ": ("erasure",),
    "ತಿದ್ದುಪಡಿ": ("correction", "amendment"),
    "ಉಲ್ಲಂಘನೆ": ("breach",),
    "ನೋಟಿಸ್": ("notice",),
    "ಸೂಚನೆ": ("notice",),
    "ಗ್ರಾಹಕ": ("consumer",),
    "ನೇರ": ("direct",),
    "ಮಾರಾಟ": ("selling",),
    "ಇ-ಕಾಮರ್ಸ್": ("ecommerce",),
    "ಸಂವಿಧಾನ": ("constitution",),
    "ಅನುಚ್ಛೇದ": ("article",),
    "ವಿಭಾಗ": ("section",),
    "ಕಲಂ": ("section",),
    "ಮಾಹಿತಿ": ("information",),
    "ಭಾರತೀಯ": ("bharatiya",),
    "ನ್ಯಾಯ": ("nyaya",),
    "ಸಂಹಿತ": ("sanhita",),
    "ನಾಗರಿಕ": ("nagarik",),
    "ಸುರಕ್ಷ": ("suraksha",),
    "ಸಾಕ್ಷ್ಯ": ("sakshya",),
    "ಮಧ್ಯಸ್ಥಿಕೆ": ("mediation",),
    "ನ್ಯಾಯವ್ಯಾಪ್ತಿ": ("jurisdiction",),
    "ಪಿರಮಿಡ್": ("pyramid",),
    "ಸ್ಕೀಮ್": ("scheme",),
    # Hindi legal terms -> statutory English keywords
    "डिजिटल": ("digital",),
    "व्यक्तिगत": ("personal",),
    "डेटा": ("data",),
    "संरक्षण": ("protection",),
    "गोपनीयता": ("privacy",),
    "नियम": ("rules",),
    "अधिनियम": ("act",),
    "अधिकार": ("rights",),
    "व्यक्ति": ("principal", "individual"),
    "सहमति": ("consent",),
    "बच्चों": ("children",),
    "बच्चे": ("child",),
    "बाल": ("child",),
    "माता-पिता": ("parent",),
    "शिकायत": ("grievance", "complaint"),
    "दंड": ("penalty",),
    "जुर्माना": ("penalty",),
    "बोर्ड": ("board",),
    "दायित्व": ("obligations",),
    "कर्तव्य": ("duties", "obligations"),
    "फिड्यूशियरी": ("fiduciary",),
    "उल्लंघन": ("breach",),
    "सूचना": ("information", "notice"),
    "नोटिस": ("notice",),
    "उपभोक्ता": ("consumer",),
    "प्रत्यक्ष": ("direct",),
    "बिक्री": ("selling",),
    "संविधान": ("constitution",),
    "अनुच्छेद": ("article",),
    "धारा": ("section",),
    "भारतीय": ("bharatiya",),
    "न्याय": ("nyaya",),
    "संहिता": ("sanhita",),
    "नागरिक": ("nagarik",),
    "सुरक्षा": ("suraksha",),
    "साक्ष्य": ("sakshya",),
    "मध्यस्थता": ("mediation",),
    "अधिकारिता": ("jurisdiction",),
    "पिरामिड": ("pyramid",),
}

_SORTED_LEGAL_STEMS = sorted(_LEGAL_STEM_TO_ENGLISH.keys(), key=len, reverse=True)


def detect_question_language(question: str) -> str | None:
    """Detect Kannada or Hindi script in a question; return None for Latin/English text."""
    if not isinstance(question, str) or not question.strip():
        return None
    if _KANNADA_CHAR_PATTERN.search(question):
        return "kn"
    if _DEVANAGARI_CHAR_PATTERN.search(question):
        return "hi"
    return None


def resolve_answer_language(question: str, selected_language: Any = None) -> str:
    """Use the question's script language when Kannada/Hindi, else the selected language."""
    detected = detect_question_language(question)
    if detected:
        return detected
    return normalize_language(selected_language)


def expand_multilingual_query(question: str) -> str:
    """Translate Kannada/Hindi legal keywords in a query to English statutory search terms."""
    if detect_question_language(question) is None:
        return ""
    tokens = _QUERY_TOKEN_PATTERN.findall(question or "")
    has_data_context = any(
        tok.startswith(("ಡಿಜಿಟಲ್", "ವೈಯಕ್ತಿಕ", "ದತ್ತಾಂಶ", "ಡೇಟಾ", "ಸಂರಕ್ಷಣ", "डिजिटल", "व्यक्तिगत", "डेटा", "संरक्षण"))
        for tok in tokens
    )
    has_evidence_act_context = any(
        tok.startswith(("ಭಾರತೀಯ", "bharatiya", "ಅಧಿನಿಯಮ", "adhiniyam", "भारतीय", "2023"))
        for tok in tokens
    )
    expanded: list[str] = []
    seen: set[str] = set()
    has_mapped_term = False

    for token in tokens:
        if token.isascii() and (len(token) >= 2 or token.isdigit()):
            key = token.casefold()
            if key not in seen:
                seen.add(key)
                expanded.append(token)
            continue

        if any(token.startswith(filler) for filler in _NON_EN_FILLER_STEMS) or len(token) < 2:
            if token.startswith("ಸಾಕ್ಷ್ಯ") and has_evidence_act_context:
                pass
            else:
                continue

        matched_english: tuple[str, ...] | None = None
        for stem in _SORTED_LEGAL_STEMS:
            if token.startswith(stem):
                matched_english = _LEGAL_STEM_TO_ENGLISH[stem]
                if stem in {"ವ್ಯಕ್ತಿ", "व्यक्ति"}:
                    matched_english = ("principal",) if has_data_context else ("person", "individual")
                elif stem in {"ಸಾಕ್ಷ್ಯ", "साक्ष्य"} and not has_evidence_act_context:
                    matched_english = None
                break

        if matched_english:
            has_mapped_term = True
            for en_term in matched_english:
                if en_term not in seen:
                    seen.add(en_term)
                    expanded.append(en_term)
            continue

        if token in _NON_EN_FILLER_STEMS or len(token) < 2:
            continue
        if token not in seen:
            seen.add(token)
            expanded.append(token)

    return " ".join(expanded) if has_mapped_term else ""

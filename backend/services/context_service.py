import re
from typing import Any
from re import escape


_CURRENTNESS_TERMS = re.compile(
    r"\b(current(?:ly)?|in force|still valid|latest|as of today|presently|"
    r"amended|repealed|commenced|effective date)\b",
    re.IGNORECASE,
)
_ADVICE_TERMS = re.compile(
    r"\b(should i|what should i do|my case|my situation|represent me|"
    r"legal advice|can i sue|will i win)\b",
    re.IGNORECASE,
)
_INDIAN_STATE_OR_UT = (
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh",
    "Dadra and Nagar Haveli and Daman and Diu", "Himachal Pradesh",
    "Jammu and Kashmir", "Madhya Pradesh", "Uttar Pradesh", "West Bengal",
    "Chandigarh", "Chhattisgarh", "Jharkhand", "Karnataka", "Maharashtra",
    "Meghalaya", "Nagaland", "Puducherry", "Pondicherry", "Rajasthan",
    "Tamil Nadu", "Telangana", "Uttarakhand", "Arunachal", "Assam", "Bihar",
    "Delhi", "Goa", "Gujarat", "Haryana", "Kerala", "Ladakh", "Lakshadweep",
    "Manipur", "Mizoram", "Odisha", "Punjab", "Sikkim", "Tripura",
)
_LOCAL_SCOPE_TERMS = re.compile(
    r"\b(?:" + "|".join(escape(name) for name in _INDIAN_STATE_OR_UT) + r")\b",
    re.IGNORECASE,
)


def classify_question(question: str) -> dict[str, Any]:
    """Return cautious context hints; these are not legal determinations."""
    return {
        "jurisdiction": "India",
        "state_or_local_scope_specified": bool(_LOCAL_SCOPE_TERMS.search(question)),
        "asks_current_legal_status": bool(_CURRENTNESS_TERMS.search(question)),
        "appears_personalized": bool(_ADVICE_TERMS.search(question)),
    }

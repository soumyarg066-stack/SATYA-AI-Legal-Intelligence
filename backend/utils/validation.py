import re
from email.utils import parseaddr

from flask import request


def json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None

def valid_email(value):
    value = (value or "").strip()
    if len(value) > 254 or parseaddr(value)[1] != value:
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


def clean_text(value, maximum):
    if not isinstance(value, str):
        return ""
    return value.strip()[:maximum]

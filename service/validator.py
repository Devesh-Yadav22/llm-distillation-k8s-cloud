"""service/validator.py: Schema validation logic using only Python standard library."""
import json
import re

VALID_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
}

REQUIRED_KEYS = {"intent", "date", "time", "place"}


def validate_and_extract_json(raw_text: str):
    """Validates raw text against schema.json requirements.
    Returns (True, parsed_dict) or (False, None).
    """
    if not raw_text or not isinstance(raw_text, str):
        return False, None

    # Search for JSON object within text
    json_match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
    if not json_match:
        return False, None

    try:
        obj = json.loads(json_match.group(0))
    except (json.JSONDecodeError, TypeError):
        return False, None

    if not isinstance(obj, dict):
        return False, None

    if set(obj.keys()) != REQUIRED_KEYS:
        return False, None

    if obj.get("intent") not in VALID_INTENTS:
        return False, None

    for slot in ("date", "time", "place"):
        val = obj.get(slot)
        if val is not None and not isinstance(val, str):
            return False, None

    return True, obj


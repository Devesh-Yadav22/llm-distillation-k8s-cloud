"""tests/test_service_validation.py: Unit tests for schema validation and fault injection logic."""
import unittest
from service.validator import validate_and_extract_json, VALID_INTENTS, REQUIRED_KEYS


class TestServiceValidation(unittest.TestCase):
    def test_valid_json_payload(self):
        """Test that a compliant 4-key JSON string is successfully validated."""
        raw = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'
        is_valid, obj = validate_and_extract_json(raw)
        self.assertTrue(is_valid)
        self.assertEqual(obj["intent"], "alarm_set")
        self.assertEqual(obj["date"], "tomorrow")
        self.assertEqual(obj["time"], "seven am")
        self.assertIsNone(obj["place"])

    def test_missing_required_keys(self):
        """Test that JSON missing any of the 4 required keys fails validation."""
        raw = '{"intent": "weather_query", "place": "london"}'
        is_valid, obj = validate_and_extract_json(raw)
        self.assertFalse(is_valid)
        self.assertIsNone(obj)

    def test_extra_keys_rejected(self):
        """Test that JSON with unexpected extra keys fails strict schema validation."""
        raw = '{"intent": "alarm_set", "date": null, "time": "5am", "place": null, "confidence": 0.99}'
        is_valid, obj = validate_and_extract_json(raw)
        self.assertFalse(is_valid)
        self.assertIsNone(obj)

    def test_invalid_intent(self):
        """Test that an intent outside the 8 allowed intents fails validation."""
        raw = '{"intent": "play_music", "date": null, "time": null, "place": null}'
        is_valid, obj = validate_and_extract_json(raw)
        self.assertFalse(is_valid)
        self.assertIsNone(obj)

    def test_non_json_fault_inject(self):
        """Test that non-JSON string (like that produced by FAULT_INJECT=1) fails validation."""
        raw = "not json"
        is_valid, obj = validate_and_extract_json(raw)
        self.assertFalse(is_valid)
        self.assertIsNone(obj)


if __name__ == "__main__":
    unittest.main()

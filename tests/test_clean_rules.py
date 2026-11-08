"""tests/test_clean_rules.py: Unit tests for dataset cleaning rules (a) through (e)."""
import unittest
from worker.clean import check_record, VALID_INTENTS, REQUIRED_KEYS


class TestCleanRules(unittest.TestCase):
    def test_rule_a_invalid_json(self):
        """Rule (a): replies that are not valid JSON must be flagged."""
        rec = {
            "id": "T001",
            "text": "set alarm for tomorrow",
            "teacher_raw": "Here is your JSON: {broken"
        }
        status, parsed = check_record(rec)
        self.assertEqual(status, 'a')
        self.assertIsNone(parsed)

    def test_rule_b_invalid_keys(self):
        """Rule (b): replies whose keys are not exactly intent, date, time, and place."""
        rec = {
            "id": "T002",
            "text": "what is the weather today",
            "teacher_raw": '{"intent": "weather_query", "date": "today"}'
        }
        status, parsed = check_record(rec)
        self.assertEqual(status, 'b')

    def test_rule_c_invalid_intent(self):
        """Rule (c): replies whose intent is not one of the eight."""
        rec = {
            "id": "T003",
            "text": "order pizza",
            "teacher_raw": '{"intent": "food_order", "date": null, "time": null, "place": null}'
        }
        status, parsed = check_record(rec)
        self.assertEqual(status, 'c')

    def test_rule_d_hallucinated_slot(self):
        """Rule (d): replies with a slot value that is neither null nor in command."""
        rec = {
            "id": "T004",
            "text": "what is the weather in boston",
            "teacher_raw": '{"intent": "weather_query", "date": null, "time": null, "place": "chicago"}'
        }
        status, parsed = check_record(rec)
        self.assertEqual(status, 'd')

    def test_valid_record_passes(self):
        """Valid record where slot exists verbatim in text passes with 'ok'."""
        rec = {
            "id": "T005",
            "text": "what is the weather in boston",
            "teacher_raw": '{"intent": "weather_query", "date": null, "time": null, "place": "boston"}'
        }
        status, parsed = check_record(rec)
        self.assertEqual(status, 'ok')
        self.assertEqual(parsed["place"], "boston")


if __name__ == "__main__":
    unittest.main()

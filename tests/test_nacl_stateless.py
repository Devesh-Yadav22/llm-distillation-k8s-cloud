"""tests/test_nacl_stateless.py: Unit tests for NACL simulation against sample packets."""
import json
import unittest
from tools.nacl_sim import load_rules, decide


class TestNACLStateless(unittest.TestCase):
    def test_nacl_against_sample_packets(self):
        rules = load_rules("network/nacl.json")
        with open("network/packets_sample.jsonl", "r", encoding="utf-8") as f:
            packets = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(packets), 6)
        for pkt in packets:
            action, rule = decide(rules, pkt)
            self.assertEqual(
                action,
                pkt["expected"],
                f"Packet {pkt['id']} expected {pkt['expected']} but got {action}"
            )


if __name__ == "__main__":
    unittest.main()

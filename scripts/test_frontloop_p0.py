"""Model-free P0 tests: When2Call 40 materialize + oracle scoring + loc schema."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "experiments" / "monkeys-passk-frontloop"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(ROOT / "scripts"))

from materialize_when2call import main as materialize  # noqa: E402
from monkeys_passk_frontloop.evaluator import score_when2call  # noqa: E402
from monkeys_passk_frontloop.schema import (  # noqa: E402
    parse_loc_action,
    parse_when2call_action,
    private_answers,
    public_fixture,
    selected,
    validate_loc_action,
)


class When2CallOracle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        materialize()
        cls.ids = selected()["stage1_when2call"]["ids"]
        cls.answers = private_answers()

    def test_forty_ids_and_private_labels(self) -> None:
        self.assertEqual(len(self.ids), 40)
        self.assertEqual(set(self.ids), set(self.answers))
        hist = {k: 0 for k in ("tool_call", "request_for_info", "cannot_answer")}
        for uid in self.ids:
            pub = public_fixture(uid)
            self.assertNotIn("correct_answer", pub)
            self.assertIn("question", pub)
            self.assertIn("tools", pub)
            hist[self.answers[uid]["correct_answer"]] += 1
        self.assertEqual(sum(hist.values()), 40)
        for count in hist.values():
            self.assertGreaterEqual(count, 13)
            self.assertLessEqual(count, 14)

    def test_oracle_gold_outputs(self) -> None:
        cases = [
            ('{"action":"tool_call","tool":"x.get","args":{"id":"1"}}', "tool_call", True),
            ('{"tool":"x.get","args":{"id":"1"}}', "tool_call", True),
            ('{"action":"request_for_info","question":"Which city?"}', "request_for_info", True),
            ('{"action":"cannot_answer"}', "cannot_answer", True),
        ]
        uid = self.ids[0]
        gold = self.answers[uid]
        allowed = [t["name"] for t in public_fixture(uid)["tools"]]
        for raw, predicted, fmt in cases:
            scored = score_when2call(raw, gold, allowed)
            self.assertTrue(scored["format_ok"] is fmt)
            self.assertEqual(scored["predicted_action"], predicted)
            self.assertEqual(scored["semantic_ok"], predicted == gold["correct_answer"])

    def test_format_failures(self) -> None:
        action, reason = parse_when2call_action("sorry I cannot help")
        self.assertIsNone(action)
        self.assertEqual(reason, "no_json_object")
        action, reason = parse_when2call_action('{"final": "15C"}')
        self.assertIsNone(action)
        self.assertEqual(reason, "missing_action")

    def test_wrong_behavior_is_format_ok_semantic_fail(self) -> None:
        cannot_ids = [u for u, g in self.answers.items() if g["correct_answer"] == "cannot_answer"]
        uid = cannot_ids[0]
        scored = score_when2call(
            '{"action":"tool_call","tool":"weather.get","args":{"city":"London"}}',
            self.answers[uid],
            ["stock_price.get"],
        )
        self.assertTrue(scored["format_ok"])
        self.assertFalse(scored["semantic_ok"])
        self.assertFalse(scored["tool_in_list"])


class LocSchema(unittest.TestCase):
    def test_grep_and_final(self) -> None:
        action, err = parse_loc_action('{"tool":"grep","args":{"pattern":"token"}}')
        self.assertIsNone(err)
        self.assertIsNone(validate_loc_action(action))
        action, err = parse_loc_action('{"final":"src/auth.py::check_token"}')
        self.assertIsNone(err)
        self.assertEqual(action["final"], "src/auth.py::check_token")

    def test_run_rejects_non_test(self) -> None:
        action, err = parse_loc_action('{"tool":"run","args":{"target":"rm -rf"}}')
        self.assertIsNone(err)
        self.assertEqual(validate_loc_action(action), "run_target_not_test")

    def test_read_file_defaults_ok(self) -> None:
        action, err = parse_loc_action('{"tool":"read_file","args":{"path":"a.py"}}')
        self.assertIsNone(err)
        self.assertIsNone(validate_loc_action(action))


if __name__ == "__main__":
    unittest.main()

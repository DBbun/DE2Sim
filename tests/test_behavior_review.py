from __future__ import annotations

import json
import re
import unittest

from de2sim.behaviors.proposal_generator import generate_behavior_proposals
from de2sim.visualization.behavior_review import build_behavior_review_data, render_behavior_review_html
from tests.test_asot_schema import representative_asot


SPECIAL_TEXT = "quotes \" apostrophe ' backslash \\ multiline\nunicode cafe \u2603 </script> line\u2028para\u2029"


class BehaviorReviewTests(unittest.TestCase):
    def test_review_html_is_standalone_safe_and_contains_decision_tools(self) -> None:
        asot = representative_asot().to_dict()
        _prompt, proposals = generate_behavior_proposals(asot, "offline")
        data = build_behavior_review_data(asot, proposals)
        html = render_behavior_review_html(data)
        self.assertIn("Behavior Proposal Review", html)
        self.assertIn("State-machine diagram", html)
        self.assertIn("Download decisions JSON", html)
        self.assertIn("Approve", html)
        self.assertIn("Reject", html)
        self.assertIn("Needs revision", html)
        self.assertIn("createElementNS", html)
        self.assertNotIn('src="http', html)
        self.assertNotIn("<link", html.lower())
        for unsafe in ("eval(", "exec(", "Function(", "document.write", "innerHTML", "insertAdjacentHTML"):
            self.assertNotIn(unsafe, html)

    def test_embedded_json_is_escaped_parseable_and_not_interpolated_into_javascript(self) -> None:
        asot = representative_asot().to_dict()
        _prompt, proposals = generate_behavior_proposals(asot, "offline")
        base = proposals["proposals"][0]
        proposals["proposals"] = []
        for index in range(7):
            item = dict(base)
            item["proposal_id"] = f"behavior-proposal-special-{index}"
            item["name"] = f"Special proposal {index} {SPECIAL_TEXT}"
            item["description"] = SPECIAL_TEXT
            item["states"] = [SPECIAL_TEXT, f"ready-{index}"]
            item["transitions"] = [{"from": SPECIAL_TEXT, "to": f"ready-{index}", "trigger": SPECIAL_TEXT}]
            item["guards"] = [SPECIAL_TEXT]
            item["actions"] = [SPECIAL_TEXT]
            item["assumptions"] = [SPECIAL_TEXT]
            item["risks"] = [SPECIAL_TEXT]
            proposals["proposals"].append(item)

        data = build_behavior_review_data(asot, proposals)
        html = render_behavior_review_html(data)
        embedded = _extract_data_script(html)
        parsed = json.loads(embedded)
        executable_js = _executable_script(html)

        self.assertEqual(len(parsed["cards"]), 7)
        self.assertIn(SPECIAL_TEXT, parsed["cards"][0]["proposal"]["description"])
        self.assertIn("\\u003c/script\\u003e", embedded.lower())
        self.assertIn("\\u0026", render_behavior_review_html({"amp": "&"}))
        self.assertIn("\\u2028", embedded)
        self.assertIn("\\u2029", embedded)
        self.assertNotIn(SPECIAL_TEXT, executable_js)
        self.assertIn("function render()", executable_js)
        self.assertIn("drawMachine(holder,p)", executable_js)
        self.assertIn("new Blob", executable_js)
        self.assertIn("URL.createObjectURL", executable_js)
        self.assertNotIn("file://", executable_js)
        self.assertNotIn("fetch(", executable_js)
        self.assertNotIn("location.href", executable_js)
        self.assertNotIn("iframe", executable_js.lower())
        self.assertIn('+"\\n"', executable_js)
        self.assertNotIn('+"\n"', executable_js)


def _extract_data_script(html: str) -> str:
    match = re.search(
        r'<script id="behavior-review-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("behavior-review-data script not found")
    return match.group(1)


def _executable_script(html: str) -> str:
    scripts = re.findall(r"<script(?: [^>]*)?>(.*?)</script>", html, flags=re.DOTALL)
    if len(scripts) < 2:
        raise AssertionError("executable script not found")
    return scripts[-1]


if __name__ == "__main__":
    unittest.main()

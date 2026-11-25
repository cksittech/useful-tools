# Tests of the generation API (no Codex call: generate_markdown's Codex part is replaced).
# Run from the app folder: python -m unittest discover tests

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import api_server
import common
from data import APP_NAME, MAX_REQUEST_CHARS


class PromptTest(unittest.TestCase):
    def test_new_deck_prompt_has_the_request(self):
        prompt = common.build_prompt("  ten slides on AI  ", None)
        self.assertIn("ten slides on AI", prompt)
        self.assertNotIn("Current presentation", prompt)

    def test_revise_prompt_has_the_request_and_the_deck(self):
        prompt = common.build_prompt("add costs", "# Deck\n\n### Plan\n")
        self.assertIn("add costs", prompt)
        self.assertIn("# Deck\n\n### Plan\n", prompt)
        self.assertIn("exactly as it is", prompt)

    def test_bad_requests_are_refused(self):
        for request, current in [("", None), ("   ", None), ("x", ""), ("x", "\n "), ("x" * (MAX_REQUEST_CHARS + 1), None)]:
            with self.assertRaises(ValueError):
                common.build_prompt(request, current)

    def test_code_fence_is_removed(self):
        self.assertEqual(common.strip_code_fence("```markdown\n# A\n```"), "# A")
        self.assertEqual(common.strip_code_fence("# A\n```x```"), "# A\n```x```")


class EndpointTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api_server.app)

    def test_health_and_who(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        who = self.client.get("/who").json()
        self.assertEqual(who["name"], APP_NAME)
        self.assertEqual(Path(who["path"]), Path(api_server.__file__).parent.resolve())

    def test_generate_passes_the_mode_on(self):
        with mock.patch.object(common, "generate_markdown", return_value="# A\n") as gen:
            res = self.client.post("/api/generate", json={"request": "r", "current": "# Old\n"})
            self.assertEqual(res.json(), {"markdown": "# A\n"})
            gen.assert_called_once_with("r", "# Old\n")
            self.client.post("/api/generate", json={"request": "r"})
            gen.assert_called_with("r", None)

    def test_errors_become_status_codes(self):
        self.assertEqual(self.client.post("/api/generate", json={"request": " "}).status_code, 400)
        with mock.patch.object(common, "generate_markdown", side_effect=common.GenerationError("no login")):
            res = self.client.post("/api/generate", json={"request": "r"})
            self.assertEqual((res.status_code, res.json()), (502, {"detail": "no login"}))

    def preflight(self, origin):
        return self.client.options("/api/generate", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})

    def test_cors_allows_the_page_opened_from_a_file_or_github_pages(self):
        for origin in ["null", "https://cksittech.github.io"]:
            self.assertEqual(self.preflight(origin).status_code, 200, origin)

    def test_cors_refuses_other_sites(self):
        for origin in ["https://example.com", "http://127.0.0.1:8000"]:
            self.assertEqual(self.preflight(origin).status_code, 400, origin)


if __name__ == "__main__":
    unittest.main()

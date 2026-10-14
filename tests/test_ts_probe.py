import json
import tempfile
import unittest
from pathlib import Path

from bot.ts_probe import describe_json, describe_script


class TestTsProbe(unittest.TestCase):
    def test_never_prints_secret_values(self):
        d = Path(tempfile.mkdtemp())
        (d / "t.json").write_text(json.dumps({"access_token": "SECRETVALUE123", "refresh_token": "OTHERSECRET", "expires_in": 1200,
                                              "token_type": "Bearer", "scope": "MarketData ReadAccount"}))
        text = "\n".join(describe_json(d / "t.json"))
        self.assertNotIn("SECRETVALUE123", text)
        self.assertNotIn("OTHERSECRET", text)
        self.assertIn("expires_in: int, largo 4 = 1200", text)
        self.assertIn("access_token: str", text)
        self.assertNotIn("Bearer", text)                       # token_type contiene "token": no se muestra el valor

    def test_script_outline_hides_assignments_and_query_values(self):
        d = Path(tempfile.mkdtemp())
        (d / "s.py").write_text("import requests\nCLIENT_SECRET = 'abc123SECRET'\ndef get():\n    return requests.post('https://signin.tradestation.com/oauth/token?client_secret=abc123SECRET')\n")
        text = "\n".join(describe_script(d / "s.py"))
        self.assertNotIn("abc123SECRET", text)
        self.assertIn("def get():", text)
        self.assertIn("https://signin.tradestation.com/oauth/token", text)


if __name__ == "__main__":
    unittest.main()

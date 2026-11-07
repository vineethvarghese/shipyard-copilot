import os
import unittest

from helpers import HookTestCase

C = "shipyard:coordinator"
NOTES = ".ai/planning/discovery.md"

# Fake, non-functional sample values built at runtime so this file holds no secret-shaped literals.
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----"
SAMPLES = {
    "private key block": PEM,
    "cloud access key ID": "key id " + "AKIA" + "ABCDEFGHIJKLMNOP",
    "API key, secret, token or password assignment": "api_key = " + "abcd1234" * 3,
    "JSON Web Token": "eyJ" + "hbGciOiJIUzI1NiJ9" + ".eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0" + ".dozjgNryP4J3jVmNHl0w5N",
    "connection-string password": "Server=db;User Id=app;Password=" + "hunter2x;",
    "connection-string account key": "Endpoint=https://store.example.com;AccountKey=" + "c2VjcmV0a2V5MTIz;",
    "signed URL signature": "https://files.example.com/a.zip?sv=1&sig=" + "Zm9vYmFyYmF6cXV4",
    "URL with embedded credentials": "postgres://admin:" + "s3cretpw@db.example.com/app",
    "GitHub token": "token ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2",
    "GitHub fine-grained token": "github_pat_" + "11ABCDEFG0123456789_abcdefXYZ",
    "chat workspace token": "xoxb-" + "123456789012-abcdefghij",
}

REDACTED = [
    "api_key: <REDACTED> (stored in env var API_KEY)",
    "Server=db;User Id=app;Password=<REDACTED>;",
    "AccountKey=<REDACTED>;",
    "https://files.example.com/a.zip?sig=<REDACTED>",
    "postgres://admin:<REDACTED>@db.example.com/app",
    "token: <REDACTED>",
    "The tokenizer is configured in src/config/tokens.ts; rotate the password in the team secret manager.",
]


class SecretsGuard(HookTestCase):
    script = "secrets-guard.py"

    def write(self, agent, rel, content):
        return self.run_tool(agent, "Write", {"file_path": os.path.join(self.repo.path, rel), "content": content})

    def test_non_shipyard_passthrough(self):
        self.assertAllowed(self.write(None, NOTES, SAMPLES["private key block"]))

    def test_outside_ai_not_scanned(self):
        self.assertAllowed(self.write("shipyard:implementer", "src/cache/fixture.ts", SAMPLES["GitHub token"]))

    def test_every_pattern_denied(self):
        for label, text in SAMPLES.items():
            res = self.write(C, NOTES, "# Notes\n\n" + text + "\n")
            self.assertDenied(res, "<REDACTED>", "where")
            self.assertIn("line 3", res.stderr, label)

    def test_secret_value_not_echoed(self):
        res = self.write(C, NOTES, SAMPLES["GitHub token"])
        self.assertDenied(res)
        self.assertNotIn("a1B2c3D4e5F6g7H8i9J0k1L2", res.stderr)

    def test_redacted_allowed(self):
        for text in REDACTED:
            self.assertAllowed(self.write(C, NOTES, text))

    def test_edit_and_multiedit_scanned(self):
        path = os.path.join(self.repo.path, NOTES)
        self.assertDenied(self.run_tool("shipyard:security-reviewer", "Edit", {
            "file_path": path, "old_string": "a", "new_string": SAMPLES["chat workspace token"]}))
        self.assertDenied(self.run_tool(C, "MultiEdit", {"file_path": path, "edits": [
            {"old_string": "a", "new_string": "fine"},
            {"old_string": "b", "new_string": SAMPLES["cloud access key ID"]}]}))


if __name__ == "__main__":
    unittest.main()

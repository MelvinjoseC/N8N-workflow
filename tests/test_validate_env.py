import unittest
import os
import sys
import tempfile

# Add scripts directory to path to import validate_env
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import validate_env

class TestValidateEnv(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_parse_env_file(self):
        env_content = """
        # Comment line
        KEY1=value1
        KEY2='value2'
        KEY3="value3"
        EMPTY_LINE=
        """
        env_file = os.path.join(self.test_dir.name, ".env.test")
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)

        parsed = validate_env.parse_env_file(env_file)
        self.assertEqual(parsed.get("KEY1"), "value1")
        self.assertEqual(parsed.get("KEY2"), "value2")
        self.assertEqual(parsed.get("KEY3"), "value3")

    def test_audit_missing_keys(self):
        env_dict = {"KEY1": "val1"}
        example_dict = {"KEY1": "val1", "KEY2": "val2", "KEY3": "val3"}
        errors, warnings = validate_env.audit_environment(env_dict, example_dict, allow_placeholders=True)
        self.assertTrue(any("Missing required environment variable: 'KEY2'" in e for e in errors))
        self.assertTrue(any("Missing required environment variable: 'KEY3'" in e for e in errors))

    def test_audit_placeholder_passwords(self):
        env_dict = {
            "DB_PASSWORD": "secure-db-password-change-me",
            "N8N_ENCRYPTION_KEY": "valid-encryption-key-32-chars-long"
        }
        example_dict = {"DB_PASSWORD": "default", "N8N_ENCRYPTION_KEY": "key"}
        errors, warnings = validate_env.audit_environment(env_dict, example_dict, allow_placeholders=False)
        self.assertTrue(any("Insecure placeholder value detected in 'DB_PASSWORD'" in e for e in errors))

    def test_audit_encryption_key_too_short(self):
        env_dict = {
            "N8N_ENCRYPTION_KEY": "short-key"
        }
        example_dict = {"N8N_ENCRYPTION_KEY": "key"}
        errors, warnings = validate_env.audit_environment(env_dict, example_dict, allow_placeholders=True)
        self.assertTrue(any("'N8N_ENCRYPTION_KEY' is too short" in e for e in errors))

    def test_audit_valid_production_config(self):
        env_dict = {
            "DB_PASSWORD": "X9#kL2!mP90$qW88",
            "N8N_ENCRYPTION_KEY": "c092a4e93f77341209bca7f912cd34ef",
            "WEBHOOK_URL": "https://n8n.company.internal/"
        }
        example_dict = {
            "DB_PASSWORD": "change-me",
            "N8N_ENCRYPTION_KEY": "change-me",
            "WEBHOOK_URL": "https://example.com"
        }
        errors, warnings = validate_env.audit_environment(env_dict, example_dict, allow_placeholders=False)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)

if __name__ == "__main__":
    unittest.main()

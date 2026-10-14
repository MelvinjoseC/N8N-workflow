import unittest
import os
import tempfile
import json
import sys

# Add scripts directory to path to import lint_workflows
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import lint_workflows

class TestLintWorkflows(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for test workflow JSON files
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def create_temp_workflow(self, name, data):
        filepath = os.path.join(self.test_dir.name, f"{name}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        return filepath

    def test_is_hardcoded_secret(self):
        # Expressions should not be flagged
        self.assertFalse(lint_workflows.is_hardcoded_secret("={{ $env.MY_SECRET }}"))
        self.assertFalse(lint_workflows.is_hardcoded_secret("{{ $env.SECRET }}"))
        # Dummy or placeholder values should not be flagged
        self.assertFalse(lint_workflows.is_hardcoded_secret("dummy-value"))
        self.assertFalse(lint_workflows.is_hardcoded_secret("test_password"))
        self.assertFalse(lint_workflows.is_hardcoded_secret("127.0.0.1"))
        # Short strings should not be flagged
        self.assertFalse(lint_workflows.is_hardcoded_secret("abcd"))
        # Long, potential hex or high-entropy values should be flagged
        self.assertTrue(lint_workflows.is_hardcoded_secret("abcdef12345678901234"))
        self.assertTrue(lint_workflows.is_hardcoded_secret("ghijk-lmnopqrst-uvwxyz"))

    def test_valid_workflow(self):
        valid_data = {
            "nodes": [
                {
                    "name": "Start",
                    "type": "n8n-nodes-base.start",
                    "parameters": {}
                },
                {
                    "name": "HTTP Request",
                    "type": "n8n-nodes-base.httpRequest",
                    "parameters": {
                        "url": "https://api.github.com",
                        "authentication": "none",
                        "options": {
                            "timeout": 5000
                        }
                    }
                }
            ],
            "settings": {
                "errorWorkflow": "error-workflow-uuid-123"
            }
        }
        filepath = self.create_temp_workflow("valid_workflow", valid_data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)

    def test_missing_nodes(self):
        invalid_data = {
            "settings": {}
        }
        filepath = self.create_temp_workflow("missing_nodes", invalid_data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertTrue(any("Missing core 'nodes' array" in e for e in errors))

    def test_missing_error_workflow_warning(self):
        data = {
            "nodes": [
                {
                    "name": "Start",
                    "type": "n8n-nodes-base.start"
                }
            ],
            "settings": {}
        }
        filepath = self.create_temp_workflow("missing_error", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertEqual(len(errors), 0)
        self.assertTrue(any("No 'errorWorkflow' configured" in w for w in warnings))

    def test_error_trigger_ignores_error_workflow_warning(self):
        # A workflow containing an Error Trigger itself shouldn't trigger the warning
        data = {
            "nodes": [
                {
                    "name": "Error Trigger",
                    "type": "n8n-nodes-base.errorTrigger"
                }
            ],
            "settings": {}
        }
        filepath = self.create_temp_workflow("error_trigger_wf", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)

    def test_duplicate_node_name(self):
        data = {
            "nodes": [
                {
                    "name": "DuplicateNode",
                    "type": "n8n-nodes-base.start"
                },
                {
                    "name": "DuplicateNode",
                    "type": "n8n-nodes-base.set"
                }
            ],
            "settings": {
                "errorWorkflow": "some-id"
            }
        }
        filepath = self.create_temp_workflow("duplicate_nodes", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertTrue(any("Duplicate node name found: 'DuplicateNode'" in e for e in errors))

    def test_hardcoded_secrets_detection(self):
        data = {
            "nodes": [
                {
                    "name": "Slack Alert",
                    "type": "n8n-nodes-base.httpRequest",
                    "parameters": {
                        "url": "https://hooks.slack.com/services/T00/B00/abcdef12345678901234",
                        "password": "my-secret-token-long-enough-to-be-flagged",
                        "nested": {
                            "secret": "another-long-secret-key-high-entropy"
                        }
                    }
                }
            ],
            "settings": {
                "errorWorkflow": "some-id"
            }
        }
        filepath = self.create_temp_workflow("hardcoded_secrets", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertTrue(any("Suspected hardcoded credential" in e for e in errors))
        self.assertTrue(any("parameter 'password'" in e or "parameter 'nested.secret'" in e for e in errors))

    def test_disabled_node_warning(self):
        data = {
            "nodes": [
                {
                    "name": "Disabled Node",
                    "type": "n8n-nodes-base.set",
                    "disabled": True
                }
            ],
            "settings": {
                "errorWorkflow": "some-id"
            }
        }
        filepath = self.create_temp_workflow("disabled_node", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertEqual(len(errors), 0)
        self.assertTrue(any("Node 'Disabled Node' is disabled" in w for w in warnings))

    def test_webhook_no_auth_warning(self):
        data = {
            "nodes": [
                {
                    "name": "Public Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {
                        "authentication": "none"
                    }
                }
            ],
            "settings": {
                "errorWorkflow": "some-id"
            }
        }
        filepath = self.create_temp_workflow("webhook_no_auth", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertEqual(len(errors), 0)
        self.assertTrue(any("Public Webhook' does not configure authentication" in w for w in warnings))

    def test_orphaned_connections_detection(self):
        data = {
            "nodes": [
                {
                    "name": "Node A",
                    "type": "n8n-nodes-base.start"
                }
            ],
            "connections": {
                "Node A": {
                    "main": [
                        [
                            {
                                "node": "NonExistent Node",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                },
                "Node B": {
                    "main": [
                        [
                            {
                                "node": "Node A",
                                "type": "main",
                                "index": 0
                            }
                        ]
                    ]
                }
            },
            "settings": {
                "errorWorkflow": "some-id"
            }
        }
        filepath = self.create_temp_workflow("invalid_connections", data)
        errors, warnings = lint_workflows.check_workflow_file(filepath)
        self.assertTrue(any("references target node 'NonExistent Node'" in e for e in errors))
        self.assertTrue(any("source node 'Node B' that does not exist" in e for e in errors))

if __name__ == "__main__":
    unittest.main()

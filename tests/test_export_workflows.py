import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import tempfile
import json

# Add scripts directory to path to import export_workflows
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import export_workflows

class TestExportWorkflows(unittest.TestCase):
    def setUp(self):
        self.api_url = "https://n8n.test.com"
        self.headers = {"X-N8N-API-KEY": "test-key", "Content-Type": "application/json"}
        self.test_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.test_dir.cleanup()

    def test_sanitize_filename(self):
        self.assertEqual(export_workflows.sanitize_filename("Lead Generation & CRM Sync"), "lead_generation_crm_sync")
        self.assertEqual(export_workflows.sanitize_filename("Test / Workflow: #123!"), "test_workflow_123")
        self.assertEqual(export_workflows.sanitize_filename("  Simple Name  "), "simple_name")

    @patch('urllib.request.urlopen')
    def test_fetch_all_workflows_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "data": [
                {"id": "1", "name": "WF 1", "active": True},
                {"id": "2", "name": "WF 2", "active": False}
            ]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        results = export_workflows.fetch_all_workflows(self.api_url, self.headers)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["name"], "WF 1")

    @patch('urllib.request.urlopen')
    def test_fetch_all_workflows_error(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Connection refused")
        results = export_workflows.fetch_all_workflows(self.api_url, self.headers)
        self.assertEqual(results, [])

    @patch('export_workflows.fetch_all_workflows')
    def test_export_workflows_all(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": "wf-1", "name": "Workflow One", "nodes": [{"name": "Start"}], "active": True},
            {"id": "wf-2", "name": "Workflow Two", "nodes": [{"name": "End"}], "active": False}
        ]

        count = export_workflows.export_workflows(self.api_url, self.headers, self.test_dir.name, active_only=False)
        self.assertEqual(count, 2)

        file1 = os.path.join(self.test_dir.name, "workflow_one.json")
        self.assertTrue(os.path.exists(file1))
        with open(file1, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data["name"], "Workflow One")
        self.assertEqual(data["id"], "wf-1")

    @patch('export_workflows.fetch_all_workflows')
    def test_export_workflows_active_only(self, mock_fetch):
        mock_fetch.return_value = [
            {"id": "wf-1", "name": "Active WF", "nodes": [], "active": True},
            {"id": "wf-2", "name": "Inactive WF", "nodes": [], "active": False}
        ]

        count = export_workflows.export_workflows(self.api_url, self.headers, self.test_dir.name, active_only=True)
        self.assertEqual(count, 1)

        active_file = os.path.join(self.test_dir.name, "active_wf.json")
        inactive_file = os.path.join(self.test_dir.name, "inactive_wf.json")
        self.assertTrue(os.path.exists(active_file))
        self.assertFalse(os.path.exists(inactive_file))

if __name__ == "__main__":
    unittest.main()

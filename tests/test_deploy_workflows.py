import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import sys
import urllib.error
import io

# Add scripts directory to path to import deploy_workflows
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts')))
import deploy_workflows

class TestDeployWorkflows(unittest.TestCase):
    def setUp(self):
        self.api_url = "https://n8n.test.com"
        self.headers = {"X-N8N-API-KEY": "test-key", "Content-Type": "application/json"}

    @patch('os.environ.get')
    def test_get_api_credentials(self, mock_env_get):
        mock_env_get.side_effect = lambda k: "val_key" if k == "KEY" else "val_url" if k == "URL" else None
        key, url = deploy_workflows.get_api_credentials("KEY", "URL")
        self.assertEqual(key, "val_key")
        self.assertEqual(url, "val_url")

    @patch('urllib.request.urlopen')
    def test_check_workflow_exists_true(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        exists = deploy_workflows.check_workflow_exists(self.api_url, self.headers, "wf-123")
        self.assertTrue(exists)
        mock_urlopen.assert_called_once()
        self.assertIn("workflows/wf-123", mock_urlopen.call_args[0][0].full_url)

    @patch('urllib.request.urlopen')
    def test_check_workflow_exists_false_on_404(self, mock_urlopen):
        # HTTPError requires fp, code, msg, hdrs, and filename/file-like object
        http_error = urllib.error.HTTPError(
            url="https://n8n.test.com/workflows/wf-123",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"")
        )
        mock_urlopen.side_effect = http_error

        exists = deploy_workflows.check_workflow_exists(self.api_url, self.headers, "wf-123")
        self.assertFalse(exists)

    @patch('urllib.request.urlopen')
    def test_check_workflow_exists_error_other(self, mock_urlopen):
        http_error = urllib.error.HTTPError(
            url="https://n8n.test.com/workflows/wf-123",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b"")
        )
        mock_urlopen.side_effect = http_error

        exists = deploy_workflows.check_workflow_exists(self.api_url, self.headers, "wf-123")
        self.assertFalse(exists)

    @patch('deploy_workflows.check_workflow_exists')
    @patch('urllib.request.urlopen')
    def test_deploy_workflow_new_without_id(self, mock_urlopen, mock_check_exists):
        # Workflow JSON without an ID
        workflow_json = '{"name": "New Workflow", "nodes": [], "connections": {}}'
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "new-wf-999", "name": "New Workflow"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch('builtins.open', mock_open(read_data=workflow_json)):
            success = deploy_workflows.deploy_workflow(self.api_url, self.headers, "dummy_path.json")
            
        self.assertTrue(success)
        mock_check_exists.assert_not_called()
        
        # Verify POST request details
        req_arg = mock_urlopen.call_args[0][0]
        self.assertEqual(req_arg.method, "POST")
        self.assertEqual(req_arg.full_url, "https://n8n.test.com/workflows")

    @patch('deploy_workflows.check_workflow_exists')
    @patch('urllib.request.urlopen')
    def test_deploy_workflow_update_existing(self, mock_urlopen, mock_check_exists):
        # Workflow JSON with an ID
        workflow_json = '{"id": "wf-existing-111", "name": "Existing Workflow", "nodes": [], "connections": {}}'
        
        mock_check_exists.return_value = True
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "wf-existing-111", "name": "Existing Workflow"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch('builtins.open', mock_open(read_data=workflow_json)):
            success = deploy_workflows.deploy_workflow(self.api_url, self.headers, "dummy_path.json")
            
        self.assertTrue(success)
        mock_check_exists.assert_called_once_with(self.api_url, self.headers, "wf-existing-111")
        
        # Verify PUT request details
        req_arg = mock_urlopen.call_args[0][0]
        self.assertEqual(req_arg.method, "PUT")
        self.assertEqual(req_arg.full_url, "https://n8n.test.com/workflows/wf-existing-111")

    @patch('deploy_workflows.check_workflow_exists')
    @patch('urllib.request.urlopen')
    def test_deploy_workflow_new_with_unregistered_id(self, mock_urlopen, mock_check_exists):
        # Workflow has an ID but is not on the target n8n instance
        workflow_json = '{"id": "wf-new-222", "name": "New Workflow with ID", "nodes": [], "connections": {}}'
        
        mock_check_exists.return_value = False
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "wf-new-222", "name": "New Workflow with ID"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch('builtins.open', mock_open(read_data=workflow_json)):
            success = deploy_workflows.deploy_workflow(self.api_url, self.headers, "dummy_path.json")
            
        self.assertTrue(success)
        mock_check_exists.assert_called_once_with(self.api_url, self.headers, "wf-new-222")
        
        # Verify POST request details (it should POST to workflows/ to register the new ID)
        req_arg = mock_urlopen.call_args[0][0]
        self.assertEqual(req_arg.method, "POST")
        self.assertEqual(req_arg.full_url, "https://n8n.test.com/workflows")

    @patch('deploy_workflows.check_workflow_exists')
    @patch('urllib.request.urlopen')
    def test_deploy_workflow_dry_run_existing(self, mock_urlopen, mock_check_exists):
        workflow_json = '{"id": "wf-123", "name": "Existing Dry Run", "nodes": []}'
        mock_check_exists.return_value = True

        with patch('builtins.open', mock_open(read_data=workflow_json)):
            success = deploy_workflows.deploy_workflow(self.api_url, self.headers, "path.json", dry_run=True)

        self.assertTrue(success)
        mock_urlopen.assert_not_called()

    @patch('deploy_workflows.check_workflow_exists')
    @patch('urllib.request.urlopen')
    def test_deploy_workflow_dry_run_new(self, mock_urlopen, mock_check_exists):
        workflow_json = '{"name": "New Dry Run", "nodes": []}'

        with patch('builtins.open', mock_open(read_data=workflow_json)):
            success = deploy_workflows.deploy_workflow(self.api_url, self.headers, "path.json", dry_run=True)

        self.assertTrue(success)
        mock_urlopen.assert_not_called()

    @patch('urllib.request.urlopen')
    def test_backup_remote_workflow(self, mock_urlopen):
        import tempfile
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "wf-backup", "name": "Backup WF"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_file = deploy_workflows.backup_remote_workflow(self.api_url, self.headers, "wf-backup", tmpdir)
            self.assertIsNotNone(backup_file)
            self.assertTrue(os.path.exists(backup_file))
            with open(backup_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Backup WF", content)

    @patch('time.sleep')
    @patch('urllib.request.urlopen')
    def test_make_request_retry_on_503(self, mock_urlopen, mock_sleep):
        err_503 = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, io.BytesIO(b""))
        ok_resp = MagicMock()
        ok_resp.status = 200
        mock_urlopen.side_effect = [err_503, ok_resp]

        req = urllib.request.Request("https://test.com")
        resp = deploy_workflows.make_request(req, max_retries=2, backoff_factor=0.01)
        self.assertEqual(resp.status, 200)
        self.assertEqual(mock_urlopen.call_count, 2)
        mock_sleep.assert_called_once()

    def test_get_git_commit_sha(self):
        sha = deploy_workflows.get_git_commit_sha()
        # In this git repo, sha should be a non-empty string of hex characters
        self.assertIsNotNone(sha)
        self.assertTrue(len(sha) >= 4)

if __name__ == "__main__":
    unittest.main()

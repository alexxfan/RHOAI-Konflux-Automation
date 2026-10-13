import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from controller.quay_controller import quay_controller


NOT_FOUND = {'detail': 'Not Found', 'error_type': 'not_found', 'status': 404}


def _resp(payload):
    r = MagicMock()
    r.json.return_value = payload
    return r


class TestManifestDetails404:
    """Cross-tenant synced images (llama-stack, vLLM) 404 on the per-repo manifest
    endpoint. fail_on_error=False must return None instead of sys.exit(1)."""

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_manifest_404_non_fatal_returns_none(self, mock_get):
        mock_get.return_value = _resp(NOT_FOUND)
        qc = quay_controller('rhoai')
        assert qc.get_manifest_details('odh-llama-stack-core-rhel9', 'sha256:deadbeef', fail_on_error=False) is None

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_manifest_404_fatal_by_default(self, mock_get):
        mock_get.return_value = _resp(NOT_FOUND)
        qc = quay_controller('rhoai')
        with pytest.raises(SystemExit):
            qc.get_manifest_details('odh-llama-stack-core-rhel9', 'sha256:deadbeef')

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_manifest_ok_returns_payload(self, mock_get):
        payload = {'manifest_data': '{}', 'is_manifest_list': False}
        mock_get.return_value = _resp(payload)
        qc = quay_controller('rhoai')
        assert qc.get_manifest_details('odh-dashboard-rhel9', 'sha256:abc', fail_on_error=False) == payload


class TestGitLabels404:
    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_labels_404_non_fatal_returns_none(self, mock_get):
        mock_get.return_value = _resp(NOT_FOUND)
        qc = quay_controller('rhoai')
        assert qc.get_git_labels('odh-llama-stack-core-rhel9', 'sha256:deadbeef', fail_on_error=False) is None

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_labels_404_fatal_by_default(self, mock_get):
        mock_get.return_value = _resp(NOT_FOUND)
        qc = quay_controller('rhoai')
        with pytest.raises(SystemExit):
            qc.get_git_labels('odh-llama-stack-core-rhel9', 'sha256:deadbeef')


class TestGetTagDetails:
    """An error response (repo not found, cross-tenant repo, auth) carries no
    'tags' key. get_tag_details must return {} instead of raising KeyError."""

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_error_payload_returns_empty(self, mock_get):
        mock_get.return_value = _resp(NOT_FOUND)
        qc = quay_controller('rhoai')
        assert qc.get_tag_details('odh-llm-d-batch-gateway-apiserver', 'rhoai-3.4') == {}

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_empty_tags_returns_empty(self, mock_get):
        mock_get.return_value = _resp({'tags': []})
        qc = quay_controller('rhoai')
        assert qc.get_tag_details('odh-dashboard-rhel9', 'rhoai-3.4') == {}

    @patch.dict(os.environ, {'RHOAI_QUAY_API_TOKEN': 'tok'})
    @patch('controller.quay_controller.requests.get')
    def test_tag_present_returns_first(self, mock_get):
        tag = {'name': 'rhoai-3.4', 'manifest_digest': 'sha256:' + 'a' * 64}
        mock_get.return_value = _resp({'tags': [tag]})
        qc = quay_controller('rhoai')
        assert qc.get_tag_details('odh-dashboard-rhel9', 'rhoai-3.4') == tag


class TestTokenEnvVar:
    def test_simple_org(self):
        qc = quay_controller('opendatahub')
        assert qc._token_env_var() == 'OPENDATAHUB_QUAY_API_TOKEN'

    def test_hyphenated_org(self):
        qc = quay_controller('rhoai-private')
        assert qc._token_env_var() == 'RHOAI_PRIVATE_QUAY_API_TOKEN'

    def test_multiple_hyphens(self):
        qc = quay_controller('my-org-name')
        assert qc._token_env_var() == 'MY_ORG_NAME_QUAY_API_TOKEN'

    def test_dot_in_org(self):
        qc = quay_controller('org.name')
        assert qc._token_env_var() == 'ORG_NAME_QUAY_API_TOKEN'

    def test_already_valid(self):
        qc = quay_controller('myorg')
        assert qc._token_env_var() == 'MYORG_QUAY_API_TOKEN'

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.util import classify_unresolvable_image

GOOD = 'sha256:' + 'a' * 64
OTHER = 'sha256:' + 'b' * 64


def _parsed(digest, repo='odh-vllm-cpu-rhel9', org='rhoai'):
    return {'org': org, 'repo': repo, 'component_name': repo.replace('-rhel9', ''), 'digest': digest}


class TestMalformedDigest:
    def test_missing_sha256_prefix(self):
        qc = MagicMock()
        msg = classify_unresolvable_image(qc, _parsed('a' * 64), 'rhoai-3.4')
        assert 'malformed digest' in msg
        qc.get_tag_details.assert_not_called()  # no API call needed

    def test_double_sha256_prefix(self):
        qc = MagicMock()
        msg = classify_unresolvable_image(qc, _parsed('sha256:sha256:' + 'c' * 64), 'rhoai-3.4')
        assert 'malformed digest' in msg
        qc.get_tag_details.assert_not_called()


class TestWellFormedDigest:
    def test_no_version_generic_message(self):
        qc = MagicMock()
        msg = classify_unresolvable_image(qc, _parsed(GOOD), rhoai_version=None)
        assert 'cross-tenant' in msg
        qc.get_tag_details.assert_not_called()

    def test_no_tag_means_unpublished(self):
        qc = MagicMock()
        qc.get_tag_details.return_value = {}
        msg = classify_unresolvable_image(qc, _parsed(GOOD), 'rhoai-3.4')
        assert 'not published for this release' in msg

    def test_same_digest_is_cross_tenant(self):
        qc = MagicMock()
        qc.get_tag_details.return_value = {'manifest_digest': GOOD}
        msg = classify_unresolvable_image(qc, _parsed(GOOD), 'rhoai-3.4')
        assert 'cross-tenant/synced image' in msg

    def test_different_digest_is_stale(self):
        qc = MagicMock()
        qc.get_tag_details.return_value = {'manifest_digest': OTHER}
        msg = classify_unresolvable_image(qc, _parsed(GOOD), 'rhoai-3.4')
        assert 'stale digest' in msg
        assert OTHER in msg

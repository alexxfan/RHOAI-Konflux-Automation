"""Offline regression tests for private operator metadata and empty-map failures."""
import importlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import util

BundleProcessor = importlib.import_module('bundle-processor').bundle_processor
DIGEST = 'sha256:' + 'a' * 64
IMAGE = 'quay.io/rhoai/odh-rhel9-operator@' + DIGEST
ENTRY = [{'name': 'RELATED_IMAGE_ODH_OPERATOR_IMAGE', 'value': IMAGE}]
LABELS = {'git.url': 'https://github.com/red-hat-data-services/rhods-operator', 'git.commit': 'c' * 40}


def inspection(labels=None, digest=DIGEST):
    return subprocess.CompletedProcess([], 0, json.dumps({'Digest': digest, 'Labels': LABELS if labels is None else labels}), '')


def test_registry_auth_avoids_quay_management_api_and_preserves_digest(tmp_path):
    auth = tmp_path / 'auth.json'
    auth.write_text('{}')
    with patch.object(util.subprocess, 'run', return_value=inspection()) as inspect, patch.object(util, 'quay_controller') as api:
        result = util.fetch_git_metadata_for_existing_digests(ENTRY, registry_auth_file=str(auth))
    api.assert_not_called()
    assert list(result['map'].values()) == [LABELS]
    assert not result['skipped']
    args = inspect.call_args.args[0]
    assert args[-1] == 'docker://' + IMAGE
    assert args[args.index('--authfile') + 1] == str(auth)
    assert '--creds' not in args
    assert inspect.call_args.kwargs['timeout'] == 120
    assert ENTRY[0]['value'] == IMAGE


@pytest.mark.parametrize('metadata', [inspection(labels={}), inspection(labels={'git.url': 'url'}), inspection(digest='sha256:' + 'b' * 64)])
def test_registry_missing_labels_or_wrong_digest_are_not_accepted(metadata):
    with patch.object(util.subprocess, 'run', return_value=metadata), patch.object(util, 'quay_controller') as api:
        result = util.fetch_git_metadata_for_existing_digests(ENTRY, registry_auth_file='auth.json')
    assert result['map'] == {}
    assert result['skipped']
    api.assert_not_called()


@pytest.mark.parametrize('error', [FileNotFoundError(), subprocess.TimeoutExpired('skopeo', 120), subprocess.CalledProcessError(1, 'skopeo', stderr='DO_NOT_LOG_TEST_CREDENTIAL')])
def test_registry_errors_do_not_leak_credentials_or_fall_back_to_api(error, caplog):
    with patch.object(util.subprocess, 'run', side_effect=error), patch.object(util, 'quay_controller') as api:
        result = util.fetch_git_metadata_for_existing_digests(ENTRY, registry_auth_file='auth.json')
    assert result['map'] == {}
    assert result['skipped']
    assert 'DO_NOT_LOG_TEST_CREDENTIAL' not in caplog.text
    api.assert_not_called()


def test_malformed_registry_metadata_is_skipped():
    response = subprocess.CompletedProcess([], 0, 'not JSON', '')
    with patch.object(util.subprocess, 'run', return_value=response):
        assert util.fetch_git_metadata_for_existing_digests(ENTRY, registry_auth_file='auth.json')['skipped']


def test_existing_api_callers_are_unchanged():
    api = MagicMock()
    api.get_manifest_details.return_value = {}
    api.get_git_labels.return_value = [{'key': k, 'value': v} for k,v in LABELS.items()]
    with patch.object(util, 'quay_controller', return_value=api), patch.object(util.subprocess, 'run') as inspect:
        result = util.fetch_git_metadata_for_existing_digests(ENTRY)
    inspect.assert_not_called()
    assert list(result['map'].values()) == [LABELS]
    api.get_manifest_details.assert_called_once()


@pytest.mark.parametrize('metadata', [{'map': {}, 'skipped': {'odh-operator': '401'}}, {'map': {'operator': {'git.url': 'url', 'git.commit': ''}}}])
def test_required_operator_metadata_fails_with_clear_error_instead_of_indexerror(metadata):
    processor = BundleProcessor.__new__(BundleProcessor)
    processor.fetch_operator_metadata = MagicMock(return_value=(ENTRY, metadata))
    with pytest.raises(ValueError, match='Cannot read required operator git metadata'):
        processor.process()


def test_existing_digest_mode_passes_registry_auth_to_lookup():
    processor = BundleProcessor.__new__(BundleProcessor)
    processor.use_existing_digests = True
    processor.registry_auth_file = 'auth.json'
    processor.patch_dict = {'patch': {'relatedImages': ENTRY}}
    with patch.object(util, 'fetch_git_metadata_for_existing_digests', return_value={'map': {'operator': LABELS}}) as lookup:
        processor.fetch_operator_metadata()
    lookup.assert_called_once_with(ENTRY, registry_auth_file='auth.json')


def test_full_bundle_processing_with_private_registry_metadata(tmp_path):
    import shutil
    import yaml
    fixtures = Path(__file__).parent / 'fixtures/bundle-processor'
    shutil.copytree(fixtures, tmp_path / 'input')
    root = tmp_path / 'input'
    patch_file = root / 'bundle/bundle-patch.yaml'
    data = yaml.safe_load(patch_file.read_text())
    data['patch']['relatedImages'][0]['value'] = IMAGE
    patch_file.write_text(yaml.safe_dump(data))
    output = tmp_path / 'output.csv.yaml'
    processor = BundleProcessor(
        build_config_path=str(root / 'config/build-config.yaml'),
        bundle_csv_path=str(root / 'bundle/manifests/rhods-operator.clusterserviceversion.yaml'),
        patch_yaml_path=str(patch_file), rhoai_version='eg-test',
        output_file_path=str(output), annotation_yaml_path=str(root / 'bundle/metadata/annotations.yaml'),
        push_pipeline_operation='enable', push_pipeline_yaml_path=str(root / 'tekton/push-pipeline.yaml'),
        build_type='ci', use_existing_digests=True, registry_auth_file='auth.json')
    with patch.object(util.subprocess, 'run', return_value=inspection()), patch.object(util, 'quay_controller') as api, patch.object(processor, 'fetch_operands_map_and_manifest_config', return_value=({'relatedImages': []}, {'map': {}, 'additional_meta': {}})):
        processor.process()
    api.assert_not_called()
    csv = yaml.safe_load(output.read_text())
    assert csv['metadata']['annotations']['containerImage'].endswith('@' + DIGEST)
    args = (root / 'bundle/bundle_build_args.map').read_text()
    assert LABELS['git.commit'] in args
    assert LABELS['git.url'] in args

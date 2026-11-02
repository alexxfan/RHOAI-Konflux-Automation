"""Regression tests for EG snapshot-to-operands-map image selection."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.util import fetch_images_and_git_metadata_from_snapshot

COMPONENT = "odh-llm-d-kv-pvc-evictor"
PR_IMAGE = "quay.io/rhoai/pull-request-pipelines@sha256:4780fa95bb351866df1a0840be58f8cc751beda6c3945a1b4dad0d6005c50252"
RELEASE_IMAGE = "quay.io/rhoai/odh-llm-d-kv-pvc-evictor-rhel9@sha256:80760d9fc13a72107b078629432e3ab05ebbfad52435ffa95f3d2c05a27b41bc"


def operand(component=COMPONENT):
    return {
        "name": "RELATED_IMAGE_" + component.upper().replace("-", "_") + "_IMAGE",
        "value": RELEASE_IMAGE if component == COMPONENT else f"quay.io/rhoai/{component}-rhel9@sha256:" + "a" * 64,
    }


def metadata(image=PR_IMAGE):
    return {
        "image": image,
        "git.url": "https://github.com/red-hat-data-services/llm-d-kv-cache",
        "git.commit": "fb80f035daf5408b7be78adaca31cc963a9b770c",
        "image_tag": COMPONENT + "-fb80f035daf5408b7be78adaca31cc963a9b770c",
    }


@pytest.mark.parametrize("suffix", ["", "-v3-6", "-v3-7-ea-1", "-v4-0"])
def test_shared_pr_image_reaches_operator_operands_map(suffix):
    # The historical snapshot and release operand from operator commit 8e0faf03.
    entries = [operand()]
    snapshot = {COMPONENT + suffix: metadata()}
    original = copy.deepcopy((entries, snapshot))
    resolved, git_meta, unresolved = fetch_images_and_git_metadata_from_snapshot(entries, snapshot)
    assert unresolved == []
    assert resolved[0]["value"] == PR_IMAGE
    assert git_meta["map"][COMPONENT] == {
        "git.url": snapshot[COMPONENT + suffix]["git.url"],
        "git.commit": snapshot[COMPONENT + suffix]["git.commit"],
    }
    assert (entries, snapshot) == original

    # Exercise the real operator merge, not just the helper return value.
    path = Path(__file__).resolve().parents[1] / "operator-processor.py"
    spec = importlib.util.spec_from_file_location("snapshot_test_operator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    processor = module.operator_processor.__new__(module.operator_processor)
    processor.operands_map_dict = {"relatedImages": entries}
    processor.latest_images = resolved
    processor.update_operands_map()
    assert processor.operands_map_dict["relatedImages"][0]["value"] == PR_IMAGE


def test_shared_repository_components_do_not_overwrite_each_other():
    other = "odh-dashboard"
    other_image = "quay.io/rhoai/pull-request-pipelines@sha256:" + "b" * 64
    snapshot = {COMPONENT + "-v3-6": metadata(), other + "-v3-6": metadata(other_image)}
    resolved, _, unresolved = fetch_images_and_git_metadata_from_snapshot(
        [operand(), operand(other)], snapshot)
    assert unresolved == []
    assert [entry["value"] for entry in resolved] == [PR_IMAGE, other_image]


@pytest.mark.parametrize("image", [RELEASE_IMAGE, "quay.io/rhoai/odh-llm-d-kv-pvc-evictor-rhel9@sha256:" + "c" * 64])
def test_component_repository_pr_and_release_images_still_resolve(image):
    resolved, _, unresolved = fetch_images_and_git_metadata_from_snapshot(
        [operand()], {COMPONENT + "-v3-6": metadata(image)})
    assert unresolved == []
    assert resolved[0]["value"] == image


def test_repository_alias_matching_is_preserved():
    resolved, _, unresolved = fetch_images_and_git_metadata_from_snapshot(
        [operand()], {"different-component-alias-v3-6": metadata(RELEASE_IMAGE)})
    assert unresolved == []
    assert resolved[0]["value"] == RELEASE_IMAGE


def test_component_identity_takes_precedence_over_repository_alias():
    resolved, _, unresolved = fetch_images_and_git_metadata_from_snapshot(
        [operand()], {COMPONENT + "-v3-6": metadata(), "alias": metadata(RELEASE_IMAGE)})
    assert unresolved == []
    assert resolved[0]["value"] == PR_IMAGE


def test_absent_components_and_excluded_artifacts_still_fall_back():
    entry = operand()
    assert fetch_images_and_git_metadata_from_snapshot([entry], {})[2] == [entry]
    resolved, _, unresolved = fetch_images_and_git_metadata_from_snapshot(
        [entry], {COMPONENT: metadata()}, exclude_filter=["EVICTOR"])
    assert resolved == []
    assert unresolved == [entry]


@pytest.mark.parametrize("snapshot", [
    {COMPONENT + "-v3-6": metadata(), COMPONENT + "-v3-7": metadata(RELEASE_IMAGE)},
    {"alias-a": metadata(RELEASE_IMAGE), "alias-b": metadata(RELEASE_IMAGE)},
])
def test_ambiguous_component_or_repository_matches_fail(snapshot):
    with pytest.raises(ValueError, match="Ambiguous snapshot images"):
        fetch_images_and_git_metadata_from_snapshot([operand()], snapshot)

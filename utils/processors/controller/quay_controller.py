import os
import re
import requests
import json
import sys
from logger.logger import getLogger

LOGGER = getLogger('processor')
BASE_URL = 'https://quay.io/api/v1'

class quay_controller:
    def __init__(self, org:str):
        self.org = org

    def _token_env_var(self):
        normalized = re.sub(r'[^A-Za-z0-9]', '_', self.org).upper()
        return normalized + '_QUAY_API_TOKEN'

    def get_tag_details(self, repo, tag):
        result_tag = {}
        url = f'{BASE_URL}/repository/{self.org}/{repo}/tag/?specificTag={tag}&onlyActiveTags=true'
        headers = {'Authorization': f'Bearer {os.environ[self._token_env_var()]}',
                   'Accept': 'application/json'}
        response = requests.get(url, headers=headers)
        payload = response.json()
        # Error responses (repo not found, cross-tenant repo, auth) carry no
        # 'tags' key — treat as "no such tag" rather than raising KeyError.
        tags = payload.get('tags') if isinstance(payload, dict) else None
        if tags:
            result_tag = tags[0]
        return result_tag

    def get_all_tags(self, repo, tag):
        url = f'{BASE_URL}/repository/{self.org}/{repo}/tag/?specificTag={tag}&onlyActiveTags=false'
        headers = {'Authorization': f'Bearer {os.environ[self._token_env_var()]}',
                   'Accept': 'application/json'}
        response = requests.get(url, headers=headers)
        if 'tags' in response.json():
            tag = response.json()['tags']
            return tag
        else:
            LOGGER.error(f'Failed to get tags: {response.json()}')
            sys.exit(1)

    def get_supported_archs(self, repo, manifest_digest):
        manifest_json = self.get_manifest_details(repo, manifest_digest)
        supported_archs = []
        if manifest_json['is_manifest_list']:
            manifest_data = manifest_json['manifest_data']
            manifest_data = json.loads(manifest_data)
            for manifest in manifest_data['manifests']:
                supported_archs.append(f'{manifest["platform"]["os"]}-{manifest["platform"]["architecture"]}')
        return supported_archs

    def get_image_manifest_digests_for_all_the_supported_archs(self, repo, manifest_digest):
        manifest_json = self.get_manifest_details(repo, manifest_digest)
        image_manifest_digests = []
        if manifest_json['is_manifest_list']:
            manifest_data = manifest_json['manifest_data']
            manifest_data = json.loads(manifest_data)
            for manifest in manifest_data['manifests']:
                image_manifest_digests.append(manifest['digest'])
        return image_manifest_digests

    def get_manifest_details(self, repo, manifest_digest, fail_on_error=True):
        url = f'{BASE_URL}/repository/{self.org}/{repo}/manifest/{manifest_digest}'
        headers = {'Authorization': f'Bearer {os.environ[self._token_env_var()]}',
                   'Accept': 'application/json'}
        response = requests.get(url, headers=headers)

        if 'manifest_data' in response.json():
            return response.json()
        # Cross-tenant synced images (e.g. AIPCC llama-stack, RHAII vLLM) carry a
        # valid tag in quay.io/rhoai but their per-repo manifest endpoint can 404.
        # Callers that can tolerate a missing manifest pass fail_on_error=False and
        # handle the None return themselves.
        if not fail_on_error:
            LOGGER.warning(f'Manifest not resolvable for {self.org}/{repo}@{manifest_digest}: {response.json()}')
            return None
        LOGGER.error(f'Failed to get manifest details: {response.json()}')
        sys.exit(1)

    def get_git_labels(self, repo, tag, fail_on_error=True):
        url = f'{BASE_URL}/repository/{self.org}/{repo}/manifest/{tag}/labels'
        # ?filter=git, throwing 403 forbidden, due to this need to check, seems quay issue, disabling the fitler for now
        headers = {'Authorization': f'Bearer {os.environ[self._token_env_var()]}',
                   'Accept': 'application/json'}
        response = requests.get(url, headers=headers)
        if 'labels' in response.json():
            labels = response.json()['labels']
            return labels
        if not fail_on_error:
            LOGGER.warning(f'Labels not resolvable for {self.org}/{repo}@{tag}: {response.json()}')
            return None
        LOGGER.error(f'Failed to get git labels: {response.json()}')
        sys.exit(1)

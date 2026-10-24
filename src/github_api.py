"""Shared GitHub REST transport."""
import json
import urllib.request

def github_json(path, token=None):
    headers = {'User-Agent': 'LXTool', 'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request('https://api.github.com' + path, headers=headers), timeout=60) as response:
        return json.load(response)



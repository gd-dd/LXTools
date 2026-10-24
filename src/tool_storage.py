"""Readable repository folders with stable identity and atomic migration."""
import os
from pathlib import Path
from lx_protocol import safe_path, discover_packages


def repository_folder(root, entry):
    root = Path(root).resolve()
    identity = entry['id']
    number = str(entry['repositoryId'])
    if identity != 'repo-' + number or not number.isdigit():
        raise ValueError('仓库身份无效')
    matches = [p for p in root.glob('*--' + number) if p.is_dir()]
    if len(matches) > 1:
        raise ValueError('同一仓库存在多个安装目录，请检查后合并')
    name = entry['repository'].split('/')[-1]
    safe_path(name)
    if '/' in name:
        raise ValueError('仓库名无效')
    target = matches[0] if matches else root / (name + '--' + number)
    if not target.resolve().is_relative_to(root):
        raise ValueError('工具目录越界')
    return target


def migrate_repository(root, entry):
    """Move intact old v2 versions; never overwrite tool payloads."""
    root = Path(root).resolve()
    target = repository_folder(root, entry)
    old = root / entry['id']
    if not old.exists():
        return target
    if not old.resolve().is_relative_to(root):
        raise ValueError('旧目录越界')
    tools, errors = discover_packages(root)
    versions = [t for t in tools if t['root'].parent == old]
    if errors or not versions or len(versions) != len(list(old.iterdir())):
        raise ValueError('旧安装目录存在未识别或损坏文件，保留原目录')
    if target.exists():
        raise ValueError('新旧仓库目录同时存在，未自动覆盖')
    target.mkdir(parents=True)
    try:
        os.replace(old, target / 'versions')
    except Exception:
        target.rmdir()
        raise
    return target

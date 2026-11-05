"""Explicit, bounded storage cleanup; never traverse junctions or symbolic links."""
import os,shutil,stat
from pathlib import Path

def checked(path,boundary):
    path=Path(path).absolute();boundary=Path(boundary).resolve()
    if path==boundary or not path.resolve().is_relative_to(boundary):raise ValueError('清理路径越界')
    for item in [path]+list(path.parents):
        if item==boundary:break
        if item.exists() and item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('保留目录链接，不清理其内容')
    for root,dirs,files in os.walk(path,followlinks=False):
        for name in dirs+files:
            if (Path(root)/name).lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:raise ValueError('目录包含链接，已保留')
    return path

def size(path):
    return sum((Path(root)/name).stat().st_size for root,dirs,files in os.walk(path) for name in files)

def remove(path,boundary):
    path=checked(path,boundary)
    if path.is_dir():shutil.rmtree(path)
    elif path.exists():path.unlink()

def backups(app_root):
    parent=Path(app_root).resolve().parent
    log=Path(os.environ.get('LOCALAPPDATA',''))/'LXTool/update-result.txt'
    if not log.exists():return []
    text=log.read_text('utf-8')
    prefix='更新成功，旧版备份：'
    if not text.startswith(prefix):return []
    candidate=Path(text[len(prefix):].strip())
    if candidate.parent!=parent or not candidate.name.startswith('.lxtool-backup-'):return []
    if not (candidate/'LXTool.exe').is_file() or not (candidate/'_internal').is_dir():return []
    return [checked(candidate,parent)]

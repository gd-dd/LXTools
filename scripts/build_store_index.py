"""Author-only stable Release discovery. Run from repository root with Python -B."""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from repository_source import RepositoryCatalog,validate_index,MAX_INDEX
from library import write_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('catalog/repo-store.json'))
    args=parser.parse_args()
    data=RepositoryCatalog(Path('runtime/index-author')).scan_author(os.environ.get('GH_TOKEN'))
    if data.get('warnings'):raise SystemExit('Index not written; resolve scan warnings: '+json.dumps(data['warnings'],ensure_ascii=False))
    validate_index(data)
    if len(json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8'))>MAX_INDEX:raise SystemExit('Index exceeds client limit')
    write_json(args.output,data)
    print(f"Validated {len(data['packages'])} releases; wrote {args.output}")

if __name__=='__main__':main()

"""Keep the source client running across requested hot reloads."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    while True:
        result = subprocess.run([sys.executable, str(ROOT / 'src/desktop.py'), '--dev'], cwd=ROOT)
        if result.returncode != 75:
            if result.returncode:
                input('开发版启动失败。请查看上面的错误，按回车退出。')
            sys.exit(result.returncode)

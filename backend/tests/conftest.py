"""
pytest 配置 + 全局 fixtures
让 tests/ 能 import backend/ 父目录下的模块（rag.py / safety.py / engine.py 等）
"""
import sys
from pathlib import Path

# 把 backend/ 目录加进 sys.path，让 import safety / from rag import X 能 work
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

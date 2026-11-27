"""pytest 根配置：隔离本地运行配置，并使测试可导入 app 包。"""
import os
import sys
from pathlib import Path

# Tests use the deterministic legacy index instead of loading the production BGE
# model from a developer's .env file.
os.environ["TRAVELMATE_VECTOR_BACKEND"] = "json"
os.environ["TRAVELMATE_EMBEDDING_PROVIDER"] = "hash"
os.environ["TRAVELMATE_EMBEDDING_DIMENSION"] = "1024"
os.environ["TRAVELMATE_EMBEDDING_ALLOW_FALLBACK"] = "false"
os.environ["TRAVELMATE_INDEX_ROOT"] = ""
os.environ["TRAVELMATE_INDEX_VERSION"] = ""

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

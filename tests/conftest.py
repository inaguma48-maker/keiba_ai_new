"""
Test isolation: use a throwaway SQLite DB and model cache so tests never touch racing_app.db.
Must run before src.db / app are imported.
"""

import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="keiba_test_")
os.environ.setdefault("KEIBA_DB_PATH", os.path.join(_TMP_DIR, "test_racing_app.db"))
os.environ.setdefault("KEIBA_MODEL_PATH", os.path.join(_TMP_DIR, "test_model_cache.pkl"))

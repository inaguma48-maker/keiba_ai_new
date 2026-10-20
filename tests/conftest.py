import os
import tempfile

# The app creates/writes its SQLite file at import time; keep tests off the tracked racing_app.db.
os.environ.setdefault("KEIBA_APP_DB", os.path.join(tempfile.mkdtemp(prefix="keiba_test_"), "racing_app.db"))

"""Short hash of the files that make up the app (shows which copy is really running)."""

import hashlib
import os

FILES = ("app.py", "templates/index.html", "static/app.js", "static/replay.js", "static/sim.js", "static/curves.js",
         "static/trends.js", "src/replay.py", "src/jra_site.py", "src/horse_profiles.py", "src/db.py", "keiba/predict.py",
         "keiba/trends.py")


def code_version(root: str) -> str:
    h = hashlib.sha1()
    for rel in FILES:
        try:
            with open(os.path.join(root, rel), "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(rel.encode())
    return h.hexdigest()[:8]

import sys
from pathlib import Path

# webapp/backend/app/paths.py -> repo root is three levels up
ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "webapp" / "data" / "app.db"
FRONTEND_DIST = ROOT / "webapp" / "frontend" / "dist"

# forecast.py and util.py live at the repo root and are imported as plain modules. Every module
# in this package imports paths, so putting the root on the path here means no import order to
# get wrong. forecast.py resolves its own data files, so no chdir is needed.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

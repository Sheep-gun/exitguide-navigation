import json
from pathlib import Path

from app.resource_paths import get_resource_root
from app.schemas import SyntheticScreenCatalog


ROOT = get_resource_root()
MANIFEST_PATH = ROOT / "fixtures" / "synthetic-screens" / "manifest.json"
SYNTHETIC_SCREEN_DIR = MANIFEST_PATH.parent


def load_synthetic_screen_catalog() -> SyntheticScreenCatalog:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return SyntheticScreenCatalog.model_validate(payload)


def list_synthetic_screen_files() -> list[str]:
    return sorted(path.name for path in SYNTHETIC_SCREEN_DIR.glob("*.png"))

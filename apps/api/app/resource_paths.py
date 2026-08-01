import os
import sys
from pathlib import Path


def get_resource_root() -> Path:
    override = os.getenv("EXITGUIDE_RESOURCE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_root:
        return Path(bundle_root)

    return Path(__file__).resolve().parents[3]

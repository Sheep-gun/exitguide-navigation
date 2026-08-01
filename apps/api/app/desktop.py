from fastapi.staticfiles import StaticFiles

from app.main import app
from app.resource_paths import get_resource_root


WEB_ROOT = get_resource_root() / "apps" / "web-demo"

if not WEB_ROOT.exists():
    raise RuntimeError(f"ExitGuide web resources were not found: {WEB_ROOT}")

app.mount("/", StaticFiles(directory=str(WEB_ROOT), html=True), name="desktop-web")

"""Serve the compiled React app alongside the API in production."""
from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Missing API endpoints must remain JSON 404s, never React HTML.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # BrowserRouter routes need index.html; missing assets stay 404.
            if (
                exc.status_code == 404
                and scope["method"] in ("GET", "HEAD")
                and not Path(path).suffix
                and ".." not in Path(path).parts
            ):
                return await super().get_response("index.html", scope)
            raise


def mount_frontend(app: FastAPI, directory: Path | None = None):
    directory = directory if directory is not None else Path(__file__).resolve().parent.parent / "static"
    if directory.is_dir():
        # Register after API and health routes so those retain priority.
        app.mount("/", SPAStaticFiles(directory=directory, html=True), name="frontend")

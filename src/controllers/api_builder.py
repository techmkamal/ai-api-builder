# pylint: disable=import-error,no-name-in-module
"""FastAPI route for the AI API Builder — POST /api/build returns a generated project ZIP."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import cache
import db
from agents.api_builder_agent.graph import get_default_app

router = APIRouter(prefix="/api/build", tags=["api-builder"])

_app = get_default_app()


class BuildRequest(BaseModel):
    """Incoming build request — a plain-English API description."""

    request: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "request": (
                    "Create a Book Management API with JWT auth, CRUD Books and "
                    "CRUD Authors, PostgreSQL, Docker, and unit tests."
                )
            }
        }
    }


@router.post("")
def build(payload: BuildRequest) -> Response:
    """Generate a FastAPI project from a plain-English description and return it as a ZIP.

    Identical requests are served from the Redis cache when one is configured
    (marked with an X-Cache: hit header and not re-recorded in history). Every
    fresh run is recorded in the build history when a database is configured;
    caching and recording are best-effort and never block the build response.
    """
    cached = cache.get_cached_build(payload.request)
    if cached:
        project, zip_bytes = cached
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{project}.zip"',
                     "X-Cache": "hit"},
        )

    result = _app.invoke({"request": payload.request})

    if result.get("error"):
        db.record_build(request=payload.request, spec=result.get("spec"),
                        attempts=result.get("attempts", 1), status="failed",
                        error=result["error"])
        raise HTTPException(status_code=422, detail=result["error"])

    zip_bytes = result.get("zip_bytes")
    if not zip_bytes:
        raise HTTPException(status_code=500, detail="Project generation produced no output.")

    build_id = db.record_build(request=payload.request, spec=result.get("spec"),
                               attempts=result.get("attempts", 1), status="success",
                               zip_bytes=zip_bytes)

    project = result.get("spec", {}).get("project_name", "generated-api")
    cache.cache_build(payload.request, project, zip_bytes)
    headers = {"Content-Disposition": f'attachment; filename="{project}.zip"'}
    if build_id is not None:
        headers["X-Build-Id"] = str(build_id)
    return Response(content=zip_bytes, media_type="application/zip", headers=headers)

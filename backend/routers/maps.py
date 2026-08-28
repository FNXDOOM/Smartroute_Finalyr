import json
from copy import deepcopy
from urllib.parse import parse_qsl, urlencode, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from config import STADIA_TILES_URL
from models.user import User
from services.stadia_client import (
    fetch_stadia_resource,
    fetch_stadia_style,
)
from utils.auth_utils import get_current_user

router = APIRouter()
# Derived from config instead of hardcoded so a changed STADIA_TILES_URL
# (different region/CDN) doesn't silently stop being rewritten, which would
# otherwise leak the raw Stadia api_key straight to the browser.
STADIA_HOST = urlsplit(STADIA_TILES_URL).hostname
PROXY_PREFIX = "/maps/stadia/resource"


def _proxy_url(value: str, base_url: str) -> str:
    parsed = urlsplit(value)
    if parsed.hostname != STADIA_HOST:
        return value
    query = [(key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=True) if key != "api_key"]
    suffix = f"?{urlencode(query)}" if query else ""
    # MapLibre requires style fields like "sprite" to already be absolute -
    # it resolves them with `new URL()` and no base, so a bare path throws
    # "Invalid sprite URL ... must be absolute" and aborts the whole style.
    return f"{base_url.rstrip('/')}{PROXY_PREFIX}{parsed.path}{suffix}"


def _rewrite_style(value, base_url: str):
    if isinstance(value, str):
        return _proxy_url(value, base_url)
    if isinstance(value, list):
        return [_rewrite_style(item, base_url) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_style(item, base_url) for key, item in value.items()}
    return value


@router.get("/style.json")
def stadia_style(request: Request, _: User = Depends(get_current_user)):
    base_url = str(request.base_url).rstrip("/")
    try:
        style = _rewrite_style(deepcopy(fetch_stadia_style()), base_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return JSONResponse(content=style, headers={"Cache-Control": "private, max-age=300"})


@router.get("/resource/{resource_path:path}")
def stadia_resource(
    resource_path: str,
    request: Request,
    _: User = Depends(get_current_user),
):
    base_url = str(request.base_url).rstrip("/")
    try:
        content, content_type = fetch_stadia_resource(resource_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if content_type == "application/json" or resource_path.lower().endswith(".json"):
        try:
            content = json.dumps(
                _rewrite_style(json.loads(content.decode("utf-8")), base_url),
                separators=(",", ":"),
            ).encode("utf-8")
            content_type = "application/json"
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )

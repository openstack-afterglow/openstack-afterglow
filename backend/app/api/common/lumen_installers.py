from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Request, Response

_TEMPLATES = Path(__file__).resolve().parents[2] / "data"
_UNCONFIGURED = "Lumen CLI setup is unavailable: this deployment has no public Lumen URL."


def _render_installer(filename: str, base_url: str) -> bytes:
    if not base_url:
        if filename == "lumen.sh":
            return f"#!/bin/sh\nprintf '%s\\n' '{_UNCONFIGURED}' >&2\nexit 1\n".encode()
        return f"throw '{_UNCONFIGURED}'\n".encode()

    def literal(value: str) -> str:
        if filename == "lumen.sh":
            # Python source inside a single-quoted shell heredoc.
            return repr(value)
        return "'" + value.replace("'", "''") + "'"

    template = (_TEMPLATES / f"{filename}.template").read_text(encoding="utf-8")
    return (
        template.replace("__LUMEN_CODEX_URL_LITERAL__", literal(f"{base_url}/v1"), 1)
        .replace("__LUMEN_ANTHROPIC_URL_LITERAL__", literal(base_url), 1)
        .encode()
    )


def build_lumen_installer_router(base_url: str) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def installer(filename: str):
        body = _render_installer(filename, base_url)
        etag = f'"{sha256(body).hexdigest()}"'
        headers = {"Cache-Control": "no-cache", "ETag": etag}

        async def download(request: Request) -> Response:
            for field in request.headers.getlist("if-none-match"):
                if any(tag.strip().removeprefix("W/") in ("*", etag) for tag in field.split(",")):
                    return Response(status_code=304, headers=headers)
            return Response(body, media_type="text/plain", headers=headers)

        return download

    for filename in ("lumen.sh", "lumen.ps1"):
        # Public /install/* belongs to the frontend proxy; keep FastAPI under the existing /api ingress prefix.
        router.add_api_route(f"/api/v1/install/{filename}", installer(filename), methods=["GET", "HEAD"], name=filename)
    return router

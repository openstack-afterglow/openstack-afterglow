"""Browser-facing Lumen action gates; native ownership and I/O fences remain authoritative."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, Request

from app.services.service_permissions import require_any_service_permission, require_service_permission

_GENERATION = ("lumen-chat_user", "lumen-images_user", "lumen-audio_user")
_READ_METHODS = frozenset({"GET", "HEAD"})


def _object(value) -> dict:
    return value if isinstance(value, dict) else {}


async def _generation(request: Request, principal: Mapping, *, native: bool) -> None:
    require_service_permission(principal, "lumen-chat_user")
    try:
        body = _object(await request.json())
    except ValueError:
        # The native request schema reports malformed JSON; never manufacture a fallback request.
        return
    features = _object(body.get("features")) if native else body
    policy = _object(features.get("tool_policy"))
    selected_tools = (
        (
            policy.get("mode", "agent_default") != "none"
            or any(_object(features.get(name)).get("enabled") for name in ("web_search", "web_fetch", "advisor"))
            or body.get("agent_id") is not None
            or body.get("execution_mode", "chat") != "chat"
            or body.get("skill_ids")
            or body.get("plugin_tool_ids")
            or body.get("plugin_skill_ids")
        )
        if native
        else bool(body.get("tools") or body.get("functions") or body.get("web_search_options"))
    )
    if selected_tools:
        require_service_permission(principal, "lumen-tools_user")
    modalities = (
        features.get("output_modalities") if native else body.get("modalities") or body.get("output_modalities")
    )
    modalities = (
        set(modalities) if isinstance(modalities, list) and all(isinstance(item, str) for item in modalities) else set()
    )
    tools = body.get("tools") if isinstance(body.get("tools"), list) else []
    if modalities & {"image", "video"} or any(_object(tool).get("type") == "image_generation" for tool in tools):
        require_service_permission(principal, "lumen-images_user")
    if modalities & {"audio", "video"} or (not native and body.get("audio")):
        require_service_permission(principal, "lumen-audio_user")
    if native and features.get("memory", True):
        require_service_permission(principal, "lumen-history_reader")


async def authorize_lumen_request(request: Request, upstream_path: str, principal: Mapping) -> None:
    path = upstream_path.partition("?")[0].removeprefix("/v1/").strip("/")
    parts = path.split("/")
    resource = parts[0]
    method = request.method
    read = method in _READ_METHODS
    if resource == "admin":
        if principal.get("is_system_admin") is not True:
            raise HTTPException(status_code=403, detail="시스템 관리자 권한이 필요합니다")
        return
    if principal.get("is_system_admin") is True or method == "OPTIONS":
        return
    if read and (path in {"models", "chat/models", "capabilities", "compat"} or resource == "usage"):
        require_service_permission(principal, "lumen-inventory_reader")
        return
    if method == "POST" and path in {
        "chat/images/generations",
        "chat/images/edits",
        "images/generations",
        "images/edits",
    }:
        require_service_permission(principal, "lumen-images_user")
        if path == "chat/images/edits":
            require_service_permission(principal, "lumen-inventory_reader")
        return
    if method == "POST" and path in {
        "chat/audio/speech",
        "chat/audio/transcriptions",
        "chat/realtime/sessions",
        "audio/speech",
        "audio/transcriptions",
    }:
        require_service_permission(principal, "lumen-audio_user")
        if path == "chat/audio/transcriptions":
            require_service_permission(principal, "lumen-inventory_reader")
        return
    if method == "POST" and path in {
        "chat/completions",
        "responses",
        "messages",
        "messages/count_tokens",
        "temp-completions",
    }:
        await _generation(request, principal, native=path == "temp-completions")
        return
    if resource in {"conversations", "workspaces", "temp-threads"}:
        if read or (method == "POST" and parts[-1] == "context-preview"):
            require_service_permission(principal, "lumen-history_reader")
            if parts[-1] == "context-preview":
                require_service_permission(principal, "lumen-inventory_reader")
        elif method == "DELETE":
            require_service_permission(principal, "lumen-history_editor")
        elif method in {"POST", "PATCH", "PUT"}:
            require_service_permission(principal, "lumen-chat_user")
            if parts[-1] in {"completions", "regenerate"}:
                await _generation(request, principal, native=True)
            if parts[-1] == "code-workspace":
                require_service_permission(principal, "lumen-tools_user")
            if parts[-1] == "compactions":
                require_service_permission(principal, "lumen-inventory_reader")
        else:
            raise HTTPException(status_code=403, detail="허용되지 않은 Lumen 작업입니다")
        return
    if resource == "runs":
        if read:
            require_service_permission(principal, "lumen-history_reader")
        elif method == "POST" and parts[-1] == "cancel":
            # Native Lumen derives the exact action from the owned run, including media-only runs.
            require_any_service_permission(principal, *_GENERATION)
        elif method == "POST" and len(parts) == 4 and parts[2] in {"approvals", "interactions"}:
            require_service_permission(principal, "lumen-chat_user")
            if parts[2] == "approvals":
                require_service_permission(principal, "lumen-tools_user")
        else:
            raise HTTPException(status_code=403, detail="허용되지 않은 Lumen 실행 작업입니다")
        return
    if resource == "batches" or path.startswith("chat/batches"):
        if read:
            require_service_permission(principal, "lumen-history_reader")
        elif method == "POST":
            # Mixed native batches and persisted compat batches are fenced per item by Lumen.
            require_any_service_permission(principal, *_GENERATION)
        else:
            raise HTTPException(status_code=403, detail="허용되지 않은 Lumen batch 작업입니다")
        return
    if resource == "api-keys":
        require_service_permission(principal, "lumen-resources_admin" if method == "DELETE" else "lumen-keys_editor")
        return
    if resource == "memories":
        require_service_permission(
            principal, "lumen-history_reader" if read or path == "memories/search" else "lumen-history_editor"
        )
        return
    if resource in {
        "assets",
        "files",
        "custom-tools",
        "skills",
        "plugin-bindings",
        "mcp-servers",
        "agents",
        "code-workspaces",
        "git-credentials",
    }:
        if method == "DELETE":
            leaf = "lumen-resources_admin"
        elif resource == "git-credentials" or (resource == "agents" and read and len(parts) == 2 and parts[1] != "hub"):
            leaf = "lumen-agents_editor"
        elif read:
            leaf = "lumen-inventory_reader"
        elif resource == "mcp-servers":
            leaf = "lumen-mcp_editor"
        elif resource in {"agents", "code-workspaces"}:
            leaf = "lumen-agents_editor"
        else:
            leaf = "lumen-assets_editor"
        require_service_permission(principal, leaf)
        if read and request.query_params.get("include_private", "").lower() in {"1", "true", "yes", "on"}:
            private_leaf = "lumen-agents_editor" if resource == "agents" else "lumen-assets_editor"
            require_service_permission(principal, private_leaf)
        return
    raise HTTPException(status_code=403, detail="알 수 없는 Lumen 작업입니다")

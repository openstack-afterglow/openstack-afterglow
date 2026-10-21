"""Self-owned native user image preferences; never fetch remote image URLs."""

import base64
import binascii
import hashlib
import io
import json
import re
import secrets
from urllib.parse import quote

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from app.services import keystone

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 4_194_304
IMAGE_SIZE = 128
_METADATA_KEY = "afterglow_profile_image"


def normalize_upload(content: bytes) -> bytes:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "profile_image_size")
    try:
        with Image.open(io.BytesIO(content), formats=("PNG", "JPEG", "WEBP", "GIF")) as source:
            width, height = source.size
            if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION) or width * height > MAX_PIXELS:
                raise HTTPException(422, "profile_image_dimensions")
            if getattr(source, "n_frames", 1) != 1:
                raise HTTPException(422, "profile_image_animation")
            source.load()  # Detect truncated/corrupt raster before persisting any bytes.
            resized = ImageOps.fit(
                ImageOps.exif_transpose(source).convert("RGBA"), (IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS
            )
            # A fresh raster, not a copied info dict: no EXIF, ICC, text, XMP or source filename.
            clean = Image.new("RGB", resized.size, (242, 243, 246))
            clean.paste(resized, mask=resized.getchannel("A"))
            output = io.BytesIO()
            clean.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(output, format="PNG")
            return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "profile_image_invalid") from exc


def _generated(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("ascii")).digest()
    image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), (242, 243, 246))
    draw = ImageDraw.Draw(image)
    color = tuple(40 + channel % 140 for channel in digest[:3])
    for y in range(5):
        for x in range(3):
            if digest[3 + y * 3 + x] & 1:
                for mirrored_x in {x, 4 - x}:
                    left, top = 14 + mirrored_x * 20, 14 + y * 20
                    draw.rectangle((left, top, left + 19, top + 19), fill=color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _require_success(response) -> None:
    response.raise_for_status()
    if not 200 <= response.status_code < 300:
        raise HTTPException(503, "profile_image_native_response")


def _user(conn, user_id: str, identity_domain_id: str) -> dict:
    response = conn.identity.get(f"/users/{quote(user_id, safe='')}", redirect=False)
    _require_success(response)
    user = response.json().get("user")
    if not isinstance(user, dict) or user.get("id") != user_id or user.get("domain_id") != identity_domain_id:
        raise HTTPException(503, "profile_image_identity_mismatch")
    if user.get("enabled") is not True:
        raise HTTPException(403, "profile_image_identity_disabled")
    return user


def _summary(user: dict) -> dict:
    preference = user.get(_METADATA_KEY)
    if preference is None:
        preference = {"kind": "gravatar"}
    if not isinstance(preference, dict):
        raise HTTPException(503, "profile_image_preference_invalid")
    kind = preference.get("kind")
    if kind == "gravatar":
        # https://docs.gravatar.com/rest/hash/: strip, lower-case, SHA-256.
        email = (user.get("email") or "").strip().lower()
        digest = hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None
        return {"kind": kind, "url": f"https://www.gravatar.com/avatar/{digest}?s=128&d=404" if digest else None}
    if (
        kind == "generated"
        and isinstance(preference.get("seed"), str)
        and re.fullmatch(r"[0-9a-f]{32}", preference["seed"])
    ):
        content = _generated(preference["seed"])
    elif kind == "upload" and isinstance(preference.get("png"), str) and len(preference["png"]) <= 100_000:
        try:
            content = normalize_upload(base64.b64decode(preference["png"], validate=True))
        except (binascii.Error, HTTPException) as exc:
            raise HTTPException(503, "profile_image_preference_invalid") from exc
    else:
        raise HTTPException(503, "profile_image_preference_invalid")
    return {"kind": kind, "url": "data:image/png;base64," + base64.b64encode(content).decode("ascii")}


def get_image(conn, user_id: str, identity_domain_id: str) -> dict:
    return _summary(_user(conn, user_id, identity_domain_id))


def save_image(conn, user_id: str, identity_domain_id: str, kind: str, content: bytes | None = None) -> dict:
    preference = {"kind": kind}
    if kind == "generated":
        preference["seed"] = secrets.token_hex(16)
    elif kind == "upload":
        preference["png"] = base64.b64encode(normalize_upload(content or b"")).decode("ascii")
    elif kind != "gravatar":
        raise HTTPException(422, "profile_image_kind")
    # Prove the exact native subject before writing. Raw API preserves native user
    # extra fields; the SDK User schema silently drops unknown update attributes.
    _user(conn, user_id, identity_domain_id)
    writer = keystone.get_admin_project_connection()
    try:
        user = _user(writer, user_id, identity_domain_id)
        response = writer.identity.get(f"/domains/{quote(identity_domain_id, safe='')}", redirect=False)
        _require_success(response)
        home = response.json().get("domain")
        if not isinstance(home, dict) or home.get("id") != identity_domain_id or home.get("enabled") is not True:
            raise HTTPException(403, "profile_image_home_disabled")
        # Native user.extra may be SQL TEXT (65,535 bytes). Conservatively bound
        # the entire visible user, not only our key, retaining existing metadata.
        if len(json.dumps({**user, _METADATA_KEY: preference}, ensure_ascii=True).encode("ascii")) > 60_000:
            raise HTTPException(422, "profile_image_metadata_size")
        # Explicit application-authorized self-image delegation: stock Keystone
        # disallows member update_user. Never send arbitrary fields or IDs.
        response = writer.identity.patch(
            f"/users/{quote(user_id, safe='')}", json={"user": {_METADATA_KEY: preference}}, redirect=False
        )
        _require_success(response)
        saved = _user(writer, user_id, identity_domain_id)
        if saved.get(_METADATA_KEY) != preference:
            raise HTTPException(503, "profile_image_write_unconfirmed")
        return _summary(saved)
    finally:
        writer.close()

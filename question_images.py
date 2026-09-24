from __future__ import annotations

"""Temporary image support for Igniter and Quiz of the Week questions.

Images are private Supabase Storage objects. The app stores only the storage path
inside question JSON. Metadata contains no student data and is used solely for
automatic expiration/cleanup.
"""

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

BUCKET = "question-images"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_STORED_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 1800
RETENTION_DAYS = 7
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _bucket(store):
    return store.client.storage.from_(BUCKET)


def _normalize_image(data: bytes) -> bytes:
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Image is too large. Choose an image under 8 MB.")
    try:
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            if image.mode == "RGBA":
                # White background keeps classroom diagrams crisp and predictable.
                bg = Image.new("RGB", image.size, "white")
                bg.paste(image, mask=image.getchannel("A"))
                image = bg
            else:
                image = image.convert("RGB")
            for quality in (88, 80, 72, 64):
                out = BytesIO()
                image.save(out, format="WEBP", quality=quality, method=6)
                value = out.getvalue()
                if len(value) <= MAX_STORED_BYTES:
                    return value
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("That file could not be read as a PNG, JPG, or WEBP image.") from exc
    raise ValueError("The image is still too large after resizing. Try a smaller crop.")


def upload_question_image(store, uploaded_file, *, question_date: date, kind: str, slot: int) -> str:
    if uploaded_file is None:
        return ""
    content_type = str(getattr(uploaded_file, "type", "") or "").lower()
    if content_type and content_type not in ALLOWED_TYPES:
        raise ValueError("Use a PNG, JPG, or WEBP image.")
    data = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else bytes(uploaded_file.read())
    normalized = _normalize_image(data)
    safe_kind = "quiz" if str(kind) == "quiz" else "igniter"
    storage_path = f"{question_date.isoformat()}/{safe_kind}/q{int(slot)}-{uuid4().hex}.webp"
    _bucket(store).upload(
        storage_path,
        normalized,
        file_options={"content-type": "image/webp", "upsert": "false"},
    )
    expires_on = question_date + timedelta(days=RETENTION_DAYS)
    try:
        store.client.table("question_images").insert({
            "storage_path": storage_path,
            "question_date": question_date.isoformat(),
            "expires_on": expires_on.isoformat(),
        }).execute()
    except Exception:
        # Avoid an orphan if metadata cannot be recorded.
        try:
            _bucket(store).remove([storage_path])
        except Exception:
            pass
        raise
    return storage_path


def signed_question_image_url(store, storage_path: str, *, expires_seconds: int = 3600) -> str:
    path = str(storage_path or "").strip()
    if not path:
        return ""
    try:
        result = _bucket(store).create_signed_url(path, int(expires_seconds))
        if isinstance(result, dict):
            return str(result.get("signedURL") or result.get("signedUrl") or result.get("signed_url") or "")
        data = getattr(result, "data", None)
        if isinstance(data, dict):
            return str(data.get("signedURL") or data.get("signedUrl") or data.get("signed_url") or "")
    except Exception:
        return ""
    return ""


def cleanup_expired_question_images(store, today: date) -> int:
    """Delete expired image objects + metadata. Safe to call repeatedly."""
    try:
        response = store.client.table("question_images").select("image_id,storage_path").lt(
            "expires_on", today.isoformat()
        ).limit(100).execute()
        rows = list(getattr(response, "data", None) or [])
    except Exception:
        return 0
    if not rows:
        return 0
    paths = [str(row.get("storage_path") or "") for row in rows if row.get("storage_path")]
    ids = [str(row.get("image_id") or "") for row in rows if row.get("image_id")]
    try:
        if paths:
            _bucket(store).remove(paths)
        if ids:
            store.client.table("question_images").delete().in_("image_id", ids).execute()
        return len(paths)
    except Exception:
        return 0


def maybe_cleanup_question_images(store, today: date) -> None:
    """At most once per Streamlit session/day; cleanup is maintenance, never blocking."""
    try:
        import streamlit as st
        key = f"question_image_cleanup::{today.isoformat()}"
        if st.session_state.get(key):
            return
        cleanup_expired_question_images(store, today)
        st.session_state[key] = True
    except Exception:
        pass

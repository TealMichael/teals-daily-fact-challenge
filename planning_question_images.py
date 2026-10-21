"""Keep temporary-image expiry tied to the destination question's scheduled date."""
from copy import deepcopy
from datetime import date
from io import BytesIO

from question_images import BUCKET, upload_question_image


def question_for_date(store, question: dict, day: date, kind: str, slot: int) -> dict:
    result = deepcopy(question)
    source = str(result.get("image_path") or "")
    if not source or source.startswith(day.isoformat() + "/"):
        return result
    # A distinct copy preserves the original date's seven-day lifecycle and
    # gives the moved draft its own correctly dated expiration metadata.
    data = store.client.storage.from_(BUCKET).download(source)
    result["image_path"] = upload_question_image(
        store, BytesIO(data), question_date=day, kind=kind, slot=slot)
    return result

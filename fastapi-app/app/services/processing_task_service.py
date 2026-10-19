from __future__ import annotations

from datetime import datetime, timezone

from app.models import Document, DocumentProcessingTask


OCR = "ocr"
TASK_TYPES = (OCR,)

LABELS = {
    OCR: "OCR",
}
VALID_STATUSES = {
    "not_applicable", "not_started", "pending", "processing", "ready", "failed"
}


def _progress(status: str, progress: int | None) -> int:
    if progress is not None:
        return max(0, min(100, int(progress)))
    return {"ready": 100, "processing": 50}.get(status, 0)


async def set_status(
    document_id: int,
    task_type: str,
    status: str,
    *,
    error: str | None = None,
    progress: int | None = None,
) -> None:
    """Create or update one durable stage row.

    OCR's legacy columns remain authoritative while old clients still use them;
    the unified read model below always overlays those values.
    """
    if task_type not in TASK_TYPES:
        raise ValueError("unsupported document processing task type")
    if status not in VALID_STATUSES:
        raise ValueError("unsupported document processing status")

    now = datetime.now(timezone.utc)
    existing = await DocumentProcessingTask.get_or_none(
        document_id=document_id, task_type=task_type
    )
    if status == "processing":
        started_at = (
            existing.started_at
            if existing and existing.status == "processing"
            else now
        )
    elif status in {"pending", "not_started", "not_applicable"}:
        started_at = None
    else:
        started_at = existing.started_at if existing else None
    values = {
        "status": status,
        "progress": _progress(status, progress),
        "error": error[:500] if error else None,
        "started_at": started_at,
        "finished_at": now if status in {"ready", "failed"} else None,
    }
    if existing:
        if status == "processing" and existing.status != "processing":
            existing.attempt_count += 1
        for name, value in values.items():
            setattr(existing, name, value)
        await existing.save()
        return
    await DocumentProcessingTask.create(
        document_id=document_id,
        task_type=task_type,
        attempt_count=1 if status == "processing" else 0,
        **values,
    )


async def initialize_document(document: Document) -> None:
    """Create the durable row for the only processing stage that actually runs."""
    await set_status(
        document.id, OCR, document.ocr_status, error=document.ocr_error
    )


def _stage(task_type: str, status: str, *, error=None, progress=None, updated_at=None) -> dict:
    return {
        "type": task_type,
        "label": LABELS[task_type],
        "status": status,
        "progress": _progress(status, progress),
        "error": error,
        "updated_at": updated_at,
    }


async def stages_for_documents(documents: list[Document]) -> dict[int, list[dict]]:
    if not documents:
        return {}
    result: dict[int, list[dict]] = {}
    for document in documents:
        stages: list[dict] = []
        for task_type in TASK_TYPES:
            if task_type == OCR:
                # Preserve compatibility with the existing OCR fields and repair
                # presentation even if a prior process stopped between two writes.
                status = document.ocr_status
                error = document.ocr_error
                updated_at = document.ocr_updated_at
                progress = None
            stages.append(_stage(
                task_type, status, error=error, progress=progress, updated_at=updated_at
            ))
        result[document.id] = stages
    return result


async def stages_for_document(document: Document) -> list[dict]:
    return (await stages_for_documents([document]))[document.id]

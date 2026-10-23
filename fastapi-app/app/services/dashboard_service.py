from app.models import (
    Document,
    Note,
    ReadingProgress,
    WebImportJob,
)
from app.services import document_service, reading_progress_service, web_import_service


ACTIVE_STATUSES = ("pending", "processing")


async def summary(account_id: int) -> dict:
    active_documents = await Document.filter(
        account_id=account_id,
        deleted_at__isnull=True,
        processing_tasks__status__in=ACTIVE_STATUSES,
    ).distinct().count()
    active_imports = await WebImportJob.filter(
        account_id=account_id,
        status__in=ACTIVE_STATUSES,
    ).count()
    recent_documents = await Document.filter(
        account_id=account_id,
        deleted_at__isnull=True,
    ).order_by("-created_at", "-id").limit(5)

    progress_records = await ReadingProgress.filter(
        account_id=account_id,
        document__deleted_at__isnull=True,
    ).select_related("document").order_by("-updated_at", "-id")
    recent_reading = []
    for record in progress_records:
        if record.document_version != record.document.content_version:
            continue
        recent_reading.append({
            **reading_progress_service.serialize(record),
            "document": document_service.serialize(record.document),
        })
        if len(recent_reading) == 5:
            break

    return {
        "document_total": await Document.filter(
            account_id=account_id, deleted_at__isnull=True
        ).count(),
        "note_total": await Note.filter(account_id=account_id).count(),
        "processing_total": active_documents + active_imports,
        "recent_documents": [document_service.serialize(doc) for doc in recent_documents],
        "recent_reading": recent_reading,
        "web_imports": await web_import_service.list_for_account(account_id, limit=3),
    }

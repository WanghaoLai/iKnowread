from app.models import (
    Document,
    ExperienceDocumentShare,
    Note,
    ReadingProgress,
    WebImportJob,
)
from app.services import document_service, reading_progress_service, web_import_service
from app.dependencies import CurrentAccount


ACTIVE_STATUSES = ("pending", "processing")


async def summary(current: CurrentAccount | int) -> dict:
    account_id = current if isinstance(current, int) else current.id
    is_experience = not isinstance(current, int) and current.is_experience
    if is_experience:
        from app.services import experience_service
        policy = await experience_service.require_enabled(current)
        shared_ids = list(await ExperienceDocumentShare.filter(
            account_id=account_id,
            document__account__role="admin",
            document__deleted_at__isnull=True,
        ).values_list("document_id", flat=True))
        document_filter = {"id__in": shared_ids, "deleted_at__isnull": True}
    else:
        policy = None
        document_filter = {"account_id": account_id, "deleted_at__isnull": True}
    active_documents = await Document.filter(
        **document_filter,
        processing_tasks__status__in=ACTIVE_STATUSES,
    ).distinct().count()
    active_imports = 0 if is_experience else await WebImportJob.filter(
        account_id=account_id,
        status__in=ACTIVE_STATUSES,
    ).count()
    recent_documents = await Document.filter(
        **document_filter,
    ).order_by("-created_at", "-id").limit(5)

    progress_records = await ReadingProgress.filter(
        account_id=account_id,
        document_id__in=(shared_ids if is_experience else await Document.filter(**document_filter).values_list("id", flat=True)),
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
        "document_total": await Document.filter(**document_filter).count(),
        "note_total": (
            await Note.filter(document_id__in=shared_ids, account__role="admin").count()
            if is_experience and policy and policy.show_notes else
            (0 if is_experience else await Note.filter(account_id=account_id).count())
        ),
        "processing_total": active_documents + active_imports,
        "recent_documents": [
            {**document_service.serialize(doc), "read_only": is_experience}
            for doc in recent_documents
        ],
        "recent_reading": recent_reading,
        "web_imports": [] if is_experience else await web_import_service.list_for_account(account_id, limit=3),
    }

from datetime import datetime, timezone

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.common.exception_handler import CustomException
from app.models import Announcement, AnnouncementRead
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementStatusUpdate,
    AnnouncementUpdate,
)


def _admin_public(announcement: Announcement) -> dict:
    creator = getattr(announcement, "created_by", None)
    return {
        "id": announcement.id,
        "title": announcement.title,
        "content": announcement.content,
        "status": announcement.status,
        "published_revision": announcement.published_revision,
        "published_at": announcement.published_at,
        "created_by_id": announcement.created_by_id,
        "created_by_name": creator.name if creator else None,
        "created_at": announcement.created_at,
        "updated_at": announcement.updated_at,
    }


def _user_public(announcement: Announcement, read_revision: int | None) -> dict:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "content": announcement.content,
        "published_revision": announcement.published_revision,
        "published_at": announcement.published_at,
        "is_read": bool(
            read_revision is not None
            and read_revision >= announcement.published_revision
        ),
    }


async def _admin_record(announcement_id: int) -> Announcement:
    announcement = await Announcement.get_or_none(id=announcement_id).select_related(
        "created_by"
    )
    if announcement is None:
        raise CustomException("公告不存在", status_code=404)
    return announcement


async def admin_list(
    keyword: str,
    status: str | None,
    page_num: int,
    page_size: int,
) -> dict:
    query = Announcement.all()
    if keyword:
        query = query.filter(title__icontains=keyword)
    if status:
        query = query.filter(status=status)
    ordered = query.order_by("-updated_at", "-id")
    rows = await ordered.offset((page_num - 1) * page_size).limit(page_size).select_related(
        "created_by"
    )
    return {
        "total": await query.count(),
        "list": [_admin_public(row) for row in rows],
    }


async def create(admin_id: int, payload: AnnouncementCreate) -> dict:
    published = payload.status == "published"
    announcement = await Announcement.create(
        title=payload.title,
        content=payload.content,
        status=payload.status,
        published_revision=1 if published else 0,
        published_at=datetime.now(timezone.utc) if published else None,
        created_by_id=admin_id,
    )
    return _admin_public(
        await Announcement.get(id=announcement.id).select_related("created_by")
    )


async def update(announcement_id: int, payload: AnnouncementUpdate) -> dict:
    async with in_transaction() as connection:
        announcement = await Announcement.filter(id=announcement_id).using_db(
            connection
        ).select_for_update().first()
        if announcement is None:
            raise CustomException("公告不存在", status_code=404)
        changed = announcement.title != payload.title or announcement.content != payload.content
        announcement.title = payload.title
        announcement.content = payload.content
        update_fields = ["title", "content", "updated_at"]
        if changed and announcement.status == "published":
            announcement.published_revision += 1
            announcement.published_at = datetime.now(timezone.utc)
            update_fields.extend(["published_revision", "published_at"])
        await announcement.save(using_db=connection, update_fields=update_fields)
    return _admin_public(await _admin_record(announcement_id))


async def update_status(
    announcement_id: int,
    payload: AnnouncementStatusUpdate,
) -> dict:
    async with in_transaction() as connection:
        announcement = await Announcement.filter(id=announcement_id).using_db(
            connection
        ).select_for_update().first()
        if announcement is None:
            raise CustomException("公告不存在", status_code=404)
        if announcement.status != payload.status:
            announcement.status = payload.status
            update_fields = ["status", "updated_at"]
            if payload.status == "published":
                announcement.published_revision += 1
                announcement.published_at = datetime.now(timezone.utc)
                update_fields.extend(["published_revision", "published_at"])
            await announcement.save(using_db=connection, update_fields=update_fields)
    return _admin_public(await _admin_record(announcement_id))


async def delete(announcement_id: int) -> None:
    deleted = await Announcement.filter(id=announcement_id).delete()
    if not deleted:
        raise CustomException("公告不存在", status_code=404)


async def _published_with_reads(account_id: int) -> tuple[list[Announcement], dict[int, int]]:
    announcements = await Announcement.filter(status="published").order_by(
        "-published_at", "-id"
    )
    if not announcements:
        return [], {}
    reads = await AnnouncementRead.filter(
        account_id=account_id,
        announcement_id__in=[item.id for item in announcements],
    ).values("announcement_id", "read_revision")
    return announcements, {
        int(item["announcement_id"]): int(item["read_revision"])
        for item in reads
    }


async def user_list(account_id: int, page_num: int, page_size: int) -> dict:
    announcements, reads = await _published_with_reads(account_id)
    start = (page_num - 1) * page_size
    page = announcements[start:start + page_size]
    return {
        "total": len(announcements),
        "unread_count": sum(
            reads.get(item.id, 0) < item.published_revision
            for item in announcements
        ),
        "list": [_user_public(item, reads.get(item.id)) for item in page],
    }


async def mark_read(account_id: int, announcement_id: int) -> dict:
    announcement = await Announcement.get_or_none(
        id=announcement_id, status="published"
    )
    if announcement is None:
        raise CustomException("公告不存在或已下架", status_code=404)
    now = datetime.now(timezone.utc)
    try:
        record, _ = await AnnouncementRead.update_or_create(
            account_id=account_id,
            announcement_id=announcement.id,
            defaults={
                "read_revision": announcement.published_revision,
                "read_at": now,
            },
        )
    except IntegrityError:
        await AnnouncementRead.filter(
            account_id=account_id, announcement_id=announcement.id
        ).update(read_revision=announcement.published_revision, read_at=now)
        record = await AnnouncementRead.get(
            account_id=account_id, announcement_id=announcement.id
        )
    return {
        "announcement_id": announcement.id,
        "read_revision": record.read_revision,
        "read_at": record.read_at,
    }


async def mark_all_read(account_id: int) -> dict:
    announcements = await Announcement.filter(status="published")
    for announcement in announcements:
        await AnnouncementRead.update_or_create(
            account_id=account_id,
            announcement_id=announcement.id,
            defaults={
                "read_revision": announcement.published_revision,
                "read_at": datetime.now(timezone.utc),
            },
        )
    return {"updated": len(announcements), "unread_count": 0}

from fastapi import APIRouter, Depends

from app.common.result import Result
from app.dependencies import CurrentAccount, get_current_account
from app.schemas.reading_progress import ReadingProgressUpdate
from app.services import reading_progress_service


router = APIRouter(prefix="/reading-progress")


@router.get("/{document_id}")
async def get_reading_progress(
    document_id: int,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(
        await reading_progress_service.get_current(current, document_id)
    )


@router.put("")
async def save_reading_progress(
    payload: ReadingProgressUpdate,
    current: CurrentAccount = Depends(get_current_account),
):
    return Result.success(
        await reading_progress_service.save(current, payload.source_anchor)
    )

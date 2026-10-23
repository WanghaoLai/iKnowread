from fastapi import APIRouter, Depends

from app.common.result import Result
from app.dependencies import CurrentAccount, get_current_account
from app.services import dashboard_service


router = APIRouter()


@router.get("/dashboard")
async def dashboard(current: CurrentAccount = Depends(get_current_account)):
    return Result.success(await dashboard_service.summary(current.id))

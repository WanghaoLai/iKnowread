from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api_paths import api_path
from app.common.result import Result
from app.config import settings
from app.dependencies import CurrentAccount, get_current_account
from app.schemas.account import AccountPublic, LoginRequest, PasswordUpdateRequest, RegisterRequest
from app.security import issue_session_token, SESSION_COOKIE, SESSION_MAX_AGE
from app.services import auth_service, captcha_service
from app.services import experience_service
from app.services.auth_guard import limit_auth

router = APIRouter()


@router.get(api_path("auth.captcha"))
async def captcha(request: Request, response: Response):
    await limit_auth(request, "captcha")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return Result.success(await captcha_service.issue())


@router.get(api_path("auth.me"))
async def me(current: CurrentAccount = Depends(get_current_account)):
    return Result.success(AccountPublic.model_validate(current.account))


# 登录
@router.post(api_path("auth.login"))
async def login(account: LoginRequest, response: Response, request: Request):
    await limit_auth(request, "login", account.username)
    await captcha_service.verify(account.captcha_id, account.captcha_code)
    logged_in = await auth_service.login(account.role, account.username, account.password)
    token = issue_session_token(
        logged_in.id,
        logged_in.role,
        logged_in.password,
        logged_in.session_version,
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        path="/",
    )
    return Result.success(AccountPublic.model_validate(logged_in))


@router.post(api_path("auth.logout"))
async def logout(
    response: Response,
    current: CurrentAccount = Depends(get_current_account),
):
    await auth_service.revoke_sessions(
        current.id, current.account.session_version
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Result.success()


# 注册
@router.post(api_path("auth.register"))
async def register(account: RegisterRequest, request: Request):
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="当前系统未开放自助注册，请联系管理员创建账号")
    await limit_auth(request, "register", account.username)
    await auth_service.register(account.username, account.password, account.name)
    return Result.success()


# 修改密码
@router.put(api_path("auth.password"))
async def update_password(
    account: PasswordUpdateRequest,
    response: Response,
    request: Request,
    current: CurrentAccount = Depends(get_current_account),
):
    experience_service.deny_experience_write(current, "修改密码")
    await limit_auth(request, "password", str(current.id))
    await auth_service.update_password(
        current.id, account.password, account.newPassword
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Result.success()

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.models import Account
from app.security import decode_session_token, SESSION_COOKIE, session_matches_account


@dataclass(frozen=True)
class CurrentAccount:
    id: int
    role: str
    account: Account

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def _unauthorized(message: str = "请先登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_account(request: Request) -> CurrentAccount:
    token = request.cookies.get(SESSION_COOKIE)
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise _unauthorized()

    try:
        payload = decode_session_token(token)
    except ValueError as exc:
        raise _unauthorized(str(exc)) from exc

    role = payload["role"]
    account = await Account.get_or_none(id=payload["sub"], role=role)
    if (
        account is None
        or not account.password
        or not session_matches_account(
            payload, account.password, account.session_version
        )
    ):
        raise _unauthorized("登录状态已失效，请重新登录")
    return CurrentAccount(id=account.id, role=role, account=account)


async def require_admin(current: CurrentAccount = Depends(get_current_account)) -> CurrentAccount:
    if not current.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current


def require_self_or_admin(current: CurrentAccount, account_id: int) -> None:
    if current.is_admin:
        return
    if current.id != account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该账号")


def require_document_owner(current: CurrentAccount, document) -> None:
    # 与文件目录权限口径一致：管理员可代管所有账号的文档，普通用户仅限本人
    if current.is_admin:
        return
    if current.id != document.account_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该文档")

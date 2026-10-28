from __future__ import annotations

from app.common.exception_handler import CustomException
from app.models import Account, Document
from app.schemas.account import AccountPublic, normalize_username
from app.security import hash_password
from app.services.auth_guard import password_work
from app.services.resource_limits import account_lock
from app.storage import complete_on_cancellation, get_storage, run_storage_io
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

RELATIVE_PREFIX = "files/download/"
TEMP_PREFIX = RELATIVE_PREFIX + "temp/"
VALID_ROLES = {"admin", "user"}


def normalize_role(role: str | None) -> str:
    value = (role or "").strip().lower()
    return value if value in VALID_ROLES else ""


def serialize(account: Account) -> dict:
    return AccountPublic.model_validate(account).model_dump()


async def get_by_id(account_id: int, role: str | None = None) -> Account:
    query = Account.filter(id=account_id)
    normalized = normalize_role(role)
    if role is not None:
        if not normalized:
            raise CustomException("账号角色无效")
        query = query.filter(role=normalized)
    account = await query.first()
    if account is None:
        raise CustomException("未找到用户", status_code=404)
    return account


async def claim_temp(path: str | None, role: str, account_id: int) -> str | None:
    normalized = normalize_role(role)
    if not path or not path.startswith(TEMP_PREFIX) or not normalized:
        return path
    name = path[len(TEMP_PREFIX):]
    storage = get_storage()
    await run_storage_io(storage.move, f"temp/{name}", f"{normalized}/{account_id}/{name}")
    return f"{RELATIVE_PREFIX}{normalized}/{account_id}/{name}"


def validate_new_avatar(path: str | None) -> None:
    if path and not path.startswith(TEMP_PREFIX):
        raise CustomException("新账号头像必须来自本次上传")


async def validate_owned_avatar(
    path: str | None, role: str, account_id: int, current_avatar: str | None = None
) -> None:
    if not path:
        return
    if path == current_avatar:
        return
    expected = f"{RELATIVE_PREFIX}{normalize_role(role)}/{account_id}/avatars/"
    if not path.startswith(expected):
        raise CustomException("头像文件不属于该账号")
    key = path[len(RELATIVE_PREFIX):]
    storage = get_storage()
    if not await run_storage_io(storage.exists, key):
        raise CustomException("头像文件不存在")


async def _delete_avatar_if_unreferenced(path: str | None) -> None:
    if not path or not path.startswith(RELATIVE_PREFIX):
        return
    if await Account.filter(avatar=path).exists():
        return
    if await Document.filter(path=path).exists() or await Document.filter(ocr_path=path).exists():
        return
    storage = get_storage()
    await run_storage_io(storage.delete, path[len(RELATIVE_PREFIX):])


async def select_page(role: str, name: str = "", page_num: int = 1, page_size: int = 10) -> dict:
    normalized = normalize_role(role)
    if not normalized:
        raise CustomException("账号角色无效")
    query = Account.filter(role=normalized, name__contains=name).order_by("-created_at", "-id")
    accounts = await query.offset((page_num - 1) * page_size).limit(page_size)
    return {"total": await query.count(), "list": [serialize(item) for item in accounts]}


async def _create_with_avatar(values: dict, uploaded_avatar: str | None, role: str) -> Account:
    """Commit the account row and avatar move as one cancellation-safe unit."""
    moved: tuple[str, str] | None = None
    try:
        async with in_transaction() as connection:
            account = await Account.create(**values, avatar=None, using_db=connection)
            if uploaded_avatar:
                avatar = await claim_temp(uploaded_avatar, role, account.id)
                if avatar is None:
                    raise CustomException("头像文件不存在", status_code=400)
                if avatar != uploaded_avatar:
                    moved = (avatar[len(RELATIVE_PREFIX):], uploaded_avatar[len(RELATIVE_PREFIX):])
                account.avatar = avatar
                await account.save(update_fields=["avatar"], using_db=connection)
    except IntegrityError as exc:
        if moved:
            storage = get_storage()
            await run_storage_io(storage.restore, moved[0], moved[1])
        raise CustomException("账号重复", status_code=409) from exc
    except BaseException:
        if moved:
            storage = get_storage()
            await run_storage_io(storage.restore, moved[0], moved[1])
        raise
    return account


async def create(data: dict) -> Account:
    role = normalize_role(data.get("role"))
    if not role:
        raise CustomException("账号角色无效")
    raw_username = data.get("username")
    if not isinstance(raw_username, str):
        raise CustomException("账号不能为空")
    username = normalize_username(raw_username)
    if not username:
        raise CustomException("账号不能为空")
    validate_new_avatar(data.get("avatar"))
    values = {key: value for key, value in data.items() if key in {"username", "password", "name", "avatar"}}
    values["username"] = username
    uploaded_avatar = values.pop("avatar", None)
    values["password"] = await password_work(hash_password, values["password"])
    values["role"] = role
    return await complete_on_cancellation(
        _create_with_avatar(values, uploaded_avatar, role)
    )


async def update(account_id: int, data: dict) -> Account:
    async with account_lock(account_id):
        account = await get_by_id(account_id)
        values = {key: value for key, value in data.items() if key in {"name", "avatar"}}
        await validate_owned_avatar(values.get("avatar"), account.role, account.id, account.avatar)
        old_avatar = account.avatar
        if values:
            await Account.filter(id=account.id).update(**values)
        new_avatar = values.get("avatar", old_avatar)
        if old_avatar and old_avatar != new_avatar and old_avatar.startswith(RELATIVE_PREFIX):
            await _delete_avatar_if_unreferenced(old_avatar)
        return await get_by_id(account.id)


async def _delete_consistently(account_id: int) -> None:
    async with account_lock(account_id):
        account = await get_by_id(account_id)
        if account.is_experience:
            raise CustomException("体验账号由体验管理页面维护，不能删除", status_code=409)
        prefix = f"{account.role}/{account.id}"
        storage = get_storage()
        staged = await run_storage_io(storage.stage_tree, prefix)
        try:
            async with in_transaction() as connection:
                if account.role == "admin":
                    admins = await Account.filter(role="admin").using_db(connection).select_for_update().all()
                    if len(admins) <= 1:
                        raise CustomException("必须至少保留一个管理员")
                await Account.filter(id=account.id).using_db(connection).delete()
        except BaseException:
            if staged:
                await run_storage_io(storage.restore_tree, staged, prefix)
            raise
        if staged:
            await run_storage_io(storage.delete_tree, staged)


async def delete(account_id: int) -> None:
    await complete_on_cancellation(_delete_consistently(account_id))

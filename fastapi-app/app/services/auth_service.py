from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Account
from app.security import PASSWORD_SCHEME, hash_password, password_needs_rehash, verify_password
from app.services.auth_guard import password_work
from app.services.account_service import normalize_role
from tortoise.exceptions import IntegrityError

_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$aWtub3dyZWFkLWR1bW15IQ$"
    "fGfdob-igIXU0SJU8pOHmhLiOSfvFHEINxt7VqnfaXc"
)


async def login(role: str, username: str, password: str) -> Account:
    normalized = normalize_role(role)
    account = await Account.get_or_none(username=username, role=normalized)
    stored = account.password if account is not None else _DUMMY_PASSWORD_HASH
    valid = await password_work(verify_password, password, stored)
    if account is None or not valid:
        raise CustomException("账号或密码错误", status_code=401)
    if password_needs_rehash(account.password):
        account.password = await password_work(hash_password, password)
        await account.save(update_fields=["password"])
    if account.role == "admin":
        bootstrap_secret = settings.data_dir / ".initial-admin-password"
        if bootstrap_secret.is_file():
            bootstrap_secret.unlink()
    return account


async def register(username: str, password: str, name: str | None = None) -> Account:
    try:
        password_hash = await password_work(hash_password, password)
        return await Account.create(username=username, password=password_hash, name=name or username, role="user")
    except IntegrityError as exc:
        raise CustomException("账号重复", status_code=409) from exc


async def update_password(account_id: int, old_password: str, new_password: str) -> None:
    account = await Account.get_or_none(id=account_id)
    if account is None:
        raise CustomException("未找到用户", status_code=404)
    if not await password_work(verify_password, old_password, account.password):
        raise CustomException("原密码错误")
    if old_password == new_password:
        raise CustomException("新密码不能跟原密码相同")
    if len(new_password) < 8:
        raise CustomException("新密码至少需要 8 位")
    password_hash = await password_work(hash_password, new_password)
    await Account.filter(id=account.id).update(password=password_hash)


async def revoke_sessions(account_id: int, current_version: int) -> None:
    """Invalidate every token issued before this logout.

    The compare-and-update keeps concurrent logout requests idempotent: if a
    second request already advanced the version, the current token is already
    invalid and no additional write is required.
    """
    await Account.filter(
        id=account_id, session_version=current_version
    ).update(session_version=current_version + 1)


async def migrate_legacy_passwords() -> None:
    for account in await Account.all():
        if password_needs_rehash(account.password) and account.password:
            # 当前方案的低迭代次数哈希由登录流程用原密码升级；
            # 其余存量值是旧版本明文，包含 "$" 也不应被误判为哈希。
            if account.password.startswith(f"{PASSWORD_SCHEME}$"):
                continue
            account.password = await password_work(hash_password, account.password)
            await account.save(update_fields=["password"])

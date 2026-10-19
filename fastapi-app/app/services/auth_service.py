import asyncio
import logging

from app.common.exception_handler import CustomException
from app.config import settings
from app.models import Account
from app.security import PASSWORD_SCHEME, hash_password, password_needs_rehash, verify_password
from app.services.auth_guard import password_work
from app.services.account_service import normalize_role
from app.schemas.account import normalize_username
from tortoise.exceptions import IntegrityError

logger = logging.getLogger(__name__)
_legacy_password_migration_task: asyncio.Task | None = None

_DUMMY_PASSWORD_HASH = (
    "pbkdf2_sha256$600000$aWtub3dyZWFkLWR1bW15IQ$"
    "fGfdob-igIXU0SJU8pOHmhLiOSfvFHEINxt7VqnfaXc"
)


async def login(role: str, username: str, password: str) -> Account:
    normalized = normalize_role(role)
    username = normalize_username(username)
    account = await Account.get_or_none(username=username, role=normalized)
    stored = account.password if account is not None else _DUMMY_PASSWORD_HASH
    if account is not None and not stored.startswith(f"{PASSWORD_SCHEME}$"):
        # Legacy plaintext comparison is cheap. Perform the normal PBKDF2 work
        # first so account discovery cannot distinguish legacy rows by timing.
        await password_work(verify_password, password, _DUMMY_PASSWORD_HASH)
        valid = verify_password(password, stored)
    else:
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
    username = normalize_username(username)
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


async def migrate_legacy_passwords(batch_size: int = 25) -> None:
    """Upgrade plaintext rows in bounded, restart-safe keyset batches."""
    last_id = 0
    batch_size = max(1, min(batch_size, 200))
    while True:
        accounts = await Account.filter(id__gt=last_id).order_by("id").limit(batch_size)
        if not accounts:
            return
        for account in accounts:
            last_id = account.id
            original = account.password
            if not original:
                continue
            # 当前方案的低迭代次数哈希由登录流程用原密码升级；
            # 其余存量值是旧版本明文，包含 "$" 也不应被误判为哈希。
            if original.startswith(f"{PASSWORD_SCHEME}$"):
                continue
            password_hash = await password_work(hash_password, original)
            # 登录期间可能已经修改密码；CAS 避免迁移覆盖新值。
            await Account.filter(id=account.id, password=original).update(
                password=password_hash
            )
        await asyncio.sleep(0)


async def _run_legacy_password_migration() -> None:
    try:
        await migrate_legacy_passwords()
    except asyncio.CancelledError:
        raise
    except Exception:
        # 启动与服务可用性不应由可恢复的后台迁移绑定；下次启动会从头扫描，
        # 已迁移行会被跳过。
        logger.exception("Legacy password migration failed; it will resume after restart")


def start_legacy_password_migration() -> None:
    global _legacy_password_migration_task
    if _legacy_password_migration_task is None or _legacy_password_migration_task.done():
        _legacy_password_migration_task = asyncio.create_task(
            _run_legacy_password_migration(), name="legacy-password-migration"
        )


async def stop_legacy_password_migration() -> None:
    global _legacy_password_migration_task
    task = _legacy_password_migration_task
    _legacy_password_migration_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

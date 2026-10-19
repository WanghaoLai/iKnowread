from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：fastapi-app/（app/config.py 的上两级）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务
    APP_NAME: str = "iKnowread"
    HOST: str = "127.0.0.1"
    PORT: int = 9090
    DEBUG: bool = False

    # 认证：生产环境必须显式配置；开发环境留空时使用进程级临时密钥
    AUTH_SECRET: str = ""
    AI_CONFIG_KEY: str = ""  # Fernet 密钥；留空时自动生成并持久化到 data/.ai-config-key
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = ""
    ALLOW_REGISTRATION: bool = False
    AUTH_RATE_WINDOW_SECONDS: int = 60
    LOGIN_RATE_LIMIT: int = 10
    PASSWORD_CHANGE_RATE_LIMIT: int = 5
    CAPTCHA_RATE_LIMIT: int = 30
    CAPTCHA_TTL_SECONDS: int = 120
    REGISTER_RATE_LIMIT: int = 3
    PASSWORD_WORKERS: int = 2
    PASSWORD_QUEUE_WAIT_SECONDS: float = 1.0

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "iknowread"
    DB_PASSWORD: str = ""
    DB_DATABASE: str = "iknowread"
    DB_AUTO_CREATE: bool = False     # 开发环境可在本地 .env 中显式启用
    DB_ECHO: bool = False
    INSTANCE_LOCK_HEARTBEAT_SECONDS: float = 15.0

    # 文件存储
    UPLOAD_DIR: str = ""                              # 留空 = 项目根下 data/files
    USER_STORAGE_QUOTA_BYTES: int = 2 * 1024 * 1024 * 1024
    USER_DOCUMENT_LIMIT: int = 200
    USER_TOTAL_DOCUMENT_LIMIT: int = 400
    USER_NOTE_LIMIT: int = 10000
    USER_HIGHLIGHT_LIMIT: int = 10000
    DOCUMENT_HIGHLIGHT_LIMIT: int = 1000
    STORAGE_MIN_FREE_BYTES: int = 2 * 1024 * 1024 * 1024
    UPLOAD_CONCURRENCY: int = 3
    UPLOAD_QUEUE_WAIT_SECONDS: float = 1.0
    DOCX_MAX_ENTRIES: int = 2000
    DOCX_MAX_UNCOMPRESSED_BYTES: int = 200 * 1024 * 1024
    PDF_MAX_PAGES: int = 1000

    # PDF OCR：OCRmyPDF 负责生成带隐藏文字层的派生 PDF，原文件始终保留
    OCR_ENABLED: bool = False
    OCR_COMMAND: str = "ocrmypdf"
    OCR_LANGUAGES: str = "chi_sim+eng"
    OCR_WORKERS: int = 1
    OCR_JOBS_PER_DOCUMENT: int = 1
    OCR_TIMEOUT_SECONDS: int = 900
    OCR_PAGE_TIMEOUT_SECONDS: int = 120
    OCR_MAX_IMAGE_MPIXELS: float = 50.0

    # AI 外呼边界：单账号串行，整台小服务器最多同时处理少量长请求。
    AI_GLOBAL_CONCURRENCY: int = 3
    AI_ACCOUNT_CONCURRENCY: int = 1
    AI_QUEUE_WAIT_SECONDS: float = 1.0
    AI_MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024

    # 导出边界，防止一次把任意增长的数据完整装入内存。
    NOTE_EXPORT_MAX_ITEMS: int = 5000
    NOTE_EXPORT_MAX_BYTES: int = 20 * 1024 * 1024

    # 跨域
    CORS_ORIGINS: str = ""                            # 逗号分隔多个源

    @field_validator("DB_DATABASE")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        # MySQL does not support binding an identifier as a query parameter.
        # Restrict the configured identifier before it is quoted in CREATE DATABASE.
        if not value or len(value) > 64 or not all(character.isalnum() or character == "_" for character in value):
            raise ValueError("DB_DATABASE 只能包含字母、数字和下划线，且不能超过 64 个字符")
        return value

    @property
    def data_dir(self) -> Path:
        """数据目录（数据库外的本地状态：密钥文件等），与 upload_dir 分离。"""
        return BASE_DIR / "data"

    @property
    def upload_dir(self) -> Path:
        if self.UPLOAD_DIR:
            return Path(self.UPLOAD_DIR).expanduser().resolve()
        return self.data_dir / "files"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if not self.DEBUG and "*" in origins:
            raise ValueError("生产环境 CORS_ORIGINS 必须列出可信前端地址，不能使用 *")
        return origins


settings = Settings()

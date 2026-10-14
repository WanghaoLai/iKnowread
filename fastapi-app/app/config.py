from pathlib import Path

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
    HOST: str = "0.0.0.0"
    PORT: int = 9090
    DEBUG: bool = True

    # 认证：生产环境必须显式配置；开发环境留空时使用进程级临时密钥
    AUTH_SECRET: str = ""
    AI_CONFIG_KEY: str = ""  # Fernet 密钥；留空时自动生成并持久化到 data/.ai-config-key
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = ""
    ALLOW_REGISTRATION: bool = True
    AUTH_RATE_WINDOW_SECONDS: int = 60
    LOGIN_RATE_LIMIT: int = 10
    CAPTCHA_RATE_LIMIT: int = 30
    CAPTCHA_TTL_SECONDS: int = 120
    REGISTER_RATE_LIMIT: int = 3
    PASSWORD_WORKERS: int = 2
    PASSWORD_QUEUE_WAIT_SECONDS: float = 1.0

    # 数据库
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_DATABASE: str = "iknowread"
    DB_AUTO_CREATE: bool = True      # 启动时自动创建数据库
    DB_ECHO: bool = False

    # 文件存储
    UPLOAD_DIR: str = ""                              # 留空 = 项目根下 data/files
    USER_STORAGE_QUOTA_BYTES: int = 2 * 1024 * 1024 * 1024
    USER_DOCUMENT_LIMIT: int = 200
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
    CORS_ORIGINS: str = "*"                           # 逗号分隔多个源

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

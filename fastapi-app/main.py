import sys
from pathlib import Path

# 自举：把脚本所在目录加入 sys.path 首位，保证从任意工作目录、任意方式启动都能解析 app 包
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app import create_app
from app.config import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        access_log=False,
    )

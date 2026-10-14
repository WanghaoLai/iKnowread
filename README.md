# iKnowread

iKnowread 使用 Vue 3 + FastAPI + MySQL，支持 PDF 与 DOCX 文档管理、在线阅读和多模型智能助手。后端需要 Python 3.11 或更新版本。

生产部署已加入 DOCX 活动内容隔离、认证限速、受控密码计算、关闭式注册、账号存储配额、文档结构验证、AI 并发边界、数据库就绪探针和一致性备份保护。Docker 默认关闭自助注册与 OCR，可在完成容量评估后显式开启。

## 架构

- `fastapi-app/app/models/account.py` 是唯一账号模型，`role` 区分管理员和用户。
- `document.account_id` 通过外键关联账号，删除账号时数据库级联删除文档记录；账号角色、文档格式、文件路径与必填字段由数据库约束保护。
- `fastapi-app/app/migrations/` 按固定顺序执行版本化迁移；应用启动不再根据 ORM 模型猜测改表。
- 路由在 `fastapi-app/app/routers/__init__.py` 显式注册。
- 登录验证码由后端生成 PNG 图片并保存为短时、一次性挑战；验证码通过后才执行密码校验。用户名、密码或角色错误继续使用统一提示，登录与验证码获取分别按客户端 IP 限速。
- 文件操作只通过 `StorageBackend` 契约进行。删除先移入暂存区，数据库事务成功后再清理；启动时会恢复中断操作并清理陈旧孤儿文件。
- PDF 由 PDF.js 通过 HTTP Range 分段读取，可在分页阅读和不分页的长文阅读之间切换；长文模式按视口懒加载页面并保留可选择文字层。DOCX 由 `docx-preview` 在浏览器连续渲染，不依赖 LibreOffice。

## 本地运行

1. 复制 `fastapi-app/.env.example` 为 `fastapi-app/.env`，配置 MySQL、`AUTH_SECRET` 和可信 `CORS_ORIGINS`。
2. 安装 OCR 运行环境。Tesseract 负责识别，OCRmyPDF 与 PDFium 已由 Python 依赖安装；中文识别需要 `chi_sim` 语言包：

   ```bash
   # macOS
   brew install tesseract tesseract-lang

   # Debian / Ubuntu
   sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim
   ```

3. 安装并启动后端：

   ```bash
   cd fastapi-app
   python3 -m pip install -r requirements.txt
   python3 -m uvicorn main:app --reload --port 9090
   ```

   `requirements.txt` 表达本地开发所需的直接依赖范围；生产 Docker 镜像使用 `requirements.lock` 中经过回归验证的完整精确版本。新增或升级依赖后，应先更新直接依赖、完成全套测试，再从验证通过的镜像重新生成锁文件。

4. 安装并启动前端：

   ```bash
   cd vue
   npm ci
   npm run dev
   ```

开发服务器把 `/api` 代理到 `http://localhost:9090`。生产环境需要由同源反向代理把 `/api` 转发到 FastAPI。

首次启动且数据库没有管理员时，系统会创建 `DEFAULT_ADMIN_USERNAME`，并使用 `DEFAULT_ADMIN_PASSWORD`；若密码留空，则生成随机一次性密码并写入后端数据目录的 `.initial-admin-password`（权限 `0600`）。Docker 部署时对应 `runtime/app-data/.initial-admin-password`。

登录验证码默认 120 秒过期且只能使用一次，可通过 `CAPTCHA_TTL_SECONDS` 调整有效期；`CAPTCHA_RATE_LIMIT` 控制同一 IP 在认证时间窗内获取验证码的次数。当前单进程部署会在内存中保存未使用的挑战，重启后自动全部失效。

## AI服务

普通用户和管理员均可从左侧「AI服务」进入两个子页面：

- **API配置**：统一管理 DeepSeek、智谱 GLM、Xiaomi MiMo 和阿里云百炼配置。每个账号可保存多项配置，分别设置官方 Base URL、API Key、模型 ID、温度、最大输出 token 数、深度思考和系统提示词，并测试、启用、切换或删除配置。配置保存后，打开模型下拉框会使用已加密保存的密钥从厂商接口获取当前账号可用模型，也可手动刷新或输入模型 ID；厂商不支持模型枚举时自动回退到常用模型建议。新建配置必须填写密钥，编辑时留空会保留原密钥。
- **智能助手**：使用当前账号启用的配置问答，也可在页面顶部直接切换已保存配置；切换时自动开始新对话，避免混用不同模型的上下文。支持连续追问、Enter 发送、Shift + Enter 换行、新建对话、加载状态和失败后保留问题。采用非流式回答，每次携带最近 20 轮且不超过 120,000 字符的上下文；会话仅保留在当前页面，离开或刷新后清空。
- **在线阅读与选文解释**：PDF 可随时切换「分页阅读」和「长文阅读」，浏览器会记住阅读偏好；分页模式使用预览区底部中央的悬浮箭头翻页，长文模式连续展示全部页面并只渲染视口附近内容。DOCX 默认连续阅读。在任一模式中拖动选择字、词、句或段，系统会在选区附近自动调用当前账号配置的模型并显示解释。PDF 通过与画布对齐的文字层支持选择。扫描版或图文混合 PDF 上传后进入后台 OCR 队列，系统保留原文件、生成带隐藏文字层的派生 PDF，完成后阅读页自动刷新；失败时可查看状态并一键重试。单次最多选择 4,000 个字符，相同选文在当前预览期间使用内存缓存，换页、滚动或切换文档会收起窗口。
- **我的笔记**：选文解释弹窗支持直接保存，或先补充个人备注再保存；也可在笔记页手动创建、编辑和删除笔记。列表支持全文检索、来源文档筛选、按时间排序和按文档编排，并可把当前筛选结果一键导出为 Markdown。笔记按账号隔离，保存文档名称快照；原文档删除后笔记仍保留并可继续检索和导出。

所有厂商通过同一配置模型和调用流程管理，厂商适配器负责官方地址校验、思考参数和输出 token 字段差异。接口依据 [DeepSeek](https://api-docs.deepseek.com/)、[智谱 GLM](https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine)、[Xiaomi MiMo](https://mimo.mi.com/docs/quick-start/model) 和 [阿里云百炼](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions/) 的 OpenAI 兼容接口；配置页提供常用模型建议，也可手动填写账号实际可用的模型 ID。系统最大输出限制为 32,768 token，接口总等待上限 125 秒。

新增依赖后需执行 `python3 -m pip install -r requirements.txt` 并重启后端。启动时自动执行版本 3 迁移创建 `ai_config` 表，版本 4 增加文档 OCR，版本 5 将单配置迁移为多厂商、多配置结构并保留原 DeepSeek 配置，版本 6 创建用户笔记表，版本 7 增加可撤销会话版本。配置和笔记均按账号隔离；配置名称在账号内唯一，删除账号时级联删除其配置和笔记。后端提供厂商目录和配置增删改查、测试及启用接口，并保留 `GET/PUT /ai/config`、`POST /ai/test` 兼容入口；`POST /ai/chat` 与 `POST /ai/explain` 始终使用当前启用配置。笔记接口提供创建、编辑、删除、搜索、汇总和 Markdown 导出。所有接口均需登录，账号身份只从登录会话读取；退出会递增账号会话版本，使同一账号此前签发的 Cookie 和 Bearer 令牌立即失效。

API Key 由后端 Fernet 加密保存，读取接口仅返回 `has_api_key`，不向浏览器回传密钥。默认首次保存时自动生成 `fastapi-app/data/.ai-config-key`（权限 0600），请将该文件与数据库分别持久化备份。多实例部署应设置相同的 `AI_CONFIG_KEY`；可通过 `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 生成。丢失或更换加密密钥后，各账号需要重新填写 API Key。

## 验证

```bash
cd fastapi-app
python3 -m compileall -q app tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tests/database_security_check.py

IKNOWREAD_TEST_USER=<user> \
IKNOWREAD_TEST_USER_PASSWORD=<password> \
IKNOWREAD_TEST_ADMIN=<admin> \
IKNOWREAD_TEST_ADMIN_PASSWORD=<password> \
bash tests/security_integration.sh

cd ../vue
npm ci
npm run build
```

仓库还提供 `deploy/compose.verify.yaml` 和 `fastapi-app/tests/docker_smoke_check.py`，用于在独立项目名和一次性卷中验证生产镜像、MySQL 迁移、本地 HTTPS、登录 Cookie、上传、笔记、重启持久性及 PDF Range。该覆盖文件要求显式传入一次性 `VERIFY_ADMIN_PASSWORD`，不能复用正式管理员密码。

## Docker 云端部署

针对 Ubuntu 24.04、2 核 2GB 内存服务器的完整步骤，见 [Docker 部署教程](docs/Ubuntu-24.04-Docker部署教程.md)。配套 `compose.yaml` 和 `deploy/` 提供 HTTPS、持久化、资源限制和备份脚本；生产基础镜像使用 digest 固定，Python 生产依赖使用精确锁文件；默认关闭 OCR，可按教程启用。

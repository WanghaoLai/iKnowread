# iKnowread

> 自托管的文档阅读与知识沉淀平台：把 PDF、DOCX、Markdown 和网页变成可划词理解、可高亮标注、可沉淀笔记的私有知识库。Vue 3 + FastAPI + MySQL，Docker 一键部署。

## 为什么需要 iKnowread

扫描版 PDF 读不了文字、划词要切词典、笔记散落在各处、AI 阅读助手把你的文件和密钥送上第三方云端——iKnowread 把这些拉回你自己手里：

- **阅读器原生可用**：上传即可读。扫描 PDF 后台 OCR 后文字可选可搜；阅读进度自动保存。
- **理解即沉淀**：划词调用你自己账号的大模型解释，一键保存为高亮备注或笔记，原文位置可随时回跳。
- **数据完全自持**：文档、笔记、高亮存你自己的服务器；AI API Key 由后端 Fernet 加密保存，不经过任何中间方。

## 功能全景

| 模块 | 能力 |
|------|------|
| 我的文档 | PDF / DOCX / Markdown 上传；URL 网页异步提取为 Markdown；预览、抓取/OCR 状态与失败重试、删除（进回收站） |
| 我的回收站 | 已删文档一键恢复（高亮、笔记关联、阅读进度一并复原）或彻底删除 |
| 在线阅读 | PDF 分页 / 长文双模式、文档内搜索、缩放；DOCX 连续阅读；阅读进度按内容版本记忆 |
| 划词解释与高亮 | 选中文本自动调用当前账号配置的模型解释；解释可直接保存为持久化高亮备注，重开文档高亮仍在，可编辑、定位、删除 |
| 我的笔记 | AI 划词笔记与手动笔记、全文检索、按来源文档筛选编排、批量导出 Markdown；删除文档不丢笔记 |
| 智能助手 | 多轮问答，上下文最多 20 轮 / 120,000 字符 |
| API 配置 | 每账号多份配置（DeepSeek / 智谱 GLM / Xiaomi MiMo / 阿里云百炼），密钥加密存储、在线测试、一键切换 |
| 账号管理 | 管理员创建账号、分配角色；注册默认关闭；账号存储配额与文档数量限额 |

## 快速开始

### Docker 部署（推荐）

面向 Ubuntu 24.04（4 核 4GB）的完整步骤见 [Docker 部署教程](docs/Ubuntu-24.04-Docker部署教程.md)；已有线上版本从本地同步代码时使用 [线上服务器代码同步更新教程](docs/iKnowread线上服务器代码同步更新教程.md)。最短路径：

```bash
# 域名与证书联系人邮箱（不覆盖已有 .env）
python3 deploy/init-env.py read.example.com you@example.com
docker compose up -d --build      # 核心服务：db + backend + web，Caddy 自动 HTTPS

# 可选网页收藏：先在 .env 设置 CRAWLER_ENABLED=true，再显式启用隔离爬虫
docker compose --profile web-import up -d --build
```

生产镜像内置 OCRmyPDF、pypdfium2 与 Tesseract 中英文语言包；按首发方案，Docker 部署默认关闭 OCR。完成容量与扫描件验收后，可在 `.env` 中设置 `OCR_ENABLED=true` 并重建后端容器以启用。

首次启动若无管理员，系统自动创建 `admin`，随机密码写入持久卷中的 `/app/data/.initial-admin-password`（权限 0600）。可执行 `docker compose exec backend cat /app/data/.initial-admin-password` 读取一次性密码。

从旧版升级时，启动前置任务会在新持久卷为空的前提下自动导入原 `runtime/app-data`；卷内已有数据时会拒绝自动合并，避免覆盖现有文件。

已有线上版本更新时，不要直接覆盖 `.env`，使用健康门禁更新脚本：

```bash
git pull --ff-only
bash deploy/update.sh

# 仅在本次发布包含 MySQL 镜像修复且已安排维护窗口时使用
bash deploy/update.sh --include-db
```

脚本会先从当前运行容器创建不可变回滚镜像，再构建带唯一版本标签的应用镜像，随后创建并隔离恢复验证数据库与文件备份，最后切换容器并等待健康检查。失败时自动恢复该运行快照；MySQL 使用独立的 `MYSQL_IMAGE_TAG`，普通更新不会重启数据库。`--include-db` 会把正在运行的 MySQL 镜像一并快照、构建、切换和回滚，必须在维护窗口使用，但不会改变 MySQL 主版本或数据卷。

### 本地开发

前置条件：Python 3.11+、Node.js 20.19+、MySQL 8；本地启用 OCR 时还需要 OCRmyPDF、Tesseract 与 Ghostscript。

```bash
# 1. 配置环境
cp fastapi-app/.env.example fastapi-app/.env   # 填 MySQL 连接、AUTH_SECRET、CORS_ORIGINS

# 2. OCR 系统依赖（可选；同时把 OCR_ENABLED 改为 true）
brew install tesseract tesseract-lang ghostscript          # macOS
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim ghostscript  # Debian / Ubuntu

# 3. URL 网页收藏（可选）
# 先在 fastapi-app/.env 中设置：
# CRAWLER_ENABLED=true
# CRAWLER_BASE_URL=http://127.0.0.1:11235
# CRAWLER_API_TOKEN=<openssl rand -hex 32 的输出>
docker compose --env-file fastapi-app/.env -f compose.crawler-dev.yaml up -d

# 4. 后端
cd fastapi-app
python3 -m pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 9090

# 5. 前端（新终端）
cd vue
npm ci
npm run dev    # 开发服务器把 /api 代理到 http://localhost:9090
```

修改 crawler 配置后需要重启后端，Pydantic 仅在进程启动时读取 `.env`。可用 `docker compose --env-file fastapi-app/.env -f compose.crawler-dev.yaml ps` 确认 crawler 已健康；停止时执行同样前缀的 `stop`。

开发环境不配置 `AUTH_SECRET` 时会生成仅本次进程有效的临时密钥；生产必须显式配置。`requirements.txt` 是直接依赖范围，生产镜像使用经过回归验证的 `requirements.lock` 精确版本。

## 架构

```
vue/            Vue 3 + Element Plus 前端（PDF.js / docx-preview 浏览器端渲染）
fastapi-app/    FastAPI 后端
  app/routers/    路由层（REST：/documents /web-imports /notes /highlights /accounts /ai /files）
  app/services/   业务层（文档、网页抓取队列、OCR、高亮、笔记、认证、AI、资源限额）
  app/models/     Tortoise ORM 模型（MySQL）
  app/migrations/ 版本化迁移（校验和保护，禁止改写已执行历史）
  app/storage/    存储抽象（StorageBackend 契约，本地实现）
deploy/         Docker Compose、Caddy、备份与发布门禁脚本
docs/           部署教程
```

关键设计：

- **删除即回收站**：删除文档只标记 `deleted_at`，文件、高亮、笔记关联原样保留；彻底删除走"暂存→事务删行→删文件→失败回滚"，每小时对账循环兜底恢复中断现场。
- **内容版本协议**：每个文档有不可复用的 `content_version`；高亮与 AI 解释都绑定版本，OCR 重处理换版本后旧定位自动失效，防止错位引用。
- **统一来源锚点**（`iknowread.source-anchor/v1`）：高亮与笔记的原文定位用「偏移 + 精确引文 + 前后文」双保险，排版变化后仍可重新解析定位。
- **存储只走契约**：文件操作不直接触盘，全部经 `StorageBackend`；换存储后端不改业务代码。
- **单实例不变式**：内存级保护（账号锁、上传并发门、AI 信号量）依赖单后端实例，启动时以 MySQL `GET_LOCK` 强制保证。
- **网页抓取隔离**：固定版本 Crawl4AI 运行于独立容器，不接触数据库和文件卷；后端以令牌通过内部网络调用，单工作线程持久化任务状态。
- **账号模型唯一**：`role` 区分管理员与用户；角色、格式、路径与必填字段由数据库约束保护。

## 配置参考

常用环境变量（完整清单见 `fastapi-app/.env.example` 与 `app/config.py`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AUTH_SECRET` | 空（必填） | 会话签名密钥；生产留空拒绝启动 |
| `APP_TAG` | `local` | 当前 backend/web 发布标签；线上更新由 `deploy/update.sh` 原子维护 |
| `MYSQL_IMAGE_TAG` | `local` | MySQL 镜像标签，独立于应用发布，避免普通更新重启数据库 |
| `ALLOW_REGISTRATION` | `false` | 自助注册开关 |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_DATABASE` | localhost / 3306 / iknowread / 空 / iknowread | MySQL 连接 |
| `CORS_ORIGINS` | 空 | 可信前端源，逗号分隔；生产禁用 `*` |
| `USER_STORAGE_QUOTA_BYTES` | 2GB | 单账号磁盘配额（含回收站文件） |
| `USER_DOCUMENT_LIMIT` | 200 | 单账号活跃文档数上限 |
| `USER_TOTAL_DOCUMENT_LIMIT` | 400 | 单账号文档总数上限（含回收站） |
| `USER_NOTE_LIMIT` | 10000 | 单账号笔记数上限 |
| `USER_HIGHLIGHT_LIMIT` | 10000 | 单账号高亮总数上限 |
| `DOCUMENT_HIGHLIGHT_LIMIT` | 1000 | 单文档高亮数及单次加载上限 |
| `OCR_ENABLED` | `false` | PDF OCR 队列开关 |
| `CRAWLER_ENABLED` | `false` | URL 网页收藏队列开关；生产需同时使用 Compose 的 `web-import` profile，爬虫故障不会阻断核心阅读服务 |
| `CRAWLER_API_TOKEN` | 空（Docker 自动生成） | 后端访问 Crawl4AI 内部 API 的令牌 |
| `CRAWLER_DNS` | `1.1.1.1` | crawler 出站解析器；企业环境可换成返回真实公网 IP 的组织 DNS，避免 Docker Desktop 合成地址触发 SSRF 拦截 |
| `WEB_IMPORT_WORKERS` | 1 | 网页导入并发 worker 数，允许 1–4；任务通过数据库条件更新原子领取 |
| `AI_CONFIG_KEY` | 自动生成 | API Key 加密密钥；多实例必须一致 |
| `AI_GLOBAL_CONCURRENCY` | 3 | 全站 AI 并发上限 |

## 验证

```bash
# 后端（静态检查 + 单元测试）
cd fastapi-app
ruff check app tests scripts
python3 -m pytest

# 已运行实例的数据库约束检查
python3 scripts/database_security_check.py

# 前端（静态检查 + 测试 + 生产构建）
cd ../vue
npm ci && npm run check

# 正式发布门禁（构建生产镜像，并启动一次性隔离栈做重启与数据验收）
cd ..
bash deploy/release-check.sh
```

`deploy/release-check.sh` 会组合 `deploy/compose.verify.yaml` 与 `fastapi-app/scripts/docker_smoke_check.py`，在独立项目名与一次性卷中验证生产镜像、真实图片型 PDF 的 OCR 文字层、迁移、HTTPS、会话与角色隔离、上传、笔记、高亮、进程重启持久性及数据库约束，完成后自动删除测试容器和卷。后端 `fastapi-app/app/api_paths.py` 是 API 方法与路径的单一来源；`fastapi-app/scripts/document_contract.py` 生成并校验前端 `vue/src/api/apiContract.json`，测试同时核对 FastAPI OpenAPI 路由，防止前后端路径在演进中失配。

## 安全与边界

- 密码 PBKDF2-SHA256（600k 迭代）；会话 HMAC 签名并绑定密码指纹，改密或退出立即吊销历史令牌。
- 登录、验证码、注册分别按客户端 IP 与账号双维度滑动窗口限速；验证码短时一次性。
- 上传有内容级校验（PDF 结构 / DOCX zip-bomb 三重防护）与全站并发门；账号配额与服务器保留空间双重限额。
- AI 外呼禁用自动重试与重定向跟随，响应字节封顶；API Key 加密存储，读取接口只返回 `has_api_key`。
- 所有接口需登录；账号身份只从会话读取，文档 / 笔记 / 高亮 / 配置按账号隔离。

## 运维

- **备份**：`deploy/backup.sh`（flock 防并发，停写保证数据库与文件快照一致）；`deploy/verify-backup.sh` 验证备份可恢复。
- **发布门禁**：`deploy/release-check.sh` 在发布前跑完整校验。
- **线上更新**：`deploy/update.sh` 先备份，再按唯一镜像标签切换并等待健康检查；失败自动恢复上一应用版本。
- **AI Key 备份提醒**：`AI_CONFIG_KEY` 默认生成于 `fastapi-app/data/.ai-config-key`，与数据库需分别持久化；丢失后各账号需重填 API Key。

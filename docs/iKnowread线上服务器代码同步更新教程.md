# iKnowread 本地代码同步与线上服务器安全更新教程

> **适用范围**：本地开发完成后，把已经测试并提交的源码同步到一台正在运行 iKnowread 的 Ubuntu Docker 服务器，并完成带备份、健康检查和自动回滚的线上更新。
>
> **不适用范围**：首次安装 Docker、首次部署、迁移到空服务器、数据库大版本升级，以及仍依赖 `compose.test.yaml` 将 Web 绑定到 `127.0.0.1:8443` 的备案期私有测试环境。首次部署和灾难恢复请使用项目的《iKnowread 通用 Docker 部署教程》。
>
> **当前依据**：仓库根目录的 `compose.yaml`，以及 `deploy/release-check.sh`、`deploy/update.sh`、`deploy/backup.sh` 和 `deploy/verify-backup.sh`。脚本行为变化后，应先更新脚本，再同步修订本文。

## 1. 先理解更新链路

一次线上更新包含四个互相独立的对象：

1. **源码**：以本地 Git 提交为唯一来源，通过 `rsync` 同步到服务器。
2. **生产配置**：服务器根目录 `.env`，包含域名、密钥、数据库密码和当前镜像标签；更新时必须保留。
3. **持久化数据**：MySQL 命名卷、应用数据卷、Caddy 证书卷和 `backups/`；源码同步不得覆盖或删除。
4. **运行版本**：容器实际使用的镜像。源码同步完成并不会改变正在运行的容器，只有 `deploy/update.sh` 通过健康门禁后才会切换版本。

标准链路为：

```text
本地提交
  → 目标架构发布检查与镜像漏洞扫描
  → rsync 预演
  → 本地源码同步到服务器中转目录
  → 中转目录精确同步到 /opt/iknowread
  → update.sh 创建运行镜像快照
  → 创建并隔离恢复验证完整备份
  → 构建唯一版本标签
  → 切换容器并等待健康检查
  → 浏览器业务验收
```

该链路遵循以下约束：

- 不从服务器反向合并 Dockerfile。仓库中的 Dockerfile 是唯一来源。
- 不手工覆盖可变的 `local` 镜像标签。
- 不用 `docker compose up --force-recreate` 绕过更新脚本。
- 不覆盖服务器 `.env`，也不把本地开发数据同步到线上。
- 不执行 `docker compose down -v`、`docker volume prune` 或其他可能删除正式卷的命令。
- 每次发布使用唯一标签，使源码、镜像、备份和故障记录可以对应。

## 2. 路径和占位符

本文使用以下占位符，执行前替换为真实值：

| 占位符 | 示例含义 |
|---|---|
| `ubuntu@你的服务器公网IP` | SSH 登录账号和服务器地址 |
| `/Users/你的用户名/项目/iKnowread` | 本地仓库根目录 |
| `/home/ubuntu/iknowread-upload` | 服务器源码中转目录 |
| `/opt/iknowread` | 服务器正式项目目录 |
| `read.example.com` | 已解析到服务器的正式域名 |
| `<发布标签>` | 本次生成的唯一版本标签 |

本文默认：

- 本地开发机是 macOS；Windows WSL2 和 Linux 可使用相同的 Bash/rsync 思路。
- 正式服务器是 Ubuntu，Docker 命令使用 `sudo`。
- 服务器已经存在健康的 iKnowread 部署和根目录 `.env`。
- 正式站点通过 `compose.yaml` 发布 80/443 端口。

## 3. 发布前停手条件

出现以下任一情况时，先解决问题，不要继续同步或切换容器：

- 本地改动尚未完成，或无法说明本次发布包含哪些文件。
- 本地完整发布检查失败。
- 当前线上 `db`、`backend` 或 `web` 没有运行。
- 服务器磁盘空间不足以同时保存构建缓存、新镜像、回滚镜像和完整备份。
- 服务器根目录 `.env` 缺失。
- `rsync -n` 预演出现不认识的 `*deleting` 项。
- 当前仍使用备案期 `compose.test.yaml` 私有端口覆盖。
- 有其他更新或备份任务正在运行。

`deploy/update.sh` 要求现有容器正在运行，以便从**实际运行镜像**建立可信回滚点。它不是修复已损坏部署的脚本。

## 4. 一次性准备

### 4.1 本地工具

在本地终端确认：

```bash
git --version
rsync --version
docker version
docker compose version
```

Docker Desktop 必须已经启动。`deploy/release-check.sh` 会构建四个生产镜像并启动隔离测试栈，需要足够的磁盘和内存。

### 4.2 服务器工具

SSH 登录服务器：

```bash
ssh ubuntu@你的服务器公网IP
```

检查依赖：

```bash
command -v docker
command -v python3
command -v rsync
command -v flock
sudo docker info >/dev/null
sudo docker compose version
```

缺少基础工具时安装：

```bash
sudo apt-get update
sudo apt-get install -y python3 rsync util-linux
```

创建只存放源码的中转目录：

```bash
mkdir -p /home/ubuntu/iknowread-upload
test -w /home/ubuntu/iknowread-upload
```

中转目录不得存放数据库备份、生产 `.env`、管理员密码或用户文件。

## 5. 本地整理并锁定发布版本

进入本地仓库：

```bash
cd /Users/你的用户名/项目/iKnowread
```

检查改动：

```bash
git status --short
git diff --check
git diff --stat
```

先完成代码审查和必要测试，再提交本次稳定版本：

```bash
git add path/to/changed-file
git commit -m "描述本次更新"
```

确认工作区干净：

```bash
test -z "$(git status --porcelain)" && echo "工作区干净"
```

生成唯一发布标签：

```bash
RELEASE_TAG="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short=12 HEAD)"
printf '%s\n' "$RELEASE_TAG"
```

标签只允许字母、数字、点、下划线和连字符。保存终端打印的值，后文用 `<发布标签>` 表示。时间前缀让同一提交的再次发布仍能获得新标签，提交号负责对应源码。

如果无法提交，不应把临时工作区直接发布到生产服务器。

## 6. 按服务器架构执行完整发布检查

先在服务器确认 CPU 架构：

```bash
uname -m
```

映射关系：

| `uname -m` | 发布检查参数 |
|---|---|
| `x86_64` | `linux/amd64` |
| `aarch64` 或 `arm64` | `linux/arm64` |

在本地项目根目录执行。腾讯云常见 x86 服务器示例：

```bash
TARGET_PLATFORM=linux/amd64 bash deploy/release-check.sh --scan
```

ARM64 服务器使用：

```bash
TARGET_PLATFORM=linux/arm64 bash deploy/release-check.sh --scan
```

脚本应完成：

- Compose 和交付清单校验；
- MySQL、backend、web、crawler 四个生产镜像构建；
- Python 静态检查、类型检查、单元测试和覆盖率门禁；
- 前端静态检查、测试、生产依赖审计和构建；
- OCR、Caddy、Crawler 和关键运行时校验；
- 隔离 Docker 栈端到端测试；
- 四个镜像的 Docker Scout 严重漏洞扫描。

必须看到最后的“发布前检查全部通过”。未带 `--scan` 只表示跳过了实际镜像漏洞扫描，不能作为正式发布的完整门禁。

Apple 芯片 Mac 检查 `linux/amd64` 时会使用跨架构模拟，速度通常较慢。不能因为耗时而取消目标架构检查。

## 7. 更新前检查线上状态

在服务器执行：

```bash
cd /opt/iknowread
sudo test -f .env
sudo docker compose ps
df -h /
sudo docker system df
free -h
```

继续前应确认：

- `db` 和 `backend` 为 `healthy`；
- `web` 为运行状态；
- 若 `.env` 中 `CRAWLER_ENABLED=true`，`crawler` 和 `crawler-gateway` 也已经运行；
- 根分区留有足够空间；
- 80/443 当前由预期的 Web 容器提供。

可检查当前标签而不显示其他机密：

```bash
sudo awk -F= '$1 == "APP_TAG" || $1 == "MYSQL_IMAGE_TAG" {print}' .env
```

旧部署可能还没有这两个字段，更新脚本会把缺失值按 `local` 处理并在成功切换时原子写入。

## 8. 本地同步到服务器中转目录

仓库提供统一排除文件 `deploy/rsync-excludes.txt`。它保护生产密钥、持久化数据、备份、依赖目录和构建产物，同时允许 `.env.example`、前端生产环境文件和项目文档正常同步。

### 8.1 必须先预演

在本地仓库根目录执行：

```bash
rsync -avzcn \
  --no-owner \
  --no-group \
  --delete-delay \
  --itemize-changes \
  --human-readable \
  --stats \
  --exclude-from=deploy/rsync-excludes.txt \
  ./ ubuntu@你的服务器公网IP:/home/ubuntu/iknowread-upload/
```

参数含义：

- `-a`：递归并保留常规文件属性；
- `-v`：显示变化；
- `-z`：传输压缩；
- `-c`：按内容校验和判断变化；
- `-n`：只预演，不写入；
- `--delete-delay`：删除目标中源码已不存在的非排除文件；
- `--exclude-from`：两段同步共用同一份保护规则。

逐行检查输出，特别是所有 `*deleting` 行。以下内容不应出现在上传或删除清单中：

- 根目录 `.env`；
- `fastapi-app/.env` 和 `fastapi-app/data/`；
- `runtime/`、`backups/`；
- `compose.test.yaml`、`deploy/Caddyfile.test`；
- `vue/node_modules/`、`vue/dist/`；
- 本地数据库、缓存和日志。

如果出现未知文件，先修订 `deploy/rsync-excludes.txt`，重新提交，再重新运行完整发布检查和预演。

### 8.2 正式上传

预演确认无误后，去掉 `-n`：

```bash
rsync -avzc \
  --no-owner \
  --no-group \
  --delete-delay \
  --itemize-changes \
  --human-readable \
  --stats \
  --exclude-from=deploy/rsync-excludes.txt \
  ./ ubuntu@你的服务器公网IP:/home/ubuntu/iknowread-upload/
```

上传成功只代表中转目录源码已更新，线上容器仍在运行旧镜像。

## 9. 中转目录精确同步到正式项目目录

SSH 登录服务器后，先检查中转目录包含本次关键文件：

```bash
ls -lah /home/ubuntu/iknowread-upload
test -f /home/ubuntu/iknowread-upload/compose.yaml
test -f /home/ubuntu/iknowread-upload/deploy/update.sh
test -f /home/ubuntu/iknowread-upload/deploy/rsync-excludes.txt
```

### 9.1 正式目录同步预演

```bash
sudo rsync -avcn \
  --no-owner \
  --no-group \
  --delete-delay \
  --itemize-changes \
  --human-readable \
  --stats \
  --exclude-from=/home/ubuntu/iknowread-upload/deploy/rsync-excludes.txt \
  /home/ubuntu/iknowread-upload/ \
  /opt/iknowread/
```

确认 `.env`、运行数据、备份和任何已知的服务器本地覆盖文件都不会被修改或删除。未知的 `*deleting` 项必须先调查。

### 9.2 正式同步

```bash
sudo rsync -avc \
  --no-owner \
  --no-group \
  --delete-delay \
  --itemize-changes \
  --human-readable \
  --stats \
  --exclude-from=/home/ubuntu/iknowread-upload/deploy/rsync-excludes.txt \
  /home/ubuntu/iknowread-upload/ \
  /opt/iknowread/
```

`rsync` 不是整个目录的原子切换，复制过程中源码可能短暂处于新旧混合状态。现有容器从已经构建的镜像运行，因此同步期间不会直接加载这些宿主机源码。不要同时运行第二次同步或镜像构建。

同步后检查脚本语法和正式 Compose：

```bash
cd /opt/iknowread
sudo bash -n deploy/update.sh
sudo bash -n deploy/backup.sh
sudo bash -n deploy/verify-backup.sh
sudo bash -n deploy/release-check.sh
sudo docker compose config --quiet
```

这里不得重新运行 `deploy/init-env.py`，否则可能覆盖已有服务器配置和密钥。

## 10. 选择普通更新或包含 MySQL 镜像更新

| 本次变化 | 命令选择 |
|---|---|
| 前端、后端、Python/Node 依赖、Caddy、Crawler 或普通配置 | 普通更新 |
| 仅新增后端数据库迁移文件 | 普通更新；迁移由后端启动流程执行 |
| `deploy/Dockerfile.mysql`、MySQL 基础镜像 digest、gosu 或 MySQL 运行时发生变化 | 在维护窗口使用 `--include-db` |
| MySQL 主版本升级 | 不使用本教程；先制定独立升级与恢复演练方案 |

### 10.1 普通更新

```bash
cd /opt/iknowread
RELEASE_TAG='把本地生成的发布标签粘贴到这里'
sudo bash deploy/update.sh "$RELEASE_TAG"
```

### 10.2 包含 MySQL 镜像更新

该过程会重建和切换数据库容器，应安排维护窗口：

```bash
cd /opt/iknowread
RELEASE_TAG='把本地生成的发布标签粘贴到这里'
sudo bash deploy/update.sh --include-db "$RELEASE_TAG"
```

**本轮 Docker 优化首次发布包含 `deploy/Dockerfile.mysql` 变更，应使用第二条命令。后续未再修改 MySQL 镜像时恢复普通更新。**

不要重复使用旧标签。服务器通常不包含 `.git`，显式传入本地生成的标签可以避免自动标签退化为 `时间-source`。

## 11. 更新脚本实际执行的工作

`deploy/update.sh` 会依次：

1. 检查 `.env`、Docker、Python、Compose 和 `flock`。
2. 获取更新互斥锁，阻止两个发布同时执行。
3. 读取当前 `APP_TAG`、`MYSQL_IMAGE_TAG` 和 `CRAWLER_ENABLED`。
4. 从正在运行的容器镜像创建唯一的 `rollback-*` 标签。
5. 拒绝覆盖已存在的发布镜像标签。
6. 校验 Compose 并构建新版本镜像。
7. 调用 `deploy/backup.sh`，短暂停止后端写入。
8. 导出数据库，打包整个应用数据、部署配置和源码。
9. 校验 SHA256，并把 SQL 导入一次性 MySQL 容器做隔离恢复验证；数据库已执行的迁移必须是备份源码迁移序列的连续前缀，已有校验和必须匹配，允许新源码包含尚未执行的待发布迁移。
10. 只有备份验证成功才创建 `COMPLETE` 标记并继续激活。
11. 原子更新 `.env` 中的应用和 MySQL 镜像标签。
12. `docker compose up -d --wait --wait-timeout 300` 切换并等待健康检查。
13. 激活阶段失败时把 `.env` 和容器恢复到本次运行镜像快照。

普通更新不会重启 MySQL。`--include-db` 会把当前 MySQL 运行镜像一并建立回滚标签、构建和切换，但不会替换数据卷，也不会自动升级 MySQL 主版本。

备份会短暂停止 backend，因此发布期间可能出现短时间接口不可用。应选择低使用量时段，并提前通知相关用户。

## 12. 更新后的自动与人工验收

脚本成功结束只证明容器健康检查通过，还需完成业务验收。

### 12.1 容器、标签和日志

```bash
cd /opt/iknowread
sudo docker compose ps
sudo awk -F= '$1 == "APP_TAG" || $1 == "MYSQL_IMAGE_TAG" {print}' .env
sudo docker compose logs --tail=150 backend web db
sudo docker stats --no-stream
df -h /
```

如果 `.env` 中 `CRAWLER_ENABLED=true`，追加检查：

```bash
sudo docker compose --profile web-import ps
sudo docker compose --profile web-import logs --tail=100 crawler crawler-gateway
```

### 12.2 HTTP 验收

将域名替换为正式域名：

```bash
curl -fsS https://read.example.com/healthz
curl -fsS https://read.example.com/api/ready
```

检查：

- HTTP 自动跳转到 HTTPS；
- 浏览器证书受信任且域名匹配；
- `/healthz` 可访问；
- `/api/ready` 返回就绪状态；
- 3306、9090 和 5173 未向公网开放。

### 12.3 浏览器业务验收

至少验证：

1. 管理员和普通用户可以登录、退出。
2. 文档列表、搜索和分页正常。
3. 上传一个小型 PDF、DOCX 和 Markdown 文件并打开阅读。
4. PDF 翻页、缩放、搜索和高亮正常。
5. DOCX、Markdown 内容渲染正常。
6. 笔记新增、修改、导出和删除正常。
7. 阅读进度在刷新后仍然存在。
8. 头像上传、个人资料和密码修改正常。
9. AI 配置和调用使用测试账号自己的 Key 验证，不在日志或截图中泄露 Key。
10. 启用网页收藏时，验证正常网址导入、任务状态和结果文档。
11. 页脚备案号和工信部链接显示正确。

出现 500、持续 429、登录循环、文档串页、上传后不可读或容器反复重启时，不应宣布发布完成。

## 13. 回滚原则

### 13.1 激活阶段失败

更新脚本会自动回滚到开始发布时实际运行的镜像，并输出回滚标签。先查看：

```bash
cd /opt/iknowread
sudo docker compose ps
sudo docker compose logs --tail=200 backend web db
sudo awk -F= '$1 == "APP_TAG" || $1 == "MYSQL_IMAGE_TAG" {print}' .env
```

如果自动回滚也未恢复健康，停止继续发布，保留脚本输出、`rollback-*` 镜像和最新带 `COMPLETE` 的备份进行诊断。

### 13.2 更新成功后业务验收失败

先记录更新脚本输出的 `rollback-*` 标签。只有确认新迁移与旧程序兼容时，才进行应用镜像回滚：

1. 备份当前 `.env` 到仅 root 可读的受控目录。
2. 将 `.env` 的 `APP_TAG` 改为本次 `rollback-*` 标签。
3. 如果本次使用了 `--include-db`，同时把 `MYSQL_IMAGE_TAG` 改为同一回滚标签。
4. 执行：

```bash
sudo docker compose up -d --wait --wait-timeout 300 --no-build
sudo docker compose ps
```

5. 重新检查 `/api/ready` 和核心业务。

如果新版本已经执行了与旧程序不兼容的数据库迁移，不能只回滚镜像。应按通用部署教程使用本次发布前生成的完整备份恢复；恢复会丢失备份时间点之后的新写入，因此恢复前必须另存当前状态并明确业务影响。

## 14. 备案期私有测试环境

旧教程使用服务器本地的 `compose.test.yaml` 和 `deploy/Caddyfile.test`，把 Web 绑定到 `127.0.0.1:8443`。当前 `deploy/update.sh` 的标准接口没有显式接收额外 Compose 文件，而默认 `compose.yaml` 会发布公网 80/443。

因此：

- 已正式上线的公网环境使用本文标准流程。
- 仍处于备案期私有测试环境时，不得直接运行本文第 10 节命令。
- 不得为了沿用旧流程而改回手工 `--force-recreate`，这会绕过备份验证、更新锁、唯一镜像标签、健康门禁和自动回滚。
- 应先为更新脚本实现并测试明确的 Compose 覆盖参数，使更新、备份、激活、健康检查和回滚全过程使用同一组 Compose 文件，再执行发布。

`deploy/rsync-excludes.txt` 会继续保护 `compose.test.yaml` 和 `deploy/Caddyfile.test`，但“文件不会被覆盖”不等于“更新脚本已经正确应用这些文件”。

## 15. Crawler 启停边界

当服务器 `.env` 已经设置 `CRAWLER_ENABLED=true`，更新脚本会自动使用 `web-import` profile，并构建和更新 crawler。它还要求更新前的 `crawler`、`crawler-gateway` 已经运行，以便建立可信回滚点。

因此不要在普通更新前直接把 `CRAWLER_ENABLED=false` 改成 `true`。首次启用 Crawler 属于部署拓扑变化，应按通用部署教程完成配置、隔离验证和首次启动；确认 crawler 与 gateway 健康后，后续更新才能使用本文标准流程。

修改 Crawler 配置后需要重新创建后端容器，单纯 `restart` 不会重新加载 Compose 环境。

## 16. 常见失败及处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `flock` 不存在 | 服务器缺少 `util-linux` | `sudo apt-get install -y util-linux` |
| 提示已有更新任务 | 另一个 `update.sh` 持有更新锁 | 等待现有任务结束，先查进程和日志，不删除锁文件冒险并发 |
| 发布标签已存在 | 重复使用标签或上次构建留下同名镜像 | 生成新的唯一标签；不要覆盖旧标签 |
| 现有服务未运行 | 无法为实际运行版本创建可信回滚点 | 先恢复当前部署健康，再发布 |
| 缺少 `iknowread-mysql:<标签>` | `.env` 标签与本机镜像不一致 | 停止发布，核对当前数据库容器镜像和 `.env`；不要随意重打标签 |
| 备份没有 `COMPLETE` | 归档、校验、数据库恢复或 backend 恢复健康失败 | 查 `backup.sh` 输出和磁盘空间；备份通过前不会激活新版 |
| 新容器健康检查失败 | 配置、迁移、运行时或依赖异常 | 脚本自动回滚；检查 backend/web/db 日志 |
| `rsync` 预演删除未知文件 | 文件放错目录或排除规则不完整 | 暂停，确认文件归属并更新排除规则 |
| 本地检查只显示“跳过 Scout” | 没有传 `--scan` | 使用 `bash deploy/release-check.sh --scan` 重跑 |
| Apple 芯片构建 amd64 很慢 | 跨架构模拟开销 | 等待完成或在可信的 amd64 CI 执行相同门禁 |
| 磁盘快速增长 | 新镜像、回滚镜像、构建缓存和备份并存 | 稳定观察后，先做异地备份，再按保留策略清理明确不再需要的对象 |

## 17. 清理原则

发布完成后不要立即删除回滚镜像和最新备份。至少经过一个明确的稳定观察窗口，并确认：

- 核心业务验收通过；
- 没有持续错误日志；
- 最新完整备份已复制到服务器之外并验证；
- 不再需要回到该版本。

只查看空间占用：

```bash
sudo docker system df
sudo docker image ls 'iknowread-*'
sudo du -sh /opt/iknowread/backups/* 2>/dev/null
```

可以在确认后交互式清理闲置构建缓存：

```bash
sudo docker builder prune
```

不要使用 `docker system prune --volumes`，不要批量删除所有 `rollback-*`，不要删除尚未转存的完整备份。

## 18. 每次更新最短清单

- [ ] 本地改动已审查、测试并提交，工作区干净。
- [ ] 已记录服务器架构并运行 `TARGET_PLATFORM=... bash deploy/release-check.sh --scan`。
- [ ] 发布检查最后显示“发布前检查全部通过”。
- [ ] 已生成并保存唯一 `<发布标签>`。
- [ ] 线上现有容器健康，磁盘和内存余量满足构建与备份需要。
- [ ] 本地到中转目录的 `rsync -n` 预演已审查。
- [ ] 中转目录到 `/opt/iknowread` 的 `rsync -n` 预演已审查。
- [ ] `.env`、数据、备份和服务器本地覆盖文件均受到排除规则保护。
- [ ] `docker compose config --quiet` 通过。
- [ ] 已根据 MySQL 镜像是否变化选择普通更新或 `--include-db`。
- [ ] `deploy/update.sh` 成功，输出新标签、回滚标签和完整备份。
- [ ] 容器、HTTPS、`/api/ready`、日志和资源正常。
- [ ] 登录、文档上传/阅读、笔记、高亮、进度、资料和相关可选功能已验收。
- [ ] 最新完整备份已计划或已经转存到服务器之外。

## 19. 标准命令速查

本地：

```bash
cd /Users/你的用户名/项目/iKnowread
git status --short
git diff --check
TARGET_PLATFORM=linux/amd64 bash deploy/release-check.sh --scan
RELEASE_TAG="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short=12 HEAD)"
printf '%s\n' "$RELEASE_TAG"

rsync -avzcn --no-owner --no-group --delete-delay \
  --itemize-changes --human-readable --stats \
  --exclude-from=deploy/rsync-excludes.txt \
  ./ ubuntu@你的服务器公网IP:/home/ubuntu/iknowread-upload/

# 审查预演输出后才执行：
rsync -avzc --no-owner --no-group --delete-delay \
  --itemize-changes --human-readable --stats \
  --exclude-from=deploy/rsync-excludes.txt \
  ./ ubuntu@你的服务器公网IP:/home/ubuntu/iknowread-upload/
```

服务器：

```bash
sudo rsync -avcn --no-owner --no-group --delete-delay \
  --itemize-changes --human-readable --stats \
  --exclude-from=/home/ubuntu/iknowread-upload/deploy/rsync-excludes.txt \
  /home/ubuntu/iknowread-upload/ /opt/iknowread/

# 审查预演输出后才执行：
sudo rsync -avc --no-owner --no-group --delete-delay \
  --itemize-changes --human-readable --stats \
  --exclude-from=/home/ubuntu/iknowread-upload/deploy/rsync-excludes.txt \
  /home/ubuntu/iknowread-upload/ /opt/iknowread/

cd /opt/iknowread
sudo docker compose config --quiet
RELEASE_TAG='把本地生成的发布标签粘贴到这里'
sudo bash deploy/update.sh "$RELEASE_TAG"
# 本轮首次发布包含 MySQL 镜像优化时改用：
# sudo bash deploy/update.sh --include-db "$RELEASE_TAG"

sudo docker compose ps
curl -fsS https://read.example.com/api/ready
```

执行速查命令前仍须完成正文中的状态检查、预演审查、命令选择和业务验收。速查表不能代替发布判断。

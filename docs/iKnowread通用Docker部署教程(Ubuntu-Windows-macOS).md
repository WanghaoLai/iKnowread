# iKnowread 通用 Docker 部署教程（Ubuntu / Windows / macOS）

> **文档用途**：在不改变 iKnowread 项目现有部署约定的前提下，统一 Docker 部署主流程，并把操作系统差异集中到独立章节。既适合第一次部署，也适合后续更新、迁移和故障恢复。
>
> **依据与范围**：依据原《Ubuntu-24.04-Docker部署教程》重构（原稿核对日期：2026-10-19），沿用仓库现有 `compose.yaml`、`deploy/`、`.dockerignore` 等文件及其脚本接口。本文**没有修改或执行这些脚本，也没有连接你的实际服务器**；实际运行前仍须以当前仓库、镜像及验收输出为准。

## 使用前先选部署方式

| 你正在使用的系统 | Docker 运行方式 | 推荐用途 | 本教程对应章节 |
|---|---|---|---|
| **Ubuntu 24.04 LTS（云服务器 / 裸机）** | Docker Engine + Compose 插件 | **正式公网部署，推荐** | §3.1 → 公共阶段 |
| **Windows 10/11（符合 Docker 官方要求）** | Docker Desktop + **WSL 2 / Linux 容器** | 本地开发、构建、隔离验收；有公网域名及完整网络条件时可做专门验证 | §3.2 → 公共阶段 |
| **macOS（Apple 芯片 / Intel）** | Docker Desktop + Linux 容器 | 本地开发、构建、隔离验收；有公网域名及完整网络条件时可做专门验证 | §3.3 → 公共阶段 |
| **其他 Linux 发行版** | 官方支持的 Docker Engine + Compose | 可以复用公共阶段；安装、防火墙、包管理器须按本系统适配 | §3.4 → 公共阶段 |

**重要区分**：本项目正式入口依赖能够申请受信任证书的公网 HTTPS 域名，且生产 Cookie **必须带 `Secure` 属性**。因此在 Mac/Windows 本机跑通 Docker、执行隔离发布门禁，**不等于**已经通过公网登录、证书自动续期、带宽和备份验收。一般做法是 Mac/Windows 用作开发和交叉架构构建机，Ubuntu 用作长期在线的生产主机。如果确需 Windows/macOS 直连公网运行，仍必须达到相同的域名、80/443 入站、持久化、供电、备份与服务自启动标准；Docker Desktop 不等同于无人值守的服务器服务。

### 固定的项目边界（所有平台一致）

- **OCR 首发默认关闭**：应用、`.env` 初始化和 Compose 维持 `OCR_ENABLED=false`。扫描型 PDF 可以查看图像，但默认没有可选择的 OCR 文字层；仅在完成专项测试后才考虑开启。
- **不预置平台级 LLM API Key**：部署者不填写统一 Key；各用户在“AI服务 → API配置”自行录入厂商、模型、Key、Base URL 与额度，并自行确认计费和数据处理规则。
- **注册默认关闭**：`ALLOW_REGISTRATION=false`，默认由管理员创建账号。
- **正式登录必须使用受信任 HTTPS**：Cookie 强制 `Secure`，不能通过 `DEBUG=true`、明文 HTTP 或 IP 地址绕开。
- **暂缓项照实记录风险**：异地备份、自动留存与失败告警、公网监控、目标机器压力测试和正式域名长期验收，原项目首发决定暂缓；不是已经实现或不需要做。尤其同盘备份无法应对云盘或整机损坏。
- **数据必须一起保存**：数据库、文档、隐藏 AI 解密密钥、会话配置相互关联，不得只迁移数据库。
- **从空系统开始部署**：本教程主流程不会自动搬运本机账号、文档、笔记或 AI 配置；历史数据须走专用迁移流程。

### 新手执行路线：每一关通过后再继续

| 阶段 | 做什么 | 看到什么才继续 |
|---|---|---|
| **阶段一：准备** | 选系统与部署模式、安装 Docker、核对架构与磁盘、准备域名、端口和项目 | Docker / Compose 版本满足要求；`hello-world` 成功；项目必需文件齐全；公网正式部署时 DNS/安全组正确 |
| **阶段二：配置与构建** | 生成 `.env`、确认数据目录和默认边界、检查 Compose、运行发布门禁与扫描 | `.env` 权限/ACL 安全、域名正确、OCR 和注册关闭；`docker compose config --quiet` 成功；发布检查输出“发布前检查全部通过”；漏洞扫描真实通过 |
| **阶段三：启动与验收** | 启动服务、查看健康状态、正式域名 HTTPS 检查、浏览器核心业务验收 | db/backend `healthy`、web `Up`；`/api/ready` 为 `ready`；管理员登录、上传、笔记、持久化等检查通过 |
| **阶段四：维护与恢复** | 查看日志、备份并验证、升级、回滚、恢复演练、整理风险清单 | 备份含 `COMPLETE` 且 SHA256 / 隔离恢复验证通过；明确能恢复什么、哪些风险未解决 |

**停手规则**：遇到 `error`、`failed`、`unhealthy`、`Killed` 或退出码 `137`，先查看原因，**不要反复删卷或执行 `docker compose down -v`**。命令通常以退出状态码 `0` 为成功，健康检查和业务验收须另外确认。

### 命令标注及路径约定

| 标记 | 在哪里执行 | Docker 权限与路径约定 |
|---|---|---|
| **[Ubuntu 服务器]** | SSH 登录后的 Ubuntu Shell | 默认 `sudo docker ...`，项目示例为 `/opt/iknowread` |
| **[Windows PowerShell]** | Windows 主机 PowerShell | 管理 WSL、检查端口、用 `ssh`/`scp` 传文件；**不在 PowerShell 直接运行 `.sh`** |
| **[Windows WSL2]** | Ubuntu WSL2 发行版 Shell | 启用 Docker Desktop 的 WSL 集成后通常执行 `docker ...`（不加 `sudo`）；项目建议放 `~/projects/iKnowread`，不放 `/mnt/c/...` |
| **[macOS 终端]** | macOS Terminal / iTerm | 先启动 Docker Desktop，执行 `docker ...`（不加 `sudo`）；项目示例 `~/projects/iKnowread` |
| **[跨平台：Docker CLI]** | Ubuntu / Windows WSL2 / macOS 对应 Shell | 命令语义相同，但 Ubuntu Docker 通常使用 `sudo`；碰到共同示例中的 `sudo docker` 时，Docker Desktop 环境去掉 `sudo` |
| **[浏览器/云控制台]** | 当前设备上的 UI | 改 DNS、安全组、服务器规则以及做业务验收 |

以下示例用 `read.example.com`、`you@example.com`、`你的服务器公网IP` 作为**占位符，执行前必须替换**。上传和恢复时的日期目录同样须替换为真实生成值。Linux 容器的 `/app/data`、MySQL 内部 3306 端口、容器 UID/GID **不因宿主操作系统改变**。

---

## 阶段一：准备（系统、Docker、项目与网络）

### 1. 部署架构与运行边界

目标 Docker 主机只需要准备 Docker 环境，无须在宿主机额外运行项目的 Node.js、Python 服务或 MySQL 服务；**运行初始化脚本时仍需要 Python 3**（Ubuntu / WSL 可单独安装；macOS 可使用已有的 Python 3）。

```text
浏览器 → https://你的域名:443
                 ↓
            Caddy 容器（web）
              ├─ 网页和静态文件
              └─ /api/* → FastAPI 容器（backend，9090）
                                ├─ MySQL 容器（db，3306）
                                ├─ 文档、头像和每账号独立的 AI 加密配置
                                ├─ OCR 派生文件（首发关闭）
                                └─ 通过 HTTPS 请求用户自己配置的 AI 厂商
```

前端构建阶段使用 Node.js，构建完成后由 Caddy 直接提供网页。Node.js 不会在生产容器中持续运行。数据库和后端不发布公网端口，只由 Docker 内部网络访问。

项目中的生产登录 Cookie 设置了 `Secure`，所以**正式使用必须通过 HTTPS 登录**。直接打开 `http://服务器IP` 不是本教程的登录方案，也不要为此把 `DEBUG` 改成 `true`。

生产镜像的 Python、Node、MySQL、Go 和 Alpine 基础镜像使用 digest 固定，Python 完整依赖闭包保存在 `fastapi-app/requirements.lock`，前端由 `package-lock.json` 和 `npm ci` 固定。Web 使用 Go 1.26.9 构建 Caddy 2.11.7；MySQL 运行镜像移除了非运行必需的 mysql-shell，并用 Go 1.26.9 重建 gosu。固定版本仍不等于字节级可复现，因此每次发布都要重新运行依赖审计和最终镜像扫描。

Caddy 以 UID/GID `10002:10002` 运行，根文件系统只读，并移除全部 Linux capabilities。后端以 `10001:10001` 运行并采用相同的只读与能力收紧。HTTPS 响应先使用 `max-age=86400` 的短周期 HSTS；只有真实域名连续稳定并确认子域策略后，才考虑延长或加入 `includeSubDomains`。

#### 1.1 原部署规格示例：4 核 / 4GB / 40GB / 3Mbps

原教程采用 **Ubuntu 24.04、4 vCPU / 4GB 内存 / 40GB SSD / 3Mbps 带宽 / 300GB 月流量**作为一台示例服务器，不是所有操作系统的固定硬件要求。这一规格适合尝试个人或小团队的轻量阅读场景，但不能仅靠标称参数保证并发容量。Docker Desktop 还要给 Windows/macOS 宿主机与 Linux 虚拟环境预留资源；实际容量以测试为准。

| 项目 | 原示例 Compose 设置与原因 |
|---|---|
| 主机 CPU | 4 vCPU；后端仍限制为 1.25 核和单进程，其余算力留给 MySQL、Caddy、Docker、系统和构建任务 |
| MySQL | 600MiB 内存上限、128MiB InnoDB 缓冲池、最多 30 个连接 |
| FastAPI | 850MiB 内存上限、单进程，避免重复启动后台 OCR 队列 |
| Caddy | 128MiB 内存上限，负责静态文件、HTTPS、反向代理 |
| 系统余量 | 容器内存上限合计约 1.54GiB；原 Ubuntu 示例有约 2GiB 留给系统、Docker 与缓存；其他主机必须重新核算 |
| Swap | 建议配置 2GiB，缓冲临时峰值；它不等同于真实内存 |
| OCR | 默认关闭，稳定运行后按需开启，文档并发和文档内部并发均为 1 |
| AI | 调用外部 API，不在这台服务器上运行大模型 |
| 上传 | 单文件 50MiB；multipart 解析前最多 3 个并发，排队超过 1 秒返回 429 |
| 日志 | 每个容器最多约 3 × 10MB，避免日志无限增长 |

`mem_limit` 限制运行中的容器，**不会自动限制镜像构建阶段的内存**。因此发布检查中分开构建镜像，前端 Node 堆上限设置为 768MiB；进程总内存仍可能高于堆上限。

3Mbps 理论上约等于 **0.375MB/s**。若文件传输方向受该峰值带宽限制，10MB 文件理想情况下约需 27 秒，50MB 约需 134 秒，实际通常更慢。3Mbps 若整月持续跑满会明显超过 300GB，因此月流量仍是独立限制；300GB 均摊到整月约为 0.93Mbps。云厂商往往分别规定入站、出站带宽、峰值口径和流量计费，请以控制台规则为准。

原示例 40GB SSD 可用于初始系统和镜像，但同时保存 Docker 构建缓存、多个回退镜像、本地备份和用户文档后会较快增长。部署前检查实际根分区容量，运行期间继续保留至少 10GB 可用空间。

本项目单文档限制为 50MiB。Caddy 放行 55MB 请求体，以便容纳表单封装，但不会取消应用自身的 50MiB 限制。OCR 会同时保留原文档和派生文件，磁盘占用会增加。

### 2. 正式部署的域名、端口与证书

对于**需要公网访问的正式部署**，准备：

1. 云服务器公网 IP。
2. SSH 登录用户名和密码或密钥。不同厂商可能默认使用 `root` 或 `ubuntu`。
3. 一个你可以管理 DNS 的域名，例如 `read.example.com`。
4. 一个真实邮箱，用于证书联系信息。
5. 包含本教程配套文件的完整项目目录。

如果暂时没有正式域名，只进行 Docker 安装、源码准备与**隔离构建/发布验证**；不要宣布公网部署完成，也不要把 IP 或 `localhost` 传给 `init-env.py`，更不要关闭生产 Cookie Secure。

本文约定：

- `你的服务器公网IP`：替换为真实 IP。
- `read.example.com`：替换为自己的域名。
- `you@example.com`：替换为自己的邮箱。
- SSH 用户示例为 `ubuntu`；如控制台提供的是其他用户，请替换。
- 示例生产 Ubuntu 服务器代码路径为 `/opt/iknowread`；其他系统使用各自章节推荐路径。
- **命令旁的系统标记优先**；跨平台命令按前面的权限约定执行。

#### 2.1 DNS（[浏览器/云控制台]）

打开域名服务商的 DNS 控制台，新增：

| 类型 | 主机记录 | 记录值 |
|---|---|---|
| A | `read` | 服务器公网 IPv4 |

例如主域名是 `example.com`，主机记录为 `read`，得到 `read.example.com`。

初次部署先使用直接 DNS 解析。如果使用了 CDN 代理，先改成仅 DNS 模式，减少证书排障变量。如果你没有配置服务器 IPv6，不要保留指向其他位置的 AAAA 记录。

本方案依赖一个能够被证书颁发机构从公网访问的域名。Caddy 可以自动申请、续期证书，并把 HTTP 跳转到 HTTPS，前提是域名、网络和持久化目录正确。[Caddy 自动 HTTPS 文档](https://caddyserver.com/docs/automatic-https)

#### 2.2 云服务器安全组（[浏览器/云控制台]）

在云服务器的“安全组”或“防火墙”里允许以下**入站 TCP**：

| 端口 | 来源 | 用途 |
|---|---|---|
| SSH 实际端口，通常是 22 | 优先仅你的公网 IP | 远程管理 |
| 80 | 公网 | HTTPS 跳转及证书验证 |
| 443 | 公网 | HTTPS 网站 |

**不要开放 3306、9090、5173。** 本配置也没有把这些端口映射到宿主机。

出站需要能访问 DNS、系统软件源、镜像仓库、证书服务和 AI 厂商 HTTPS 接口。若厂商默认允许出站，不必另加规则。


### 3. 按操作系统安装 Docker 并检查环境

#### 3.1 Ubuntu 24.04 LTS：生产服务器（推荐）

**适用**：干净的 Ubuntu 24.04 云服务器或本地 Ubuntu Linux 主机。生产建议使用 Docker Engine + Compose 插件，不要求桌面图形界面。若已有正在使用的 Docker，请先核对现有版本与容器，**不要直接卸载或覆盖**。

**步骤 A：远程登录与基础信息**

```bash
# [macOS 终端 / Windows PowerShell / Windows WSL2] 连接 Ubuntu 服务器（按真实账号与 IP 修改）
ssh ubuntu@你的服务器公网IP
# 私钥连接时改用：ssh -i ~/.ssh/你的私钥文件 ubuntu@你的服务器公网IP
```

首次连接应从云控制台核对主机指纹。实际 SSH 端口不是 22 时，`ssh -p 端口`；稍后的 `scp -P 端口` 使用大写 P。

```bash
# [Ubuntu 服务器] 查看发行版、架构、内存、磁盘、时间以及 80/443 占用
cat /etc/os-release
uname -m
free -h
df -h /
timedatectl status
sudo ss -lntp | grep -E ':(80|443)\b' || true
```

**看到什么才继续**：系统是预期版本，`x86_64` 对应 `linux/amd64`、`aarch64` 对应 `linux/arm64`；磁盘、时间正常；80/443 未被不认识的服务占用。不要因为占用就停止别的业务进程。

**步骤 B：基础工具与系统更新**

```bash
# [Ubuntu 服务器]
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl python3 nano ufw dnsutils rsync
```

若提示内核更新需要重启，在维护窗口执行 `sudo reboot`，重新 SSH 登录后再继续。

**步骤 C：UFW 与云安全组配合（绝不可漏开实际 SSH 端口）**

```bash
# [Ubuntu 服务器] 如果 SSH 非 22，请先替换 22；不要关闭当前 SSH 会话
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

**看到什么才继续**：SSH、80、443 有符合预期的入站规则；另开终端再次 SSH 成功。云平台安全组仍要单独检查。Docker 发布端口可能绕过普通 UFW 规则，因此只允许 Web 映射 80/443，**不暴露 3306、9090、5173**。也不要把 `ufw disable` 当作排障捷径。

**步骤 D：可选配置 Swap（原 4GB 主机示例建议 2GiB）**

```bash
# [Ubuntu 服务器] 先检查；有可用 Swap 或已有 /swapfile 时不要重复创建
swapon --show
ls -lh /swapfile 2>/dev/null || true
```

仅当 **Swap 不存在且 `/swapfile` 不存在** 时操作：

```bash
# [Ubuntu 服务器] 仅执行一次
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# 先确认 swapon 成功，且 /etc/fstab 尚无 /swapfile 项，再追加：
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

Swap 不等于物理内存；如出现频繁 Swap 或 OOM，应先减小负载（OCR 仍关闭）再考虑升级内存。

**步骤 E：从 Docker 官方 apt 源安装 Engine 与 Compose**

```bash
# [Ubuntu 服务器] 仅适用于已确认没有冲突 Docker 安装的环境
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF_DOCKER
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

**看到什么才继续**：显示 `Hello from Docker!`；Compose 版本 **≥ 2.24.4**（项目 `deploy/compose.verify.yaml` 使用 `!override`）；`docker compose` 可运行（不是旧命令 `docker-compose`）。本指南在生产 Ubuntu 用 `sudo docker`，不要求把普通用户加入等同于高权限访问的 `docker` 组。

**验证防火墙限制与安装文档**：[Docker Engine Ubuntu 安装](https://docs.docker.com/engine/install/ubuntu/)；[Docker 与 UFW/iptables](https://docs.docker.com/engine/network/packet-filtering-firewalls/)。

#### 3.2 Windows：Docker Desktop + WSL 2（Linux 容器）

**适用**：符合 Docker Desktop 官方要求的 Windows 10/11 **客户端系统**。本项目生产镜像是 Linux 镜像，**不要切换到 Windows containers**。Windows Server 不等同于 Docker Desktop 支持的桌面 Windows；若目标是 Windows Server，优先改用独立 Ubuntu 虚拟机/主机承载这套 Linux 容器。

**步骤 A：安装 / 更新 WSL 2**

```powershell
# [Windows PowerShell（管理员）] 已安装 WSL 时可先查看版本
wsl --version
wsl --status
wsl --list --verbose
# 没装 WSL 时，按微软提示执行并按要求重启
wsl --install -d Ubuntu
```

若 Ubuntu 发行版已经存在，**不要用 `wsl --install` 覆盖它**。需要时运行 `wsl --update`，首次进入 Ubuntu 设置 WSL 用户名和密码。确保发行版版本列为 **2**；不是 2 时可按实际发行版名称执行 `wsl --set-version Ubuntu 2`。启用虚拟化并满足 Windows / WSL 最低版本要求。

**步骤 B：安装 Docker Desktop（官网下载）**

从 [Docker Desktop for Windows 官方页面](https://docs.docker.com/desktop/setup/install/windows-install/) 下载并安装，启动 Docker Desktop。在 Settings 中选择 WSL 2 后端，并在 **Settings → Resources → WSL Integration** 启用你实际使用的 Ubuntu 发行版；Docker Desktop 采用 Linux containers 模式。在 WSL 发行版中**不要再安装一个相互冲突的 Docker Engine**。

```powershell
# [Windows PowerShell] 确保 Docker Desktop 已启动后验证 Windows 端 CLI
docker version
docker compose version
docker info --format '{{.OSType}} / {{.Architecture}}'
```

```bash
# [Windows WSL2：Ubuntu Shell] 后续 .sh 脚本、Linux 命令都在这里执行
docker version
docker compose version
docker info --format '{{.OSType}} / {{.Architecture}}'
docker run --rm hello-world
python3 --version
```

若 `python3` 不存在，可在 WSL 的 Ubuntu 中安装 `sudo apt-get update && sudo apt-get install -y python3`。若 WSL 报无法访问 Docker daemon，优先检查 Docker Desktop 是否运行、WSL Integration 是否开启；**不要为此安装第二套 Linux Docker daemon**。

**看到什么才继续**：输出 `linux / amd64`（或实际 Linux 架构）、`Hello from Docker!`，Compose ≥ 2.24.4；在 **WSL Shell** 中能调用 Docker。

**项目路径**：优先把源码放进 WSL 文件系统，例如 `~/projects/iKnowread`，而非 `C:\Users\...` 或 `/mnt/c/...`，这样更接近 Linux 的大小写、权限与 IO 语义：

```bash
# [Windows WSL2]
mkdir -p ~/projects
cd ~/projects
# 从 Git 仓库获取代码或将现有源代码复制到这里（不得复制生产 .env / 数据）
```

| 路径类型 | 示例 | 用途 |
|---|---|---|
| Windows 主机 | `C:\Users\<用户名>\projects\iKnowRead` | PowerShell 管理文件；不建议把 Linux 构建源直接放在这里 |
| WSL Linux | `/home/<用户名>/projects/iKnowread` | **推荐运行 `deploy/*.sh` 与 Compose 的工作目录** |
| Docker 容器 | `/app/data` | 容器内部持久化挂载点，保持不变 |

**防火墙与端口**：在纯本地验证阶段不需要给公网开放任何端口；隔离验证栈会临时使用 `13306`、`19090`、`18080`、`18443`（来自原教程），先确认无冲突。若确实在 Windows 主机发布网站并完成公网验收，必须在 Windows Defender 防火墙、高级安全规则和路由器/云安全组中**仅**为 Web 允许 TCP 80/443；不要对外开放数据库和后端端口。端口检查：

```powershell
# [Windows PowerShell] 有输出说明端口已被监听；需识别对应 PID/程序
Get-NetTCPConnection -LocalPort 80,443 -State Listen -ErrorAction SilentlyContinue
```

**注意**：Windows Desktop 退出、注销、休眠或 WSL 停止可能导致服务不可用；不要仅凭 Docker Compose 的 `restart` 策略就声称 Windows 已具备服务器级常驻保障。

官方参考：[Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)、[WSL 2 后端与集成](https://docs.docker.com/desktop/features/wsl/)。

#### 3.3 macOS：Docker Desktop（Apple Silicon / Intel）

**步骤 A：安装 Docker Desktop**

按芯片类型从 [Docker Desktop for Mac 官方页面](https://docs.docker.com/desktop/setup/install/mac-install/) 获取对应安装包，安装到“应用程序”，启动并完成首次授权。操作系统和机器必须满足官方版本及虚拟化要求；macOS 主机**没有 Ubuntu 的 `apt`/`ufw`**，不能照抄 Ubuntu 的安装、Swap 和 `systemctl` 命令。

```bash
# [macOS 终端] Docker Desktop 启动并准备完成后
uname -m
docker version
docker compose version
docker info --format '{{.OSType}} / {{.Architecture}}'
docker run --rm hello-world
python3 --version
```

**看到什么才继续**：容器引擎为 `linux`，Compose ≥ 2.24.4，`hello-world` 成功；Apple 芯片的 `arm64`、Intel 的 `amd64` 都可以用于本机验证。部署到异构 Ubuntu 服务器时必须在构建阶段指定 `TARGET_PLATFORM=linux/amd64` 或 `linux/arm64` 并验证镜像实际架构（见 §16）。如果没有 `python3`，先按可信安装方式准备 Python 3，**不需要安装宿主机 MySQL、Node.js、Nginx**。

**项目路径**：例如 `/Users/<用户名>/projects/iKnowread` 或 `~/projects/iKnowread`；把构建缓存、运行文件与根目录 `.env` 留在受保护的本机目录，不放在共享网盘目录。Docker Desktop 中根据构建压力配置可用 CPU、内存和磁盘，不可把“Mac 物理内存”误当成全部可分配给 Docker 的额度。

```bash
# [macOS 终端] 端口被占用时会显示监听程序
lsof -nP -iTCP:80 -sTCP:LISTEN
lsof -nP -iTCP:443 -sTCP:LISTEN
```

macOS 的“系统设置 → 网络 → 防火墙”用于宿主入站管理，但**不能代替**路由器端口转发、云安全组或 Caddy 的公网证书要求。仅做发布隔离验证，不需让外网访问 80/443；确需直连公网发布时，先确认公网入口能抵达这台 Mac、80/443 没有端口冲突，并且应用、Docker Desktop、网络不会随休眠中断。**不要为了本地 HTTP 登录放宽生产 Cookie。**

**命令区别**：本地 Docker Desktop 直接 `docker compose ...`，不使用 `sudo docker`；文件 SHA256 用 `shasum -a 256`；进程/端口检查用 `lsof`，不能直接运行 Linux 的 `systemctl`、`ss`、`ufw`。

#### 3.4 其他 Linux 发行版：共享流程可复用，安装部分需适配

Debian / Fedora / Rocky / AlmaLinux 等其他 Linux 发行版，**只复用本指南的架构原则与阶段二至阶段四的 Compose 逻辑**。必须先根据 Docker 官方对应发行版文档确认 Docker Engine/Compose 的支持情况，并用发行版实际的包管理工具、系统防火墙（如 `firewalld`）和安全规则替换 Ubuntu 的 `apt`/`ufw`。不要把 Ubuntu 的官方 apt 仓库直接装到其他发行版；需要核实 SELinux、挂载权限、容器的 UID/GID 与卷行为。

### 4. 源码文件、路径和上传（部署主机）

项目需包含以下已有文件（**不需要手工重写 Compose 或 Dockerfile**）：

```text
# [所有系统：项目根目录，名称一致]
iKnowread/
├── compose.yaml
├── .dockerignore
├── deploy/
│   ├── Dockerfile.backend
│   ├── Dockerfile.mysql
│   ├── Dockerfile.web
│   ├── Caddyfile
│   ├── compose.verify.yaml
│   ├── init-env.py
│   ├── backup.sh
│   ├── release-check.sh
│   └── verify-backup.sh
├── docs/
├── fastapi-app/
└── vue/
```

| 场景 | 源码放哪里 | 如何准备 | 验收 |
|---|---|---|---|
| Ubuntu 远程生产 | `/opt/iknowread` | 在自己的电脑打包；校验 SHA256；用 `scp` 传输并在 Ubuntu 解压 | `compose.yaml`、`deploy/`、后端/前端代码存在 |
| Windows 本地隔离构建 | WSL `~/projects/iKnowread` | 在 WSL 中克隆或复制完整源码；排除 `.env` 与数据 | WSL 可运行 Bash 脚本且不读取 Windows 开发密钥 |
| macOS 本地隔离构建 | `~/projects/iKnowread` | 在 Mac 终端克隆或复制完整源码；排除 `.env` 与数据 | 文件齐全；Docker Desktop 正在运行 |

**上传到 Ubuntu：从 macOS / Windows WSL2 / Linux Shell 打包**。先 `cd` 到**实际的项目根目录**，不要照抄原教程中个人电脑的绝对路径。以下命令使用通用 `tar`，注意原有排除表（开发用密钥/运行数据不可上传）：

```bash
# [macOS 终端 / Windows WSL2 / Linux Shell] 在项目根目录
# Mac 自动排除 AppleDouble；其他 Linux Shell 设置该变量也无害
COPYFILE_DISABLE=1 tar \
  --exclude='.git' --exclude='.idea' --exclude='.DS_Store' --exclude='._*' \
  --exclude='node_modules' --exclude='dist' --exclude='__pycache__' \
  --exclude='.venv' --exclude='venv' \
  --exclude='./.env' --exclude='./fastapi-app/.env' \
  --exclude='./fastapi-app/data' --exclude='./runtime' --exclude='./backups' \
  -czf /tmp/iknowread-source.tar.gz .

tar -tzf /tmp/iknowread-source.tar.gz | grep -E '^\./(compose.yaml|deploy/release-check.sh|deploy/verify-backup.sh|fastapi-app/main.py|vue/package.json)$'
if tar -tzf /tmp/iknowread-source.tar.gz | grep -Eq '^\./(\.env$|fastapi-app/\.env$|fastapi-app/data/|runtime/|backups/)'; then
  echo '打包中出现敏感配置或用户数据，停止传输。' >&2
  exit 1
fi
```

**看到什么才继续**：5 个关键文件都列出；敏感路径检查无命中；命令成功。Windows WSL2/Linux 使用 `sha256sum`，macOS 使用 `shasum`，不要在 PowerShell 直接执行这一 Bash 片段。

```bash
# [macOS 终端] 若打包系统为 macOS
shasum -a 256 /tmp/iknowread-source.tar.gz > /tmp/iknowread-source.tar.gz.sha256
scp /tmp/iknowread-source.tar.gz /tmp/iknowread-source.tar.gz.sha256 ubuntu@你的服务器公网IP:/tmp/
```

```bash
# [Windows WSL2 / Linux Shell] 若打包系统为 Linux / WSL2
sha256sum /tmp/iknowread-source.tar.gz > /tmp/iknowread-source.tar.gz.sha256
scp /tmp/iknowread-source.tar.gz /tmp/iknowread-source.tar.gz.sha256 ubuntu@你的服务器公网IP:/tmp/
```

```bash
# [Ubuntu 服务器] 新部署：仅在目标 /opt/iknowread 尚未包含生产数据时执行
cd /tmp
sha256sum -c iknowread-source.tar.gz.sha256
sudo mkdir -p /opt/iknowread
sudo chown "$(id -u):$(id -g)" /opt/iknowread
tar -xzf /tmp/iknowread-source.tar.gz -C /opt/iknowread
cd /opt/iknowread
ls -la
```

解压前必须看到 `OK`；升级已有服务**不能直接用 tar 覆盖**，必须改走 §12 的备份、临时目录和 `rsync --delete`（带保护排除项）流程。不要将 macOS `node_modules`、本地 `.env` 和开发数据库直接拷进生产环境。

---

## 阶段二：配置与构建（共同主线）

### 5. 生成 .env、持久化与安全配置

先替换示例中的域名和邮箱。**这是具有正式 HTTPS 域名的部署**。没有域名的 Mac/Windows 用户可先完成 §6 的隔离发布门禁，但不能把 `localhost` 作为生产域名启动并声称登录验收通过。

```bash
# [Ubuntu 服务器] 项目目录为 /opt/iknowread
cd /opt/iknowread
python3 deploy/init-env.py read.example.com you@example.com
sudo install -d -o 10001 -g 10001 -m 0700 runtime/app-data
stat -c '%a %u:%g %n' .env runtime/app-data
grep -E '^(DOMAIN|ACME_EMAIL|OCR_ENABLED|ALLOW_REGISTRATION|APP_TAG)=' .env
```

```bash
# [macOS 终端 / Windows WSL2] 仅当具备合格域名、确实要启动完整服务时；从各自项目根目录执行
python3 deploy/init-env.py read.example.com you@example.com
mkdir -p runtime/app-data
chmod 700 runtime/app-data
# WSL/Linux 检查：stat -c '%a %u:%g %n' .env runtime/app-data
# macOS 检查：stat -f '%Lp %Su:%Sg %N' .env runtime/app-data
grep -E '^(DOMAIN|ACME_EMAIL|OCR_ENABLED|ALLOW_REGISTRATION|APP_TAG)=' .env
```

Docker Desktop 的 bind mount 与宿主机 UID/GID 映射可能不同：**不能假定本机 `chmod`/`chown` 会产生与 Ubuntu 原生 Linux 完全一致的结果**。`runtime/app-data` 仅供首次导入/恢复；正式文件写入的是 Linux 命名卷。若权限报错，看 `app-data-init` 和后端日志，禁止 `chmod 777`。Windows 应在 WSL Linux 文件系统中运行 `.env` 初始化，避免 NTFS ACL 与 POSIX `600` 权限语义混淆。

Ubuntu 原生部署预期 `.env` 权限为 `600`；暂存目录为 `700 10001:10001`。这里直接检查数字 UID/GID，因为宿主机不需要创建名为 `app` 的 10001 账号。首发还应看到 `OCR_ENABLED=false`、`ALLOW_REGISTRATION=false`、`APP_TAG=local`。这里的 `grep` 只显示非密钥项。不要用 `cat .env` 做检查，因为终端记录、截图或协作工具可能保存其中的数据库密码和会话密钥。

生成脚本会：

- 在**项目根目录**创建 `.env`，权限为 `600`。
- 分别随机生成数据库业务密码、数据库 root 密码、会话签名密钥。
- 默认关闭 OCR。
- 默认关闭公网自助注册，由管理员在后台创建账号。
- 默认每账号最多 200 份文档、累计 2GiB，并为服务器保留至少 2GiB 空闲空间。
- 如果 `.env` 已存在则退出，避免误改已有数据库的密码。
- 不写入任何 AI 供应商 Key；每个用户上线后在自己的账号中配置。

此处的根目录 `.env` 是 Docker Compose 读取的配置，和开发用的 `fastapi-app/.env` 不同。Docker 构建会排除开发 `.env`，后端配置通过容器环境变量传入。

如果需要修改域名或邮箱：

```bash
# [Ubuntu 服务器 / Windows WSL2 / macOS 终端] 从项目根目录编辑；没有 nano 可使用已有文本编辑器
nano .env
```

需要开放自助注册时，将 `ALLOW_REGISTRATION=false` 改为 `true`，然后在 Ubuntu 执行 `sudo docker compose up -d --no-build backend`（Docker Desktop 环境去掉 `sudo`）。公网系统应先确认认证限速和存储配额符合实际用户规模。账号配额可通过 `USER_STORAGE_QUOTA_BYTES`、`USER_DOCUMENT_LIMIT` 和 `STORAGE_MIN_FREE_BYTES` 调整；字节值不要写单位。

Nano 中按 `Ctrl+O` 保存，回车确认文件名，再按 `Ctrl+X` 退出。

不要在截图、论坛或聊天中展示 `.env` 全文。它包含真实密码。不要把生产文件提交到代码仓库。

#### 数据保存在哪里？

| 内容 | 持久化位置 |
|---|---|
| 账号、文档记录、笔记、加密后的 AI 配置 | Docker 命名卷 `iknowread_mysql_data` |
| 上传文档、头像、OCR 派生文件 | `iknowread_app_data` 命名卷内的 `files/` |
| AI 加密密钥 | `iknowread_app_data` 命名卷内的 `.ai-config-key`，首次保存 AI 配置时生成 |
| 首次管理员密码 | `iknowread_app_data` 命名卷内的 `.initial-admin-password` |
| HTTPS 证书和私钥 | Docker 命名卷 `iknowread_caddy_data` |
| 数据库密码、会话签名密钥 | **项目根目录** `.env`（Ubuntu 示例为 `/opt/iknowread/.env`） |

后端进程以 UID/GID `10001:10001` 运行，所以 Ubuntu 原生 Linux 首次导入目录也需要对应属主。不要用 `chmod 777` 解决权限问题。

**不能只备份 MySQL。** 数据库记录依赖文件，AI API Key 的解密依赖 `.ai-config-key`。本方案故意挂载整个 `/app/data`，而不只是 `files` 子目录。

MySQL 容器初始化数据库和业务账号；后端使用业务账号，并设置 `DB_AUTO_CREATE=false`，随后仍会自动执行项目的版本化表迁移。业务账号拥有当前数据库的权限，但不用数据库 root 账号运行应用。[MySQL 官方镜像初始化说明](https://hub.docker.com/_/mysql)

#### 命名卷与旧目录的区别

当前应用文件和 AI 密钥存放于 `iknowread_app_data` 命名卷。`runtime/app-data` 仅用于旧版本升级、首次迁移或空环境恢复时暂存数据；`app-data-init` 会在卷为空时导入，并写入导入标记。卷已有数据时不会合并或覆盖。首次启动后再修改旧目录，不会同步到运行中的系统。

恢复前除检查 `iknowread_mysql_data` 外，还必须确认 `iknowread_app_data` 不存在；已有任一数据卷都不能按空环境恢复。完成恢复或本地数据迁移的暂存步骤后，在 Ubuntu 执行 `sudo docker compose up -d --no-build`，检查 `sudo docker compose logs app-data-init`，确认导入成功。不要删除导入标记来强制覆盖已有卷。

### 6. DNS 与 Compose 校验、构建和发布门禁

```bash
# [Ubuntu 服务器] 正式公网部署：项目目录与 DNS
cd /opt/iknowread
dig +short A read.example.com
dig +short AAAA read.example.com
sudo docker compose config --quiet
```

```bash
# [macOS 终端 / Windows WSL2] 从项目根目录执行；无正式域名时，仅做隔离门禁
# 如果已经生成 .env 且准备正式启动，再执行下面的配置校验
docker compose config --quiet
```

注意：未生成 `.env` 时，单独的 `docker compose config --quiet` 可能因为缺少密码/域名变量而失败；此时**不要编造密钥**。可以先运行 `release-check.sh` 自身的一次性占位配置与隔离验证；只有真正准备运行主栈时才生成生产 `.env`。

A 记录应指向服务器；若没有 IPv6，AAAA 应为空。配置检查成功时通常没有输出。不要随意执行不带 `--quiet` 的 `docker compose config` 后分享输出，因为它会展开密码。

先执行一键发布前检查。它使用一次性占位配置校验 Compose，顺序构建三个生产镜像；执行 Ruff、生产后端镜像回归测试、前端 `npm ci` 与 `npm run check`、生产依赖审计；检查 Caddy、MySQL 和真实 OCR 运行能力；最后启动隔离栈验证网关、数据库约束和后端重启持久化。测试数量随源码变化，以本次输出为准。独立 OCR 检查不会开启正式服务的 OCR。隔离栈使用 172.30.31.0/24 网段及本机 13306、19090、18080、18443 端口，执行前确保它们未被占用；不要同时运行多份检查。验证栈不挂载生产旧数据目录，退出时删除自己的容器和卷。
```bash
# [Ubuntu 服务器] 发布检查（从项目根目录）
sudo bash deploy/release-check.sh
```

```bash
# [macOS 终端 / Windows WSL2] 本地隔离构建/验收（在项目根目录）
bash deploy/release-check.sh
```

成功时最后一行是“发布前检查全部通过”。脚本构建的 `local` 标签必须与 `.env` 中的 `APP_TAG=local` 一致。不要在检查通过后再次手工构建同名镜像，否则后续启动的可能不是刚验证过的产物。

如果已经安装并登录 Docker Scout，正式发布前使用漏洞门禁模式；任一最终镜像存在可修复的 critical/high 漏洞都会失败：

```bash
# [Ubuntu 服务器] 安装且可用 Docker Scout 时的正式发布门禁
sudo bash deploy/release-check.sh --scan
```

```bash
# [macOS 终端 / Windows WSL2] 已安装且可用 Docker Scout
bash deploy/release-check.sh --scan
```

服务器没有 Docker Scout 时，可以在受信任的开发机或 CI 上对同一提交和目标架构运行 `--scan`，再把这三个已经扫描的 `local` 镜像按第 16 节传到服务器。不要把“没有安装扫描工具”当成扫描通过，也不要在服务器加载后再次构建。

脚本仍会顺序构建，尽量控制小内存机器的构建峰值，并避免构建任务与 Docker、系统服务争抢资源。初次下载 Python 依赖、OCR 字体、MySQL、Go 和 Node 镜像可能花较长时间。下载速度取决于服务器的实际入站网络，而不是只看 3Mbps 公网峰值带宽。

另开一个 SSH 窗口，可以观察：

```bash
# [Ubuntu 服务器 / Windows WSL2] 当前 Shell 的资源快照（WSL 不代表 Windows 全部资源）
free -h
df -h /
top
```

```bash
# [macOS 终端] 宿主机资源；Docker 容器另在 Desktop 仪表盘观察
vm_stat
df -h .
top -l 1 | head -n 15
```

前端构建有大文件体积提示不一定代表失败，应看最后退出状态是否成功。如果看到 `Killed`、退出码 `137`，先看系统 OOM 日志，参照第 15 节。如果服务器构建资源不足，可按第 16 节从 Windows/macOS 构建对应架构镜像再上传。

镜像选择了 Python 3.12、Node 24、MySQL 8.4.11、Go 1.26.9 和 Caddy 2.11.7。基础镜像 digest 与完整应用依赖锁文件会减少漂移，但软件仓库内容和构建元数据仍可能变化。首次稳定部署后应保留已经验收的镜像和备份，以便回退。

**跨平台门禁注意**：Windows WSL2 和 macOS 上运行发布门禁前，须保证 Bash、Docker CLI、Compose、Buildx 和 Docker Desktop 资源都已准备好；脚本中如调用 Linux 平台特有命令，应以**脚本实际实现**为准处理，不可从本文推断未经测试的全部 Windows/macOS 本地兼容性。发布门禁通过只证明该次构建与隔离验收；不能替代公网 HTTPS 或真实业务验收。

---

## 阶段三：启动与验收（共同主线）

### 7. 启动主服务并获取管理员密码

```bash
# [Ubuntu 服务器] 正式生产主机
cd /opt/iknowread
sudo docker compose up -d --no-build
sudo docker compose ps
sudo docker compose logs --tail=100 db backend web
```

```bash
# [macOS 终端 / Windows WSL2] 符合正式域名与端口条件、确需启动主栈时；从项目根目录执行
docker compose up -d --no-build
docker compose ps
docker compose logs --tail=100 db backend web
```

`--no-build` 保证启动的是第 6 节通过检查的同一组镜像。若提示镜像不存在，返回第 6 节修复构建或镜像加载问题，不要去掉参数让 Compose 隐式构建。首次启动 MySQL 会初始化磁盘数据，可能需要几分钟。启动顺序是数据库健康检查通过 → 后端启动及自动迁移 → Caddy 启动。

正常状态应类似：db 和 backend 显示 `healthy`，web 显示 `Up`。后端健康检查有 90 秒启动宽限期，之后按 30 秒间隔最多重试 3 次；首次初始化可观察约 3 分钟。超过这一范围仍未健康就查看日志，不要反复重启 MySQL。

读取首次管理员密码：

```bash
# [Ubuntu 服务器] 获取仅首次初始化时生成的密码（注意终端回显）
sudo docker compose exec -T backend cat /app/data/.initial-admin-password
# [macOS 终端 / Windows WSL2] 等价命令：docker compose exec -T backend cat /app/data/.initial-admin-password
```

然后浏览器打开：

```text
https://read.example.com
```

选择管理员身份，用户名为 `admin`，密码使用上面读到的随机值。登录后立即到修改密码页面设置自己的强密码。

注意：管理员首次成功登录后，应用会删除初始密码文件；**文件删除不代表密码自动作废**，你仍然需要主动修改密码。若文件不存在，应先检查是否已经登录过或数据库中已经有管理员，不要反复重建数据库。

Ubuntu 正式服务器退出 SSH 不会停止容器，因为使用了 `-d` 后台运行；Docker 服务已设置开机启动且容器使用 `restart: unless-stopped`，主动停止的容器不会因为该策略自动恢复。**Windows/macOS 的 Docker Desktop 仍依赖宿主会话、电源与 Desktop 本身的运行状态**，不能以 `-d` / `restart` 推定可用性与生产持续在线。

### 8. HTTPS、健康检查与业务验收

#### 8.1 检查 HTTPS 和 API

```bash
# [Ubuntu 服务器 / macOS 终端 / Windows WSL2] 仅在正式域名实际可达时执行
curl -I http://read.example.com
curl -I https://read.example.com
curl -fsS https://read.example.com/api/health
curl -fsS https://read.example.com/api/ready
curl -fsS https://read.example.com/api/capabilities
```

预期：HTTP 跳转到 HTTPS，HTTPS 首页可访问，并包含 `Strict-Transport-Security: max-age=86400`；`health` 响应的 `data.status` 为 `ok`，`ready` 响应的 `data.status` 为 `ready`。前者只表示进程存活，后者还检查数据库连接和上传目录权限；Compose 使用 `ready` 判断后端是否健康。首发的 `capabilities.data` 应显示注册和 OCR 都为关闭状态。

Caddy 把 `/api/health` 转发为后端的 `/health`，通过 `handle_path` 去掉 `/api`。如果你换成 Nginx 或其他代理，也必须保持这个行为。[Caddy handle_path 文档](https://caddyserver.com/docs/caddyfile/directives/handle_path)

健康接口只是基础可达性检查，不代表数据库、文件读写和所有业务都已经通过验收。

#### 8.2 在浏览器依次检查

1. 登录管理员后刷新页面，登录状态仍然存在。
2. 在管理员后台创建一个普通账号，确认能正常登录。默认不开放自助注册。
3. 上传一个较小的文字版 PDF，确认列表出现、能阅读、翻页、选中文字和下载。
4. 上传一个 DOCX，确认能预览。
5. 新建笔记、编辑笔记，再导出 Markdown。
6. 上传伪装成 PDF/DOCX 的无效文件，确认系统拒绝，而不是保存或预览。
7. 确认扫描版 PDF 显示 OCR 未启用或相应终止状态，不会永久停留在等待中。
8. 执行下面的后端重启，再确认账号、文档和笔记仍然存在。

```bash
# [Ubuntu 服务器] 容器重启后继续从浏览器检查数据持久化
sudo docker compose restart backend
# [macOS 终端 / Windows WSL2] 使用：docker compose restart backend
```

AI 不属于本次首发验收项，部署者不需要提供统一 Key。上线后，每个用户可在自己的“AI服务 → API配置”中填写自己的厂商 Key、Base URL、模型和额度设置，先测试再启用；不同账号的配置相互隔离。供应商可用性、模型权限、费用、限流和数据处理条款由实际使用者确认。用户未配置 Key 时，文档管理、阅读和笔记功能仍可正常使用。

Caddy 的上游响应头等待时间设置为 180 秒，以覆盖项目最长约 125 秒的 AI 等待。普通前端请求仍有自己的超时，不能靠单独增加代理超时解决所有问题。

还可以检查端口映射：

```bash
# [Ubuntu 服务器] 检查宿主端口和 Docker 映射
sudo docker compose ps
sudo ss -lntp
```

```bash
# [macOS 终端 / Windows WSL2] 检查 Compose 是否仅对外映射 Web
docker compose ps
# [macOS 终端] lsof -nP -iTCP -sTCP:LISTEN
# [Windows PowerShell] Get-NetTCPConnection -State Listen
```

Compose 中只有 web 应显示宿主机 `80` 和 `443` 映射。db 显示容器内部端口不等于发布到了公网，应以是否存在 `0.0.0.0:端口->...` 等宿主映射为准。

**平台完成判定**：Windows/macOS 隔离验证通过时只标记“本地构建/验证完成”；只有在浏览器以真实域名使用受信任 HTTPS，且上述全部核心业务与数据重启检查通过时，才可标记为“该主机公网部署验收通过”。

### 9. OCR：保持首发关闭，未来按条件启用

本项目已经决定首发不启用 OCR，本节不是首次部署必做步骤。默认关闭 OCR 是为了先让普通阅读和笔记功能稳定运行。关闭时 PDF 会明确显示“OCR 未启用”，不会产生永久等待任务。**扫描版 PDF 仍能显示图像，但通常不能选中文字，也无法直接选文解释。**

镜像已安装 OCRmyPDF、PDFium、Tesseract 中英文包及 Noto 字体。本项目输出普通 PDF，并使用 PDFium 栅格化；OCRmyPDF 17 中 Ghostscript 是可选项，因此此镜像未额外安装它。[OCRmyPDF 安装要求](https://ocrmypdf.readthedocs.io/en/latest/installation.html)

只有以后明确需要扫描件文字层，并且已经在同规格机器完成小样本、异常样本、内存、Swap 和超时验收后，才执行以下步骤：

```bash
# [Ubuntu 服务器 / macOS 终端 / Windows WSL2] 从项目根目录编辑配置
nano .env
```

把：

```dotenv
OCR_ENABLED=false
```

改成：

```dotenv
OCR_ENABLED=true
```

应用配置：

```bash
# [Ubuntu 服务器] 可选 OCR 专项验收；Docker Desktop 环境把 sudo docker 改为 docker
sudo docker compose up -d --no-build backend
sudo docker compose exec backend tesseract --list-langs
sudo docker compose exec backend python -m ocrmypdf --version
sudo docker stats
```

语言列表应包含 `eng` 和 `chi_sim`。按 `Ctrl+C` 退出资源监视，不会停止容器。

启用后，后端会把此前标记为“OCR 服务未启用”的已有 PDF 自动恢复为待处理，并按单工作线程依次重新识别；如果系统已经积累很多 PDF，不要在业务高峰直接开启。先在测试部署或文档很少时用 1～3 页的小扫描 PDF 验证，观察 OCR 状态、内存与日志，再逐步增加页数。其他原因失败的文件不会全部自动重试，界面出现“重试识别”时可人工重试。

当前 OCR 配置：

- 同时处理 1 份文档，单份文档 1 个任务。
- 单页最大 20 百万像素，比开发默认值保守；复杂页面仍可能消耗大量内存。
- 单文档超时 900 秒、单页超时 120 秒。
- 后端 CPU 上限 1.25 核、内存上限 850MiB；内存不足时 OCR 或整个后端可能被终止。

这些设置不能保证所有扫描件成功。如果出现持续卡顿、频繁退出或大文档失败，先改回 `OCR_ENABLED=false` 并执行 `sudo docker compose up -d --no-build backend`。4GB 主机有较充足的系统余量，但当前后端仍受 850MiB 内存和 1.25 核 CPU 限制；大量 OCR 工作更适合调整架构或使用独立任务服务，不要只增加并发或 Uvicorn workers。

---

## 阶段四：维护、备份、更新与恢复（共同主线）

> **执行地点**：以下涉及 `/opt/iknowread`、`sudo`、`ufw`、`systemctl`、`timedatectl`、`sha256sum`、`/var/log` 的示例默认是 **[Ubuntu 服务器]**，保留自原版经过验证的生产路径；在 Windows/macOS 本地运行容器操作时从各自项目根目录执行、用 `docker` 代替 `sudo docker`，但 **Ubuntu 系统管理、备份恢复与 Linux 文件权限命令不可整段照搬**。跨平台备份恢复应先在隔离环境演练，并按脚本实际依赖确认兼容性。

### 10. 日常运行与故障定位

运行前进入项目根目录：

```bash
# [Ubuntu 服务器]；[macOS 终端 / Windows WSL2] 切换到各自存放源码的根目录
cd /opt/iknowread
```

| 目的 | 命令 |
|---|---|
| 查看容器 | `sudo docker compose ps` |
| 查看最近后端日志 | `sudo docker compose logs --tail=100 backend` |
| 持续观察日志 | `sudo docker compose logs -f --tail=100 backend web` |
| 查看资源 | `sudo docker stats` |
| 重启后端进程 | `sudo docker compose restart backend` |
| 应用环境变量修改 | `sudo docker compose up -d --no-build backend web` |
| 停止整套服务 | `sudo docker compose stop` |
| 启动已停止服务 | `sudo docker compose start` |
| 查看磁盘 | `df -h /` |
| 查看应用文件大小 | `sudo docker compose exec -T backend du -sh /app/data` |
| 查看 Docker 空间 | `sudo docker system df` |
| 检查公网就绪 | `curl -fsS https://read.example.com/api/ready` |
| 查看一次资源快照 | `sudo docker stats --no-stream` |

后端每条请求日志包含 `request_id`、HTTP 方法、路由模板、状态码和耗时；响应头 `X-Request-ID` 是同一个值。用户报告错误时可让其提供该响应头，再执行 `sudo docker compose logs backend | grep 'request_id=这里替换为实际值'` 定位。日志不会主动记录查询参数、Cookie、Authorization、请求正文或异常消息；不要为了排障把这些敏感内容手工打印出来。

改 `.env` 后，单纯 `restart` 不会加载新容器环境，应该用 `up -d` 让 Compose 重建配置有变化的容器。[Compose 服务配置文档](https://docs.docker.com/reference/compose-file/services/) 这只适用于 OCR、注册、配额、域名等普通配置；数据库密码不能只改 `.env`，处理方式见第 15 节“MySQL 报 Access denied”。

**任何操作系统都不要执行 `docker compose down -v` 或带卷删除选项的清理命令**，它会删除数据库卷和证书卷。普通 `down` 不删除命名卷，但日常暂停用 `stop` 更直观。

这套配置关闭了 MySQL binlog 以减少单机磁盘占用，因此没有基于 binlog 的时间点恢复，也没有数据库复制。恢复精度取决于你的备份频率。

首发当前决定暂不配置公网监控和自动告警，因此至少应人工定期执行 `docker compose ps`、公网 `/api/ready`、`docker stats --no-stream`、`df -h /` 和云控制台流量检查。建议磁盘保留至少 10GB 余量，月流量到 70%～80% 时检查文档下载、构建缓存及备份传输。没有告警意味着故障只能在人工检查或用户反馈后被发现。

**常用 Docker 命令的等价关系（不用重复改写全篇）**：`sudo docker compose ps/logs/exec/up/stop/start` 是 Ubuntu 正式部署写法；在 Windows WSL2 和 macOS Docker Desktop，通常一律去掉 `sudo`。Linux 宿主机资源检查 `free` / `journalctl` 不等于 macOS 或 Windows 的系统资源检查。**绝不把数据库 `3306` 或后端 `9090` 临时映射到公网用于排障。**

### 11. 完整备份与可恢复性验证

当前决定暂不配置异地备份、自动保留、备份加密密钥管理和失败告警。下面流程仍应保留：如果系统开始保存真实账号、文档或用户 AI Key，只有同盘本地数据而没有异地副本时，服务器或 SSD 故障可能造成全部数据丢失。至少在重要更新前手工执行一次，并把完成校验的备份保存到服务器之外。

#### 11.1 手动备份

```bash
# [Ubuntu 服务器] 从生产项目根目录执行
cd /opt/iknowread
sudo bash deploy/backup.sh
sudo ls -lt backups
```

脚本会短暂停止后端，等待写入和 OCR 停止，然后：

1. 导出 MySQL 逻辑备份。
2. 打包整个应用数据目录，包括隐藏的 AI 密钥。
3. 打包部署配置、根目录 `.env` 和对应源码。
4. 写入 SHA256 校验文件并检查所有归档可解压。
5. 把 SQL 恢复到一次性 MySQL 容器，确认备份源码对应数量的迁移记录以及核心业务表存在。
6. 后端恢复健康且隔离恢复验证通过后，最后创建 `COMPLETE` 文件。
7. 无论成功或失败，退出时尝试重新启动后端。

备份过程中网页可能显示接口错误，这是计划内的短暂停机，应在低使用时段运行。脚本使用互斥锁阻止两个备份同时运行，并在写入 `COMPLETE` 前等待后端恢复健康。随后 `verify-backup.sh` 会使用 `iknowread-mysql:local` 启动一次性 MySQL，实际导入 SQL；归档损坏、数据库恢复失败或迁移不完整时都不会生成 `COMPLETE`。大文件较多时，打包和校验可能很久，也需要额外磁盘与内存余量。

备份目录使用 UTC 时间命名，例如 `20261012T120000Z`。**只有存在 `COMPLETE` 且校验通过的目录才能作为完整备份使用。** 脚本若被强制杀死或服务器断电，自动恢复步骤可能无法执行，需手动检查并启动后端。

校验示例，替换为真实目录：

```bash
# [Ubuntu 服务器] 使用真实备份目录名
sudo sh -c 'cd /opt/iknowread/backups/20261012T120000Z && sha256sum -c SHA256SUMS'
sudo bash deploy/verify-backup.sh backups/20261012T120000Z
sudo docker compose ps
```

第二条会再次执行隔离数据库恢复验证；只需要快速检查归档与校验和时可在末尾加 `--archive-only`。完整备份仍以隔离恢复验证成功为准。

备份内容包含明文数据库密码、AI 解密密钥和用户文档，应作为敏感数据保管。脚本使用 `umask 077`，默认不让其他普通用户读取。

#### 11.2 下载到自己的电脑

备份只放在同一块服务器磁盘上，不能应对整机损坏。先在服务器将某次完整备份合成压缩包，并只交给当前 SSH 用户读取：

```bash
# [Ubuntu 服务器] 先打包，且只将临时副本交给当前 SSH 用户
cd /opt/iknowread
sudo tar -czf /tmp/iknowread-backup.tar.gz -C backups 20261012T120000Z
sudo chown "$(id -u):$(id -g)" /tmp/iknowread-backup.tar.gz
chmod 600 /tmp/iknowread-backup.tar.gz
```

再在**[macOS 终端 / Windows PowerShell / Windows WSL2]** 运行（把目标路径换成实际安全目录；PowerShell 的 `~/Downloads/` 须确保存在）：

```bash
# [macOS 终端 / Windows WSL2（已建 Downloads） / Windows PowerShell（路径可达）]
scp ubuntu@你的服务器公网IP:/tmp/iknowread-backup.tar.gz ~/Downloads/
```

确认下载并妥善保存后，在服务器删除临时副本：

```bash
# [Ubuntu 服务器]
rm /tmp/iknowread-backup.tar.gz
```

建议使用加密磁盘或可信的加密备份存储。备份文件越多，占用 40GB 磁盘越快；在确认异地副本有效后手动淘汰过旧备份，不要盲目清空整个备份目录。

#### 11.3 可选：每天自动备份

先手动成功备份一次，再运行：

```bash
# [Ubuntu 服务器] 可选定时备份；默认未启用
sudo crontab -e
```

加入：

```cron
# [Ubuntu 服务器的 root crontab；按服务器时区运行]
0 3 * * * /bin/bash /opt/iknowread/deploy/backup.sh > /var/log/iknowread-backup.log 2>&1
```

这会按**服务器时区**每天 03:00 执行；先用 `timedatectl` 确认时区。日志覆盖保存最近一次输出，但备份目录不会自动清理，必须定期下载、验证和淘汰旧副本。这只是你自行配置的服务器 cron，并不表示本文已经替你安装了定时任务。

**Windows/macOS 的自动化区别**：不要把 Ubuntu `crontab`、`/var/log` 当作 Windows PowerShell/macOS 完全通用命令，也不要把 Docker Desktop 随登录启动当作可靠备份调度。长期正式运营推荐将备份计划放在 Ubuntu 生产主机或受管控的独立备份执行环境。当前项目仍未实际启用异地备份和自动保留；此处的“可选”只是操作说明。

### 12. 版本更新、迁移兼容与回滚

每次更新先确认有可恢复备份，再构建。数据库启动迁移可能改变结构，因此“只换回旧镜像”不一定能安全回退。

```bash
# [Ubuntu 服务器]
cd /opt/iknowread
sudo bash deploy/backup.sh
```

可额外保留当前镜像，假设 `.env` 中 `APP_TAG=local`：

```bash
# [Ubuntu 服务器] 保护原有 local 镜像标签，避免被后续构建覆盖
sudo docker image tag iknowread-backend:local iknowread-backend:previous
sudo docker image tag iknowread-web:local iknowread-web:previous
sudo docker image tag iknowread-mysql:local iknowread-mysql:previous
```

将新版源码按 §4 的打包上传步骤重新打包并上传。更新时不能直接覆盖解压：普通解压不会删除新版已经移除的旧源码，可能让旧模块继续进入构建上下文。先校验到临时目录，再用 `rsync --delete` 精确同步，同时保护生产配置和数据：

```bash
# [Ubuntu 服务器] 校验新包，临时目录增量替换源码，保留生产配置/数据
cd /tmp
sha256sum -c iknowread-source.tar.gz.sha256
release_dir="$(mktemp -d /tmp/iknowread-release.XXXXXX)"
tar -xzf iknowread-source.tar.gz -C "$release_dir"
sudo apt-get install -y rsync
sudo rsync -a --delete \
  --exclude='.env' \
  --exclude='runtime/' \
  --exclude='backups/' \
  "$release_dir/" /opt/iknowread/
rm -rf "$release_dir"
cd /opt/iknowread
sudo docker compose config --quiet
```

同步前的源码包必须继续排除根目录 `.env`、`runtime`、`backups` 和本机 `fastapi-app/data`。`rsync` 的三个排除项会同时阻止删除服务器上的生产配置、运行数据和备份；不要增加 `--delete-excluded`。如果在 `/opt/iknowread` 手工保存了其他文件，应先移出项目目录，否则精确同步会删除它们。

如果从旧版 root Caddy 首次升级到当前非 root 镜像，先停止 Web，再把已有证书卷所有权交给固定 UID/GID 10002。新安装不需要这一步：

```bash
# [Ubuntu 服务器] 仅旧版 root Caddy 升级时执行；其他系统先核对实际卷名
sudo docker compose stop web
sudo docker run --rm -u 0 \
  -v iknowread_caddy_data:/data \
  -v iknowread_caddy_config:/config \
  alpine:3.23@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0 \
  chown -R 10002:10002 /data /config
```

先用 `sudo docker volume ls | grep caddy` 核对卷名；如果 Compose 项目名不是 `iknowread`，应使用实际卷名，不能照抄后误改其他项目。该命令只调整 Caddy 证书和配置卷，不要用于 MySQL 卷。

为控制 4GB 机器在构建期间的内存峰值，可安排维护窗口。发布检查已经包含构建、测试和审计，通过后再启动：

```bash
# [Ubuntu 服务器] 在维护窗口执行，已备份并保留 previous 镜像
sudo docker compose stop
sudo bash deploy/release-check.sh --scan
sudo docker compose up -d --no-build
sudo docker compose ps
curl -fsS https://read.example.com/api/ready
```

服务器没有 Scout 时，只能在同一源码与目标架构已于开发机/CI 扫描通过的前提下，将第二条改为 `sudo bash deploy/release-check.sh`。一条成功后再执行下一条。如果发布检查失败，停止的旧容器仍指向原镜像，可先执行 `sudo docker compose start` 恢复旧服务，再修复源码；不要用失败过程中部分生成的 `local` 镜像创建新容器，也不要反复运行全量清理命令。备份中的部署配置和源码可用于恢复原版本。

**原稿在 2026-10-19 的源码快照记录**迁移共有 14 个版本：版本 7 增加会话撤销；版本 8～10 依次增加文档内容版本、统一来源锚点和持久化高亮；版本 11 增加回收站状态，版本 12 规范化用户名，版本 13 增加文档处理任务状态，版本 14 清理未实现任务类型的占位记录。应用还会为既有迁移记录补写校验和，以后若已执行的迁移文件被改动会拒绝启动。升级会保留账号、文档、笔记、AI 配置和已有文件，不应手工修改 `schema_migration`、删除字段或改写历史迁移文件。升级前签发的旧格式会话可能失效，用户需要重新登录。

正常更新**不要顺手更新 MySQL 大版本**。需要升级数据库时，应先查对应版本的官方升级路径，并在备份副本上验证。

仅当数据库结构与旧代码兼容时，可以在 `.env` 将 `APP_TAG=local` 改成 `APP_TAG=previous`，然后执行：

```bash
# [Ubuntu 服务器] 仅确认数据库结构兼容旧程序后可尝试镜像回滚
sudo docker compose up -d --no-build db backend web
```

回滚后执行 `docker compose ps`、`/api/ready` 和第 8 节业务检查。再次升级前把 `.env` 的 `APP_TAG` 改回 `local`。若迁移不兼容，按下一节恢复备份配套的数据、源码、配置；恢复会丢失备份时间点之后的新改动，因此应先另存当前状态。

**桌面系统参与发布时**：推荐只负责构建、在目标架构运行门禁与传输“已检查”的镜像。生产上的数据库迁移、备份和版本切换仍在 Ubuntu 执行。严禁以“桌面构建成功”替代生产 `ready`、HTTPS 和兼容性验证。

### 13. 在全新空主机上恢复完整备份

以下操作命令均为 **[Ubuntu 服务器]**；流程面向**新的空部署环境**，不要直接覆盖仍承载正式业务的服务器。

1. 按第 2～3 节准备新服务器和 Docker。
2. 上传完整备份包并校验。
3. 解压源码、部署配置和数据，确认或修改恢复后的域名。
4. 构建镜像，启动空 MySQL，确认没有业务表后导入 SQL。
5. 启动应用，更新域名解析，重新验收。

以下假设备份目录最终位于 `/opt/iknowread/backups/20261012T120000Z`：

先确认目标机没有同名数据库卷：

```bash
# [Ubuntu 服务器] 确认空数据库卷
sudo docker volume ls --format '{{.Name}}' | grep -x 'iknowread_mysql_data' || true
```

全新服务器应没有输出。如果出现 `iknowread_mysql_data`，说明这台机器曾创建过同名部署，不能继续按“空环境恢复”；先确认卷中数据归属，不要直接删除或覆盖。

```bash
# [Ubuntu 服务器] 校验归档后再恢复文件
sudo mkdir -p /opt/iknowread/backups
sudo tar -xzf /tmp/iknowread-backup.tar.gz -C /opt/iknowread/backups
cd /opt/iknowread
sudo test -f backups/20261012T120000Z/COMPLETE
sudo sh -c 'cd /opt/iknowread/backups/20261012T120000Z && sha256sum -c SHA256SUMS'
```

只有全部校验成功后继续。解压部署配置后，先决定恢复使用哪个域名：继续使用原域名时确认 DNS 将切换到新服务器；改用新域名时，在执行配置检查和启动容器前用 `sudo nano .env` 修改 `DOMAIN` 和需要更新的 `ACME_EMAIL`。不要重新生成或改动数据库密码和 `AUTH_SECRET`。

```bash
# [Ubuntu 服务器] 从已验证完整备份恢复同版本部署配置、源码和文件
sudo tar -xzf backups/20261012T120000Z/deployment.tar.gz -C /opt/iknowread
sudo tar -xzf backups/20261012T120000Z/source.tar.gz -C /opt/iknowread
sudo mkdir -p runtime
sudo tar -xzf backups/20261012T120000Z/app-data.tar.gz -C runtime
sudo chown -R 10001:10001 runtime/app-data
sudo chmod 700 runtime/app-data
sudo chmod 600 .env
sudo grep -E '^(DOMAIN|ACME_EMAIL|APP_TAG)=' .env
```

根据输出检查域名、邮箱和标签。如果需要修改，运行 `sudo nano .env`。`APP_TAG` 必须是 `local`，因为恢复流程将构建 `local` 镜像。修改完成后再次运行上面的 `sudo grep`，确认无误再执行：

```bash
# [Ubuntu 服务器] 使用同一套生产配置和对应镜像
sudo grep '^APP_TAG=local$' .env
sudo docker compose config --quiet
sudo bash deploy/release-check.sh
sudo docker compose up -d --no-build db
sudo docker compose ps
```

`APP_TAG` 检查必须输出 `APP_TAG=local`。有 Scout 时可把发布检查改为 `sudo bash deploy/release-check.sh --scan`。

等待 db 显示 `healthy`。导入前确认新数据库还没有任何业务表；以下命令应无输出：

```bash
# [Ubuntu 服务器] 校验此时尚无业务表
sudo docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -N -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "SHOW TABLES"'
```

若列出了表，停止恢复并调查当前卷，不能把备份覆盖到已有数据库。确认无输出后再导入：

```bash
# [Ubuntu 服务器] 仅空业务库可执行此恢复导入
sudo bash -o pipefail -c 'gzip -dc backups/20261012T120000Z/database.sql.gz | docker compose exec -T db sh -c '\''MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'\'''
```

导入正常完成后再启动后端和 Web，避免应用先迁移或创建新管理员：

```bash
# [Ubuntu 服务器] 完成导入后启动业务服务
sudo docker compose up -d --no-build backend web
sudo docker compose ps
curl -fsS https://read.example.com/api/ready
```

恢复 `.env` 后**不要再运行初始化脚本生成新密码**。新 MySQL 卷会使用恢复的密码初始化，AI 配置则依靠恢复的数据目录中的原密钥解密。

启动 Web 前应已按上文确认 `.env` 域名，并将对应 A 记录指向新服务器。若启动后才发现域名写错，使用 `sudo nano .env` 修改 `DOMAIN`，然后执行 `sudo docker compose up -d --no-build backend web` 重新创建相关容器。

本备份不包含 Caddy 证书卷，新服务器会重新申请证书。因此必须保证域名验证畅通；不要反复重建空服务器触发无谓的证书申请。恢复后使用原管理员密码登录，通常不会生成新的初始密码文件。

推荐先做一次演练：至少验证旧文档可打开、笔记存在、AI 配置仍能调用。只有真正恢复过，才知道备份是否可用。

**跨平台恢复限制**：以上恢复顺序适用于新的 Linux Docker Engine 主机。Windows/macOS 的 Docker Desktop 也可能存在同名卷，但不要直接把 Ubuntu 的 `sudo tar`、UID 修正、存储路径和数据库恢复命令复制到 PowerShell；必须先核对 Linux VM 的卷位置、挂载行为并进行隔离演练。优先恢复到全新 Ubuntu 服务器，且恢复前验证 `iknowread_mysql_data` 与 `iknowread_app_data` **两个卷都不存在**，绝不覆盖正在服务的数据卷。

### 14. 迁移旧电脑的账号、文件与 AI 密钥

主流程部署的是空系统。要保留本机账号、笔记和文档，需要迁移数据库和完整的应用数据状态：

1. 本机 MySQL 数据库的 SQL 导出。
2. 本机实际文件存储目录，包括文档、头像和 OCR 派生文件。
3. `fastapi-app/data` 下的隐藏状态文件，包括存在时的 AI 加密密钥和初始管理员密码文件。

先停止本机后端，避免导出期间文档仍在修改；如果有重要数据，先保留独立副本。

本机数据库导出示例（**[macOS 终端 / Windows WSL2 / Linux Shell]**，需要兼容的 `mysqldump` 客户端；使用真实主机、端口、用户名与数据库名，密码通过 `-p` 提示输入）：

```bash
# [macOS 终端 / Windows WSL2 / Linux Shell] 使用真实库信息，手动输入密码
mysqldump -h 127.0.0.1 -P 3306 -u 你的数据库用户 -p \
  --single-transaction --no-tablespaces --set-gtid-purged=OFF \
  你的数据库名 > /tmp/iknowread-local.sql
```

这需要本机具备与源数据库版本兼容的 MySQL 客户端。如果没有 `mysqldump`，也可以用现有数据库管理软件导出完整结构和数据。先检查导出文件非空且命令成功，再传输。

迁移必须在云端后端**从未启动、数据库没有业务表**时进行。只启动 db，后端和 Web 保持停止，再准备导入容器的 `iknowread` 数据库：

```bash
# [Ubuntu 服务器] 迁移必须在空业务库、后端尚未初始化时进行
cd /opt/iknowread
sudo docker compose stop backend web
sudo docker compose up -d --no-build db
```

等 db 健康后先检查业务库。以下命令应无输出：

```bash
# [Ubuntu 服务器] 先确认业务表不存在
sudo docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -N -u"$MYSQL_USER" "$MYSQL_DATABASE" -e "SHOW TABLES"'
```

如果出现任何表名，说明后端曾经初始化过该库，不要继续覆盖；应改用第 13 节的全新空环境恢复思路。确认无输出并上传 SQL 后运行：

```bash
# [Ubuntu 服务器] 空数据库导入 SQL；实际上传的 SQL 文件必须经过独立检查
sudo docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot iknowread' < /tmp/iknowread-local.sql
```

默认情况下，本机 `fastapi-app/data` 与容器中的 `/app/data` 对应，应把它的**全部内容（包括隐藏文件）**迁移到服务器 `runtime/app-data`。推荐在本机项目目录打包，避免普通通配符遗漏点文件：

```bash
# [macOS 终端 / Windows WSL2 / Linux Shell] 从项目根目录打包，包括隐藏的密钥文件
COPYFILE_DISABLE=1 tar -czf /tmp/iknowread-app-data.tar.gz -C fastapi-app data
# [macOS / Windows WSL2 / Linux] 根据当前系统自动选 SHA256 工具
if [ "$(uname -s)" = Darwin ]; then
  shasum -a 256 /tmp/iknowread-app-data.tar.gz > /tmp/iknowread-app-data.tar.gz.sha256
else
  sha256sum /tmp/iknowread-app-data.tar.gz > /tmp/iknowread-app-data.tar.gz.sha256
fi
scp /tmp/iknowread-app-data.tar.gz /tmp/iknowread-app-data.tar.gz.sha256 \
  ubuntu@你的服务器公网IP:/tmp/
```

在服务器校验并解压；此操作只适用于前文确认过的空云端部署：

```bash
# [Ubuntu 服务器] 校验旧应用数据压缩包
cd /tmp
sha256sum -c iknowread-app-data.tar.gz.sha256
cd /opt/iknowread
sudo mkdir -p runtime/app-data
sudo tar -xzf /tmp/iknowread-app-data.tar.gz -C runtime/app-data --strip-components=1
```

如果本机 `.env` 设置了自定义 `UPLOAD_DIR`，文档可能不在 `fastapi-app/data/files`：仍要迁移 `fastapi-app/data` 中的隐藏状态文件，并把自定义上传目录的内容另外复制到云端 `runtime/app-data/files`。

默认 AI 密钥是 `fastapi-app/data/.ai-config-key`。如果本机用的是环境变量 `AI_CONFIG_KEY`，当前 Compose 模板没有传入它：必须将原始 Fernet 密钥通过受保护的文件传输，保存为云端 `runtime/app-data/.ai-config-key`，权限 `600`，不能生成替代密钥。没有保存过 AI 配置时，该文件不存在是正常情况。`fastapi-app/data/.initial-admin-password` 若存在也应随完整数据目录迁移；它与数据库中的初始管理员密码对应。

迁移完成后修正目录属主：

```bash
# [Ubuntu 服务器] 按容器固定 UID/GID 修复首次导入目录权限
sudo chown -R 10001:10001 runtime/app-data
sudo chmod 700 runtime/app-data
sudo test ! -f runtime/app-data/.ai-config-key || sudo chmod 600 runtime/app-data/.ai-config-key
sudo test ! -f runtime/app-data/.initial-admin-password || sudo chmod 600 runtime/app-data/.initial-admin-password
sudo docker compose up -d --no-build
```

启动时应用会核对存储并执行迁移，所以**必须先把 SQL、文件、密钥完整放好，再启动后端**。使用原有管理员密码登录并完成第 8 节检查。本节属于数据搬迁，不适合把旧数据直接合并进已有用户的云端数据库。

**必须区分“空部署迁移”与“已有云端数据合并”**。该流程只适用于全新空业务库的数据搬家，不支持将两边已有账号/文档直接合并。Windows/macOS 本地开发的文件路径、SQL 客户端版本和隐藏密钥位置应先逐项核实，再执行 Ubuntu 端的导入；绝不能以新密钥代替旧 `.ai-config-key`。

### 15. 故障排查：先定位层次，再选择修复

#### 构建时出现 Alpine、GitHub 或 Docker Hub TLS 错误

如日志先出现 `fetching ... APKINDEX.tar.gz: TLS`，随后才显示 `git (no such package)`，通常不是 Dockerfile 中的包名错误，而是容器没有成功下载 Alpine 软件索引。如果安装依赖已经成功，但随后 `git clone https://github.com/tianon/gosu.git` 报 `TLS connect error` 或 `unexpected eof`，则是构建容器访问 GitHub 的 HTTPS 连接被中途断开。`failed to fetch oauth token`、`auth.docker.io ... EOF` 表示 Docker Hub 认证或镜像下载链路也不稳定。先检查服务器时间、DNS、出站 HTTPS 和 Docker 容器网络：

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
timedatectl status
curl -I https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/APKINDEX.tar.gz
curl -I https://github.com/tianon/gosu.git
curl -fsS 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/mysql:pull' >/dev/null
sudo docker run --rm \
  alpine:3.23@sha256:85fe1e81d6758c208f3e1eed4338a1997e19d4be002d4dd32d3100c9a8c010a0 \
  sh -c 'wget -q https://dl-cdn.alpinelinux.org/alpine/v3.23/main/x86_64/APKINDEX.tar.gz -O /dev/null && wget -q "https://github.com/tianon/gosu.git/info/refs?service=git-upload-pack" -O /dev/null'
```

原 Ubuntu 示例目标机为 x86_64，因此这里检查 `x86_64` 索引；若目标架构不同，必须换成对应镜像/索引并按镜像真实架构验证。命令全部成功后重新运行发布检查；偶发断线可以重试，持续失败则检查云平台出站策略、DNS、代理和运营商链路。不要因为下载失败就随意更换不可信镜像源、解除源码提交固定或使用失败过程中生成的部分镜像。

#### 网站打不开

依次检查：

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
dig +short A read.example.com
sudo docker compose ps
sudo docker compose logs --tail=100 web
sudo ss -lntp
```

确认 DNS 指向本机、云安全组开放 80/443、没有其他 Nginx/Apache 占用这两个端口。出现 `address already in use` 时先确认占用服务是什么，不要直接停止不认识的业务。

#### HTTPS 证书申请失败

检查 A/AAAA、80/443 入站、出站网络、系统时间，以及是否仍经过错误配置的 CDN。日志若指出 CAA 限制，应到域名 DNS 中检查证书颁发机构授权。先修正原因，再观察 Caddy 重试；不要不停删除证书卷。

#### 页面能打开，登录后马上退出

优先确认浏览器地址是 `https://`，域名与 `.env` 中一致，且不是 IP 的 HTTP 页面。项目生产 Cookie 需要 HTTPS。浏览器开发者工具可查看登录响应是否设置 Cookie、后续 `/api/me` 请求是否携带 Cookie。

再检查：

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo docker compose logs --tail=100 backend
```

不要改成 `DEBUG=true` 规避问题。

#### API 返回 404，或者返回网页 HTML

外部地址应是 `/api/health`，内部后端是 `/health`。确认使用了配套 Caddyfile 的 `handle_path /api/*`；前端生产 `VITE_BASE_URL` 应是 `/api`，不能是 `localhost:9090`。

Caddyfile 是构建进 web 镜像的，修改该文件后要重新执行发布门禁。门禁会重建并验证三个相互配套的镜像；通过后只替换 web 容器：

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo bash deploy/release-check.sh --scan
sudo docker compose up -d --no-build web
```

服务器没有 Scout 时，按第 6 节说明在受信任开发机或 CI 扫描同一提交与目标架构；不要用一次未验收的 `docker compose build web` 直接覆盖当前镜像。

#### 502 / 504 或 backend unhealthy

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo docker compose logs --tail=150 backend db web
sudo docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9090/ready').read().decode())"
```

如果容器没有运行，`exec` 会失败，先看日志。重点检查数据库连接、迁移异常、数据目录权限和内存。健康检查失败本身不会自动触发 Docker 重启；自动重启策略主要处理容器进程退出，需要修复实际故障。

#### MySQL 报 Access denied

数据库初始化环境变量只在空数据目录初始化时生效。如果 MySQL 已运行过，单改 `.env` 密码不会改变数据库内已有账号密码。

先恢复原来的 `.env` 密码；需要轮换密码时，应同时修改数据库中的用户密码和环境变量，并重新创建相关容器。不要通过删除数据库卷来“修复”正式系统。

#### `Permission denied` / 数据文件写入失败

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo docker compose logs --tail=100 app-data-init backend
sudo docker compose run --rm --no-deps --entrypoint sh backend -c 'id; ls -ld /app/data; test -w /app/data'
```

正式数据位于 `app_data` 命名卷。不要通过修改宿主机旧目录权限来修复已有卷，也不要删除卷。若是旧数据导入失败，检查 `app-data-init` 日志和旧目录 UID 10001 的读取权限。

#### 上传中断或超时

文件不能超过应用限制。后端还会验证 PDF/DOCX 结构、PDF 页数、DOCX 解压大小与压缩比；仅修改文件扩展名不会被接受。Caddy 已允许较大的请求体。文档与头像上传在解析 multipart 正文前共用 3 个并发槽，排队超过 1 秒会返回 429，以免多份大文件同时耗尽后端 850MiB 内存上限和 256MiB 临时盘；等待片刻后再重试，不要通过增加 Uvicorn worker 绕过这个边界。文档上传由 Element Plus 的原生上传实现发起，不使用项目通用 Axios 的 30 秒超时。

先用小于 5MB 的有效 PDF/DOCX 验证，再在开发者工具看具体失败请求。若浏览器、运营商或云平台另有超时，应按实际失败层调整；不要直接把所有请求无限等待。

#### OCR 失败或服务器很慢

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo docker compose logs --tail=150 backend
sudo docker stats --no-stream
free -h
sudo journalctl -k --since '1 hour ago' | grep -Ei 'oom|out of memory|killed process'
```

还可检查后端是否被 OOM 杀死：

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
sudo docker inspect "$(sudo docker compose ps -aq backend)" --format '{{.State.OOMKilled}}'
```

该字段只反映当前容器状态的一部分，需结合内核日志和重启记录。先关闭 OCR、使用更小样本并确认 Swap。若只有 backend 因 850MiB 容器上限被杀，应先保持 OCR 关闭，再根据实测谨慎调整 Compose 的后端内存上限；若宿主机整体内存不足，再考虑升级内存。

#### AI 提示密钥无法解密

检查是否恢复了原 `.ai-config-key`。重新生成密钥无法解密原记录；找不到旧密钥时只能让各账号重新填写 API Key。

#### 磁盘越来越满

```bash
# [Ubuntu 服务器] 默认在 /opt/iknowread 项目根目录执行；Desktop 本地排障须按系统替换
df -h /
sudo docker compose exec -T backend du -sh /app/data
sudo du -sh backups
sudo docker system df
```

优先处理已验证有异地副本的过旧备份和确认不再需要的构建缓存。`sudo docker builder prune` 会询问后清理闲置构建缓存，后续构建会重新下载部分内容；保留回退镜像和所有正式数据卷。

#### 15.1 按系统补充排查（别混用宿主命令）

| 现象 | Ubuntu 服务器 | Windows / WSL2 | macOS |
|---|---|---|---|
| `docker` 连接不到引擎 | `sudo systemctl status docker`；检查权限与 daemon | Docker Desktop 状态、WSL Integration、Linux containers；核对当前 Docker context | Docker Desktop 状态和 `docker context ls` |
| `address already in use` | `sudo ss -lntp` | PowerShell：`Get-NetTCPConnection -State Listen`，以及 IIS/本地代理端口 | `lsof -nP -iTCP:80 -sTCP:LISTEN` 等 |
| 存储权限错误 | `app-data-init` / backend 日志、UID/GID 10001、卷属主 | WSL Linux 路径与 NTFS bind mount 差异；确认不是 `/mnt/c` | File Sharing、文件属主/卷、Docker Desktop Linux VM |
| 构建 OOM | `free -h`、`journalctl -k`、`docker stats` | Docker Desktop / WSL 内存资源，Windows 任务管理器 | Docker Desktop Resources、活动监视器 |
| 浏览器能打开但无法登录 | HTTPS/Cookie Secure/域名一致性 | 同左；不得以 localhost HTTP 作为生产验收 | 同左；不得以 localhost HTTP 作为生产验收 |

不管哪个平台，优先查看 `docker compose ps`、`docker compose logs --tail=150 db backend web` 与 `/api/ready`，不要以删数据卷作为故障修复方法。

### 16. 跨架构构建后向 Ubuntu 生产主机传镜像

适用于服务器构建资源不足。自己的电脑需要 Docker 引擎正在运行：**Windows WSL2** 和 **macOS** 都需要先启动 Docker Desktop。Apple 芯片 Mac 不能直接把默认 ARM 镜像交给 x86 服务器，必须明确指定目标平台。

先在 Ubuntu 服务器运行 `uname -m` 确认架构。以下示例针对 **x86_64 服务器**，在**[macOS 终端 / Windows WSL2]** 的本地项目根目录执行。`TARGET_PLATFORM` 会让发布门禁直接构建、测试并扫描最终要上传的 `linux/amd64` 镜像：

```bash
# [macOS 终端 / Windows WSL2] 先 cd 到自己的项目根目录
env TARGET_PLATFORM=linux/amd64 bash deploy/release-check.sh --scan
docker image inspect \
  iknowread-backend:local iknowread-web:local iknowread-mysql:local \
  --format '{{.RepoTags}} -> {{.Os}}/{{.Architecture}}'
```

三行检查结果都应以 `linux/amd64` 结尾。服务器若是 `aarch64`，把目标值改为 `linux/arm64`，并确认三行结果一致。跨架构模拟构建和测试可能很慢；命令失败就先修复，不要打包失败前遗留的旧 `local` 镜像。

打包镜像并上传：

```bash
# [macOS 终端 / Windows WSL2] 保存刚验收的同一组三镜像
bash -o pipefail -c 'docker save iknowread-backend:local iknowread-web:local iknowread-mysql:local | gzip > /tmp/iknowread-images.tar.gz'
# [macOS / Windows WSL2] 根据当前系统自动选 SHA256 工具
if [ "$(uname -s)" = Darwin ]; then
  shasum -a 256 /tmp/iknowread-images.tar.gz > /tmp/iknowread-images.tar.gz.sha256
else
  sha256sum /tmp/iknowread-images.tar.gz > /tmp/iknowread-images.tar.gz.sha256
fi
scp /tmp/iknowread-images.tar.gz ubuntu@你的服务器公网IP:/tmp/
scp /tmp/iknowread-images.tar.gz.sha256 ubuntu@你的服务器公网IP:/tmp/
```

服务器仍需按前文准备代码目录、Compose、`.env`、持久化目录和 Docker，然后加载：

```bash
# [Ubuntu 服务器] 检查 sha256、加载刚验收的生产架构镜像，禁止加载后再次构建
cd /tmp
sha256sum -c iknowread-images.tar.gz.sha256
sudo docker load -i /tmp/iknowread-images.tar.gz
cd /opt/iknowread
sudo grep '^APP_TAG=local$' .env
sudo docker compose up -d --no-build
```

校验、加载和 `APP_TAG` 检查三步都成功后才能启动。三个运行镜像都来自刚才通过目标架构发布门禁的结果。镜像压缩包可能很大，必须留足上传、解压和 Docker 存储空间；确认加载成功后可删除服务器上的压缩包和校验文件。

**注意两种平台标签**：`docker image inspect` 在上传前必须看到目标 `linux/amd64`（x86_64 服务器）或 `linux/arm64`（aarch64 服务器），且确认 `release-check.sh --scan` 检查的是**相同的提交、架构和 `local` 镜像**。`docker save` 不等于漏洞门禁；服务器 `docker load` 后不要又运行 `docker compose build` 覆盖同一标签。

### 17. 最终检查单与风险留档

以下项目应逐项实际验证。任何“跳过”都应记录为风险，不要直接打勾。

#### 核心部署

- [ ] HTTPS 正常，HTTP 会跳转。
- [ ] HTTPS 响应包含短周期 HSTS，正式域名观察稳定后再决定是否延长。
- [ ] 数据库和后端没有公网映射端口。
- [ ] `[Ubuntu] sudo bash deploy/release-check.sh --scan`，或 `[macOS / Windows WSL2] bash deploy/release-check.sh --scan`，已在**目标架构**或受信任 CI 真正通过（无 Scout 不冒充通过）。
- [ ] `.env` 中 `APP_TAG=local`，启动使用 `[Ubuntu] sudo docker compose up -d --no-build` 或 `[Desktop] docker compose up -d --no-build`。
- [ ] 初始管理员密码已经修改。
- [ ] 自助注册和 OCR 均保持关闭。
- [ ] 有效 PDF/DOCX、无效文件拒绝、阅读、下载、笔记、高亮、回收站恢复和导出通过。
- [ ] 重启后账号、文件、笔记和高亮仍然存在。
- [ ] 最近一次备份存在 `COMPLETE`，且 `verify-backup.sh` 隔离恢复验证通过。

#### 条件功能

- [ ] AI 不作为首发前置条件；用户自行配置后，按其供应商账号单独测试。
- [ ] OCR 首发不启用；以后若开启，先完成小扫描件、异常文件、内存、Swap 和超时测试。

#### 当前已接受但尚未消除的风险

- [ ] 尚未配置异地备份、自动保留、备份加密和失败告警；已理解同盘故障可能丢失全部数据。
- [ ] 尚未配置公网和资源告警；已安排人工检查 `/api/ready`、容器、磁盘和月流量。
- [ ] 若沿用原示例规格，尚未在目标 4 核 4GB、40GB SSD、3Mbps 峰值带宽环境完成压力与恢复演练，不能把本地 ARM64 验证视为目标机容量结论。
- [ ] 尚未完成正式域名、受信任证书续期和长周期 HSTS 验收；未完成前不能宣称公网生产验收通过。

配套文件中的所有正式密码都由你在服务器上生成。本地验证仅使用一次性凭据；本文没有访问你的服务器，也没有发布任何线上服务；跨平台步骤为依据原项目部署约定和 Docker 官方文档的迁移说明，不代表已在三套操作系统上实际跑过项目全量脚本。


---

## 参考资料与后续扩展约定

| 范围 | 官方文档 | 在本教程中的作用 |
|---|---|---|
| Ubuntu Docker Engine | https://docs.docker.com/engine/install/ubuntu/ | 发行版安装与防火墙注意事项 |
| Windows Docker Desktop | https://docs.docker.com/desktop/setup/install/windows-install/ | Windows 安装和版本要求 |
| Windows WSL2 | https://docs.docker.com/desktop/features/wsl/ | Linux 容器、WSL 集成和文件路径 |
| macOS Docker Desktop | https://docs.docker.com/desktop/setup/install/mac-install/ | Apple Silicon / Intel 安装与资源要求 |
| Compose `!override` | https://docs.docker.com/reference/compose-file/merge/ | `2.24.4+` 的兼容性要求 |
| Caddy 自动 HTTPS | https://caddyserver.com/docs/automatic-https | 域名、证书与续期 |
| Docker Scout | https://docs.docker.com/scout/install/ | 可修复高危漏洞发布门禁 |

**维护约定**：更新 Docker 安装步骤时，只改 §3 相应操作系统小节；更新应用配置、镜像构建、运行和恢复时，只改 §5～§17 的公共阶段。跨平台差异用 `[Ubuntu 服务器]`、`[Windows PowerShell]`、`[Windows WSL2]`、`[macOS 终端]` 标记。新增功能先落实到仓库实际脚本，再更新本文，不要让文档中的假设变成未经验证的操作指令。

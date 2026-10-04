# TG Checkin

> 用你自己的 Telegram 账号，定时给机器人 / 群聊自动签到，并把结果推送给你。
> 带 Web 管理面板，一条命令部署到服务器。

[![CI](https://github.com/tmclsamxy/tg-checkin/actions/workflows/ci.yml/badge.svg)](https://github.com/tmclsamxy/tg-checkin/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

TG Checkin 是一个自托管的 Telegram 自动签到服务。它以**你的用户账号**（不是 bot）登录 Telegram，
按设定时间向指定机器人发送签到命令或点击内联按钮，并把机器人回复汇总推送给你。

```
┌─────────────────────────────────────────────────────────┐
│  浏览器 ──▶ Vue 3 面板 ──▶ FastAPI ──▶ Telethon ──▶ Telegram │
│                              │                              │
│                        SQLite(任务/日志)                     │
│                        APScheduler(每日定时)                 │
└─────────────────────────────────────────────────────────┘
```

---

## ✨ 主要特性

| | |
|---|---|
| **多种签到方式** | 向机器人发消息（`/sign`、`签到`）、点击**文字按钮**或**内联回调按钮**、向群聊发消息 |
| **自动过人机验证** | 识别「请计算 11 + 15 = ？」这类算术验证码，自动算出答案并点击正确选项；识别不出来时保持原样不乱点 |
| **Web 管理面板** | 任务增删改查、启停开关、单条/全部立即执行、运行日志与统计 |
| **登录流程可视化** | 在网页里填 API 凭据 → 收验证码 → 填验证码 / 两步验证密码，无需命令行 |
| **结果通知** | 签到结束后把汇总报告推送到 Telegram（可用专属 bot，也可直接用本人账号） |
| **运行可追溯** | 每次执行都记录状态、机器人回复、耗时、触发方式（定时/手动） |
| **凭据加密** | API Hash、Bot Token、登录会话在数据库中均以 Fernet 加密存储 |
| **抗风控** | 任务之间可配置间隔、失败自动重试、自动处理 Telegram FloodWait |
| **一条命令部署** | `./scripts/deploy.sh` 自动构建镜像并启动 |

---

## 🚀 快速开始

要求：一台装了 Docker 与 Docker Compose 的服务器（Linux，内存 512MB 足够）。

### 方案 A：从源码构建（默认）

```bash
git clone https://github.com/tmclsamxy/tg-checkin.git
cd tg-checkin
docker compose up -d
```

一条命令就够：compose 在本地没有镜像时会**自动构建**前后端并后台启动。
打开 `http://<服务器IP>:8000`，用 `admin` / `admin123` 登录（**登录后请立刻改密码**）。

```bash
docker compose logs -f         # 看日志
docker compose down            # 停止并移除容器
docker compose up -d --build   # 源码更新后强制重新构建
```

### 方案 B：用预构建镜像（不用装 Node、不用拉源码）

CI 每次推送都会把镜像发布到 GHCR（`linux/amd64` + `linux/arm64`）。
服务器上只需要一个 compose 文件：

```bash
curl -O https://raw.githubusercontent.com/tmclsamxy/tg-checkin/main/docker-compose.hub.yml
docker compose -f docker-compose.hub.yml up -d
```

升级：

```bash
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d
```

### 自定义端口 / 管理员密码

两个 compose 文件的变量都有默认值，**不建 `.env` 也能跑**。要改就在仓库根目录建一个：

```bash
cp .env.example .env
```

```ini
PORT=9000                 # 监听端口
ADMIN_PASSWORD=换成强密码  # 仅首次启动生效
TZ=Asia/Shanghai
```

改完 `docker compose up -d` 重新创建容器即可。

> 也可以用 `./scripts/deploy.sh`（可选）：交互选端口、占用时自动推荐空闲端口、
> 启动后等健康检查并打印访问地址。它只是 `docker compose` 的一层封装，不用也能正常部署。
>
> ```bash
> ./scripts/deploy.sh -p 9000   # 指定端口
> ./scripts/deploy.sh port      # 查看当前端口
> ./scripts/deploy.sh update    # 拉代码 + 重新构建
> ./scripts/deploy.sh logs      # 日志
> ./scripts/deploy.sh stop      # 停止
> ```

### 反向代理（可选，推荐）

用 Nginx 套一层 HTTPS，避免明文传输密码：

```nginx
server {
    listen 443 ssl;
    server_name tg.example.com;
    ssl_certificate     /etc/letsencrypt/live/tg.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tg.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 🛠 手动部署（不用 Docker）

需要 Python 3.11+ 与 Node 18+。

```bash
./scripts/deploy.sh local
```

等价的手工步骤：

```bash
cd frontend && npm install && npm run build && cd ..   # 产出 backend/app/static
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
export DATA_DIR=./data ADMIN_PASSWORD='换成强密码'
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

生产环境建议用 systemd 托管，示例见 [`deploy/tg-checkin.service`](./deploy/tg-checkin.service)。

---

## 📖 使用指南

### 1. 获取 Telegram API 凭据

访问 <https://my.telegram.org/apps>，用手机号登录后创建一个应用，得到 **App api_id** 与 **App api_hash**。

### 2. 登录 Telegram 账号

面板 → **Telegram 账号** → 填入 api_id / api_hash / 手机号 → 点「发送验证码」→
把 Telegram 收到的验证码填进去（开了两步验证的话再填一次云端密码）。

登录成功后会话会加密存进数据库，重启服务也不掉线。

### 3. 添加签到任务

面板 → **签到任务** → 「新建任务」：

- **机器人**：填用户名（如 `@sgkboxbot`）
  - 动作选「发送消息」→ 填 `/qd` 之类的命令，或「点击按钮」→ 按按钮文字 / 回调数据匹配
  - 可选「启动命令」，会先发 `/start` 唤醒机器人菜单再执行
- **群组 / 频道**：填群 ID（`-1001234567890`）或 `@群用户名`，动作固定为发送消息

> **如何拿到回调数据？** 用 Telegram 桌面版或 `@JsonDumpBot` 之类工具查看按钮的 `callback_data`。

### 3.1 自动通过人机验证

有些机器人在签到前会弹一道验证题，例如：

```
🤖 人机验证：请计算 11 + 15 = ？
请选择正确答案继续操作：
[26] [27] [28] [25]
```

面板默认开启**自动解答**（任务表单里也有单独的开关，可按任务关闭）：

- 发送签到后会在新消息里寻找这类题目，**算出答案并点击数值匹配的按钮**
- 支持 `+ - × ÷`、`* / x`、中文运算符（`加` `减去` `乘以` `除以`）和中文数字（`六 + 三`）
- 另外覆盖「请选择最大的数字」和「请点击『确认』」两种常见变体
- 有些机器人会连续出题，可作答轮数在「系统设置 → 人机验证」里调整（默认 2 轮，设 0 关闭）

**安全性**：只在能确定答案时才点击。题目里找不到算式、或算出的答案不在选项里，就什么都不做，
交给原来的重试逻辑 —— 所以普通的功能菜单不会被误点。算式由内置解析器求值，不会执行题目里的任意文本。

### 4. 配置时间与通知

面板 → **系统设置**：设置每日执行时间（如 `08:00`）、时区、任务间隔、失败重试次数，
以及是否开启结果通知和接收者 ID（填 `me` 就是发到「已保存的消息」）。

---

## 🔄 从旧版脚本迁移

如果你之前用的是单文件版 `telegram_user_checkin.py`，可以一键导入 `checkin_tasks.json`：

```bash
# 先启动一次服务让数据库初始化（或直接指定 DATA_DIR）
export DATA_DIR=./data
python tools/import_legacy.py /path/to/checkin_tasks.json --dry-run   # 先预览
python tools/import_legacy.py /path/to/checkin_tasks.json             # 正式导入
```

旧的 `telegram_api.json` / `notification_config.json` 内容请在「系统设置」页面重新填写一次
（旧版是明文存储在 JSON 里，新版会加密入库）。

---

## ⚙️ 配置项

### 环境变量（`.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | 面板管理员用户名，仅首次启动时生效 |
| `ADMIN_PASSWORD` | *空* | 留空则使用 `admin123` 并在面板提示修改 |
| `SECRET_KEY` | *自动生成* | JWT 签名与凭据加密的种子。**迁移服务器要带走它**，否则已存的会话无法解密 |
| `DATA_DIR` | `./data` | SQLite 数据库与密钥文件目录 |
| `PORT` | `8000` | 监听端口（也可 `./scripts/deploy.sh -p 9000` 设置） |
| `TZ` | `Asia/Shanghai` | 容器时区 |
| `DEBUG` | `false` | 开启 `/api/docs` 与宽松 CORS，仅用于本地开发 |

### 面板可调参数

| 参数 | 默认 | 说明 |
|---|---|---|
| 每日执行时间 | `08:00` | 按服务器时区，支持任意 `HH:MM` |
| 时区 | `Asia/Shanghai` | 例如 `UTC`、`America/New_York` |
| 等待回复秒数 | `8` | 发送签到后等待机器人回复的时间 |
| 启动命令后等待 | `5` | 发完 `/start` 后等待多久再执行动作 |
| 任务间隔秒数 | `5` | 相邻任务之间的间隔，降低风控概率 |
| 失败重试次数 | `1` | 单个任务失败后的重试次数 |
| 自动解答人机验证 | 开启 | 遇到算术验证码时自动作答；可在单个任务里单独关闭 |
| 最多连续作答轮数 | `2` | 机器人连续出题时的上限，`0` 表示关闭 |
| 作答后等待秒数 | `5` | 点完选项后等待机器人继续回复的时间 |
| 通知 | 关闭 | 可选择只在失败时通知 |

---

## 📁 目录结构

```
tg-checkin/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口、静态文件托管
│   │   ├── config.py            # pydantic-settings 配置
│   │   ├── database.py          # SQLAlchemy 异步引擎
│   │   ├── models.py            # ORM：User / AppSetting / Task / RunLog
│   │   ├── schemas.py           # 请求与响应模型
│   │   ├── security.py          # PBKDF2 密码哈希 / JWT / Fernet 加密
│   │   ├── runner.py            # 执行编排 + 日志落库 + 汇总通知
│   │   ├── scheduler.py         # APScheduler 每日定时
│   │   ├── telegram/
│   │   │   ├── manager.py       # Telethon 登录流程与会话持久化
│   │   │   ├── executor.py      # 单个任务的签到执行引擎
│   │   │   └── captcha.py       # 人机验证识别与作答（纯逻辑，无副作用）
│   │   └── routers/             # auth / telegram / tasks / runs / settings / system
│   ├── static/                  # 前端构建产物（gitignore）
│   └── tests/
├── frontend/                    # Vue 3 + Vite 面板
├── scripts/deploy.sh            # 可选的部署封装（端口选择 / 健康检查）
├── tools/import_legacy.py       # 旧版任务导入
├── Dockerfile                   # 多阶段构建（Node → Python）
├── docker-compose.yml           # 从源码构建并启动
└── docker-compose.hub.yml       # 拉取 GHCR 预构建镜像，免构建
```

---

## 🔌 API

所有接口前缀 `/api`，除 `/api/auth/login` 与 `/api/health` 外均需在请求头带
`Authorization: Bearer <token>`。开启 `DEBUG=true` 后访问 `/api/docs` 可查看完整 Swagger。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/login` | 登录获取 JWT |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/auth/password` | 修改密码 |
| GET | `/api/telegram/status` | 连接状态 |
| POST | `/api/telegram/request-code` | 保存凭据并请求验证码 |
| POST | `/api/telegram/verify-code` | 提交验证码 |
| POST | `/api/telegram/verify-password` | 两步验证密码 |
| POST | `/api/telegram/logout` | 退出并清除会话 |
| GET/POST/PUT/DELETE | `/api/tasks` `/api/tasks/{id}` | 任务增删改查 |
| POST | `/api/tasks/{id}/run` | 立即执行单个任务 |
| POST | `/api/tasks/run-all` | 立即执行全部 |
| GET | `/api/runs` | 运行日志（支持 `task_id` / `status` 过滤） |
| GET | `/api/runs/stats` | 统计 |
| GET/PUT | `/api/settings` | 读写配置（密钥仅返回掩码） |
| GET | `/api/system/info` | 版本、下次执行时间等 |

---

## 🔒 安全建议

1. **务必修改默认密码**，并用反向代理开启 HTTPS。
2. 不要把 `data/` 目录、`.env` 提交到仓库（已在 `.gitignore` 中）。
3. `SECRET_KEY` 决定了数据库中加密内容能否解密，备份时连同 `data/` 一起备份。
4. 本项目使用**你的个人 Telegram 账号**，请只在自己可控的服务器上部署；
   频繁自动化操作存在被 Telegram 限制的风险，建议把任务间隔设大一些。
5. 若不再使用，请在面板「Telegram 账号」中点击**退出并清除会话**。

---

## ❓ 常见问题

**验证码收不到？**
确认手机号带了国际区号（如 `+8613800138000`）；Telegram 可能把验证码发到「已保存的消息」
或另一台已登录设备上。也可以点「重新发送」。

**提示「尚未配置 Telegram API ID / API Hash」？**
去「Telegram 账号」页面重新登录一次。

**任务一直失败「未找到按钮」？**
机器人菜单可能变了。确认用了「启动命令」`/start`，或改用「按按钮文字」匹配；
也可以把「等待回复秒数」调大一点。

**换服务器后提示会话失效？**
把旧服务器的 `data/` 整个目录（含 `.secret_key`）复制到新服务器即可。

**面板打不开 / 端口冲突？**
改 `.env` 里的 `PORT`，或 `docker-compose.yml` 的端口映射。

**容器一直 `Restarting (1)`，端口连不上？**

镜像以非 root 用户（uid 10001）运行，而 Docker 为 bind mount 创建的宿主目录是 root 属主，
容器内写不了 SQLite，启动即崩溃。日志里会看到 `PermissionError`。

```bash
docker logs tg-checkin --tail 40      # 确认是不是权限问题
chown -R 10001:10001 data            # 修数据目录属主
docker compose up -d
```

不想管属主就改用**具名卷**（Docker 会自动继承镜像内的属主）：把 `docker-compose.yml` 里的

```yaml
    volumes:
      - tg-checkin-data:/app/data
volumes:
  tg-checkin-data:
```

**`docker compose up -d` 报 iptables / DOCKER-FORWARD 错误？**

```
failed to create network tg-checkin_default: Failed to Setup IP tables:
Unable to enable ACCEPT OUTGOING rule ... DOCKER-FORWARD: No chain/target/match
```

Docker 的 iptables 链没建起来（VPS 上很常见）。按顺序试：

```bash
systemctl restart docker                        # 1. 多数情况直接恢复

# 2. 仍失败：多半是 iptables 后端（nft / legacy）和 Docker 不一致
iptables --version
update-alternatives --set iptables /usr/sbin/iptables-legacy
update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy
systemctl restart docker

# 3. 兜底：直接用宿主机网络，完全绕开网桥与 iptables
docker compose -f docker-compose.hostnet.yml up -d
```

`docker-compose.hostnet.yml` 走 `network_mode: host`，容器直接占用宿主机端口，
不需要端口映射；换端口在 `.env` 里设 `PORT` 即可。

---

## 🧑‍💻 参与开发

```bash
# 后端
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && pytest -q

# 前端（热更新，自动代理到 :8000）
cd frontend && npm install && npm run dev
```

提交前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。

---

## 📄 许可证

[MIT](./LICENSE)

> 本项目与 Telegram 官方无关。使用自动化脚本请遵守 Telegram 服务条款，
> 因滥用导致的账号限制由使用者自行承担。

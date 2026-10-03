#!/usr/bin/env bash
# TG Checkin —— 一键部署 / 运维脚本
#
#   ./scripts/deploy.sh                首次部署（构建并启动，会询问监听端口）
#   ./scripts/deploy.sh -p 9000        指定端口部署
#   ./scripts/deploy.sh -p 9000 update 换端口并重新构建
#   ./scripts/deploy.sh update         拉取最新代码后重新构建
#   ./scripts/deploy.sh stop           停止服务
#   ./scripts/deploy.sh restart        重启服务
#   ./scripts/deploy.sh logs           查看实时日志
#   ./scripts/deploy.sh status         查看服务状态
#   ./scripts/deploy.sh port           查看当前端口
#   ./scripts/deploy.sh local          不使用 Docker，用本机 Python + Node 启动
#
# 选项：
#   -p, --port <1-65535>   指定监听端口（写入 .env，后续命令自动沿用）
#   -y, --yes              非交互模式，全部使用默认/已配置的值
#   -h, --help             显示本帮助
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
info()  { printf '%s[info]%s  %s\n'  "$GREEN" "$OFF" "$*"; }
warn()  { printf '%s[warn]%s  %s\n'  "$YELLOW" "$OFF" "$*"; }
error() { printf '%s[error]%s %s\n'  "$RED" "$OFF" "$*" >&2; }

DEFAULT_PORT=8000
PORT_ARG=""
ASSUME_YES=0
COMMAND=""
ENV_JUST_CREATED=0

usage() { sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^#\{1,2\} \{0,1\}//'; }

# --------------------------------------------------------------- .env 读写
env_get() {
  local key="$1" line
  [[ -f .env ]] || return 1
  line="$(grep -E "^${key}=" .env | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1
  printf '%s' "${line#*=}"
}

# Portable key=value upsert (no GNU/BSD sed -i difference).
env_set() {
  local key="$1" val="$2" tmp
  [[ -f .env ]] || cp .env.example .env
  tmp="$(mktemp)"
  awk -v k="$key" -v v="$val" '
    { i = index($0, "=")
      if (i > 0 && substr($0, 1, i - 1) == k) { print k "=" v; found = 1 }
      else print $0 }
    END { if (!found) print k "=" v }
  ' .env > "$tmp"
  mv "$tmp" .env
}

# ------------------------------------------------------------------- 端口
is_valid_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 1 && 10#$1 <= 65535 ))
}

port_in_use() {
  local p="$1"
  if command -v ss >/dev/null 2>&1; then
    if ss -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}$"; then return 0; fi
  fi
  if command -v netstat >/dev/null 2>&1; then
    if netstat -lnt 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}$"; then return 0; fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then return 0; fi
  fi
  # Last resort: try to connect (works with bash's /dev/tcp, unlike Windows netstat
  # whose column layout differs from Linux/BSD).
  if (exec 3<>"/dev/tcp/127.0.0.1/${p}") >/dev/null 2>&1; then return 0; fi
  return 1
}

next_free_port() {
  local p="$1" guard=0
  while port_in_use "$p" && (( guard < 100 )); do
    p=$((p + 1)); guard=$((guard + 1))
  done
  printf '%s' "$p"
}

prepare_env() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    ENV_JUST_CREATED=1
    warn "已生成 .env（来自 .env.example）—— 建议立刻修改 ADMIN_PASSWORD"
  fi
  mkdir -p data
}

# Decide which port to use: CLI flag > .env > interactive prompt > default.
resolve_port() {
  local current=""
  current="$(env_get PORT || true)"

  if [[ -n "$PORT_ARG" ]]; then
    if ! is_valid_port "$PORT_ARG"; then
      error "端口号无效：$PORT_ARG（应为 1-65535 的整数）"
      exit 1
    fi
    PORT="$PORT_ARG"
  else
    PORT="${current:-$DEFAULT_PORT}"
    # Ask on the very first run, or whenever the port has not been set yet.
    if [[ $ENV_JUST_CREATED -eq 1 || -z "$current" ]] && [[ -t 0 ]] && [[ $ASSUME_YES -eq 0 ]]; then
      read -r -p "$(printf '%s[ask]%s  监听端口 [%s]: ' "$GREEN" "$OFF" "$PORT")" answer || answer=""
      answer="${answer//[[:space:]]/}"
      if [[ -n "$answer" ]]; then PORT="$answer"; fi
      if ! is_valid_port "$PORT"; then
        error "端口号无效：$PORT（应为 1-65535 的整数）"
        exit 1
      fi
    fi
  fi

  if ! is_valid_port "$PORT"; then
    error "端口号无效：$PORT（应为 1-65535 的整数）"
    exit 1
  fi

  if [[ "$PORT" != "$current" ]]; then
    env_set PORT "$PORT"
    info "端口已写入 .env：PORT=$PORT"
  fi

  # Privileged ports need root; warn early instead of failing inside Docker.
  if (( PORT < 1024 )); then
    warn "端口 $PORT < 1024，Linux 上通常需要 root 权限才能绑定"
  fi

  if port_in_use "$PORT"; then
    warn "端口 $PORT 已被占用"
    if [[ -t 0 ]] && [[ $ASSUME_YES -eq 0 ]]; then
      local suggested; suggested="$(next_free_port "$PORT")"
      read -r -p "$(printf '%s[ask]%s  改用端口 %s？[Y/n] ' "$GREEN" "$OFF" "$suggested")" answer || answer=""
      if [[ ! "$answer" =~ ^[Nn] ]]; then
        PORT="$suggested"
        env_set PORT "$PORT"
        info "已改用端口 $PORT"
      fi
    else
      local suggested; suggested="$(next_free_port "$PORT")"
      warn "非交互模式下将继续使用 $PORT；若启动失败请改用 $suggested 后重试"
    fi
  fi

  export PORT
}

# --------------------------------------------------------------- docker
detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    error "未检测到 Docker Compose，请先安装 Docker（https://docs.docker.com/engine/install/）"
    exit 1
  fi
}

check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    error "未检测到 docker 命令，请先安装 Docker"
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    error "Docker 守护进程未运行，或当前用户无权限（可尝试 sudo usermod -aG docker \$USER）"
    exit 1
  fi
}

wait_healthy() {
  info "等待服务就绪 (http://127.0.0.1:${PORT}/api/health) ..."
  for _ in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      info "服务已就绪"
      return 0
    fi
    sleep 2
  done
  warn "健康检查超时，请执行 ./scripts/deploy.sh logs 查看日志"
}

local_ip() {
  local ip=""
  if command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  if [[ -z "$ip" ]] && command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 addr show scope global 2>/dev/null | awk '/inet /{print $2; exit}' | cut -d/ -f1)"
  fi
  printf '%s' "${ip:-<服务器IP>}"
}

# --------------------------------------------------------------- 命令
cmd_up() {
  check_docker
  local compose; compose="$(detect_compose)"
  prepare_env
  resolve_port
  info "开始构建镜像（首次约需 3-5 分钟）..."
  PORT="$PORT" $compose up -d --build
  wait_healthy
  echo
  printf '%s部署完成%s\n' "$BOLD" "$OFF"
  echo "  面板地址: http://$(local_ip):${PORT}"
  echo "  本机访问: http://127.0.0.1:${PORT}"
  echo "  默认账号: ${ADMIN_USERNAME:-admin} / ${ADMIN_PASSWORD:-admin123}（若未在 .env 中设置）"
  echo "  下一步:   打开面板 → Telegram 账号 → 填写 API 凭据完成登录"
}

cmd_update() {
  check_docker
  local compose; compose="$(detect_compose)"
  prepare_env
  resolve_port
  if [[ -d .git ]]; then
    info "拉取最新代码..."
    git pull --ff-only || warn "git pull 失败，使用本地代码继续"
  fi
  PORT="$PORT" $compose up -d --build
  wait_healthy
  info "更新完成 → http://$(local_ip):${PORT}"
}

cmd_stop()    { check_docker; $(detect_compose) down; info "已停止"; }
cmd_restart() { check_docker; $(detect_compose) restart; wait_healthy; info "已重启"; }
cmd_logs()    { check_docker; $(detect_compose) logs -f --tail=100; }
cmd_status()  { check_docker; $(detect_compose) ps; }

cmd_port() {
  prepare_env
  local current; current="$(env_get PORT || true)"
  if [[ -n "$PORT_ARG" ]]; then
    resolve_port
    info "端口已设置为 $PORT（写入 .env）"
    info "执行 ./scripts/deploy.sh update 使配置生效"
    return
  fi
  if [[ -n "$current" ]]; then
    info "当前端口：$current（.env）"
  else
    info "当前端口：未设置，将使用默认 $DEFAULT_PORT"
  fi
}

cmd_local() {
  if ! command -v python3 >/dev/null 2>&1; then
    error "未检测到 python3"; exit 1
  fi
  if ! command -v npm >/dev/null 2>&1; then
    error "未检测到 npm（构建前端需要，Node >= 18）"; exit 1
  fi

  prepare_env
  resolve_port

  info "构建前端..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)

  if [[ ! -d .venv ]]; then
    info "创建 Python 虚拟环境..."
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  info "安装后端依赖..."
  pip install -q -r backend/requirements.txt

  info "启动服务 → http://127.0.0.1:${PORT}"
  exec uvicorn backend.app.main:app --host "${HOST:-0.0.0.0}" --port "$PORT"
}

# --------------------------------------------------------------- 参数解析
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)
      [[ $# -ge 2 ]] || { error "--port 需要一个端口号"; exit 1; }
      PORT_ARG="$2"; shift 2 ;;
    --port=*)
      PORT_ARG="${1#*=}"; shift ;;
    -y|--yes)
      ASSUME_YES=1; shift ;;
    -h|--help|help)
      usage; exit 0 ;;
    up|start|deploy|update|upgrade|stop|down|restart|logs|status|ps|local|port)
      if [[ -n "$COMMAND" ]]; then error "只能指定一个命令（已有 $COMMAND，又出现 $1）"; exit 1; fi
      COMMAND="$1"; shift ;;
    *)
      error "未知参数: $1"
      usage
      exit 1 ;;
  esac
done

case "${COMMAND:-up}" in
  up|start|deploy) cmd_up ;;
  update|upgrade)  cmd_update ;;
  stop|down)       cmd_stop ;;
  restart)         cmd_restart ;;
  logs)            cmd_logs ;;
  status|ps)       cmd_status ;;
  port)            cmd_port ;;
  local)           cmd_local ;;
esac

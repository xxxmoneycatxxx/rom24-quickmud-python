#!/usr/bin/env bash
#
# QuickMUD Docker 管理脚本
#
# 用法: ./manage.sh <command>
#   build       构建 Docker 镜像
#   up          启动服务器 (后台运行)
#   down        停止服务器
#   restart     重启服务器
#   logs        查看日志 (最近100行)
#   status      查看容器状态
#   shell       进入容器 shell
#   test        运行测试套件
#   backup      备份数据库
#   update      更新并重启服务器
#   preflight   环境自检
#   help        显示此帮助信息
#

set -e

# ── 强制 UTF-8，防止中文乱码 ──────────────────────────────────────
export LANG=en_US.UTF-8 2>/dev/null || export LANG=C.UTF-8
export LC_ALL=en_US.UTF-8 2>/dev/null || export LC_ALL=C.UTF-8

# ── 配置 ──────────────────────────────────────────────────────────
BACKUP_DIR="./backups"
CONTAINER_NAME="quickmud-server"
SERVER_PORT=5001
COMPOSE_CMD=""

# 从 .env 读取端口（如果存在）
if [ -f ".env" ]; then
    _port=$(grep -E "^PORT=" .env 2>/dev/null | head -1 | cut -d= -f2 | tr -d '\r')
    [ -n "$_port" ] && SERVER_PORT="$_port"
fi

# ── 颜色输出 ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# ── 初始化 compose 命令 ──────────────────────────────────────────
init_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "docker compose 未安装"
        echo "  请安装 Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
}

# ── 自检自修 ──────────────────────────────────────────────────────
preflight() {
    log_info "===== 环境自检 ====="

    # 1. 检查 Docker
    log_info "检查 Docker..."
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker 未安装或不在 PATH 中"
        echo "  请安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker daemon 未运行"
        echo "  请启动 Docker 后重试"
        exit 1
    fi
    log_success "Docker 可用"

    # 2. 检查 Compose
    log_info "检查 Docker Compose..."
    init_compose
    log_success "Compose 可用 ($COMPOSE_CMD)"

    # 3. 检查必要文件
    log_info "检查必要文件..."
    for f in Dockerfile docker-compose.yml; do
        if [ ! -f "$f" ]; then
            log_error "缺少必要文件: $f"
            exit 1
        fi
    done
    if [ ! -f ".env" ]; then
        log_warn ".env 文件不存在，正在创建默认配置..."
        cat > .env << 'ENVEOF'
DATABASE_URL=sqlite:///mud.db
PORT=5001
HOST=0.0.0.0
LANGUAGE=zh
ENVEOF
        log_success "已创建 .env 文件（默认配置）"
    fi
    log_success "文件检查通过"

    # 4. 检查端口冲突
    log_info "检查端口 $SERVER_PORT..."
    if command -v ss >/dev/null 2>&1; then
        if ss -tlnp 2>/dev/null | grep -q ":${SERVER_PORT} "; then
            # 端口被占用——检查是否是我们的容器
            if docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" -q 2>/dev/null | grep -q .; then
                log_info "端口 $SERVER_PORT 已被容器占用（服务器正在运行）"
            else
                log_error "端口 $SERVER_PORT 被其他进程占用"
                echo "  请释放端口后重试，或修改 .env 中的 PORT"
                exit 1
            fi
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -i ":$SERVER_PORT" >/dev/null 2>&1; then
            if docker ps --filter "name=$CONTAINER_NAME" --filter "status=running" -q 2>/dev/null | grep -q .; then
                log_info "端口 $SERVER_PORT 已被容器占用（服务器正在运行）"
            else
                log_error "端口 $SERVER_PORT 被其他进程占用"
                exit 1
            fi
        fi
    fi
    log_success "端口可用"

    # 5. 清理残留容器
    _cleanup_stale

    # 6. 确保数据目录存在
    if [ ! -d "./data" ]; then
        mkdir -p "./data"
        log_info "已创建 data/ 目录"
    fi

    log_success "===== 自检全部通过 ====="
}

_cleanup_stale() {
    local state
    state=$(docker inspect "$CONTAINER_NAME" --format '{{.State.Status}}' 2>/dev/null || true)
    if [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
        log_warn "检测到残留容器（状态: $state），正在清理..."
        $COMPOSE_CMD down --remove-orphans >/dev/null 2>&1 || true
        log_success "残留容器已清理"
    fi
}

# 跨平台端口检测辅助函数
_port_open() {
    local port=$1
    if command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$port" 2>/dev/null && return 0
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$port)); s.close()" 2>/dev/null && return 0
    else
        # bash 内建 /dev/tcp（Linux 默认支持，macOS 默认不支持）
        (echo > /dev/tcp/127.0.0.1/$port) 2>/dev/null && return 0
    fi
    return 1
}

_wait_healthy() {
    local timeout=${1:-30}
    log_info "等待服务器就绪（超时 ${timeout}s）..."
    local elapsed=0
    while [ "$elapsed" -lt "$timeout" ]; do
        if _port_open "$SERVER_PORT"; then
            log_success "服务器已就绪（${elapsed}s）"
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    log_error "服务器在 ${timeout}s 内未就绪"
    log_info "正在检查容器状态..."
    docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
    log_info "最近 10 行日志："
    $COMPOSE_CMD logs --tail=10 2>/dev/null || true
    return 1
}

# ── 帮助 ──────────────────────────────────────────────────────────
show_help() {
    cat << 'EOF'

QuickMUD Docker 管理脚本

用法: ./manage.sh <command>

命令:
  build       构建 Docker 镜像
  up          启动服务器 (后台运行)
  down        停止服务器
  restart     重启服务器
  logs        查看日志 (最近100行, -f 实时跟踪)
  status      查看容器状态
  shell       进入容器 shell
  test        运行测试套件
  backup      备份数据库
  update      更新并重启服务器
  preflight   环境自检（不启动服务）
  help        显示此帮助信息

示例:
  ./manage.sh build          # 构建镜像
  ./manage.sh up             # 启动服务器
  ./manage.sh logs -f        # 实时查看日志
  ./manage.sh shell          # 进入容器
  ./manage.sh backup         # 备份数据库
  ./manage.sh preflight      # 环境自检

EOF
}

# ── 业务命令 ──────────────────────────────────────────────────────
cmd_status() {
    log_info "容器状态："
    $COMPOSE_CMD ps
}

cmd_build() {
    preflight
    log_info "构建 Docker 镜像..."
    $COMPOSE_CMD build --no-cache
    log_success "镜像构建成功"
}

cmd_up() {
    preflight
    log_info "启动 QuickMUD 服务器..."
    if $COMPOSE_CMD up -d; then
        log_success "服务器已启动"
        if _wait_healthy; then
            log_info "Telnet: localhost:$SERVER_PORT"
            log_info "查看日志: ./manage.sh logs"
        else
            log_warn "服务器可能未正常启动，请检查日志"
            log_info "修复建议: ./manage.sh restart"
        fi
    else
        log_error "启动失败，正在尝试清理后重试..."
        $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
        if $COMPOSE_CMD up -d; then
            log_success "重试成功"
            _wait_healthy
        else
            log_error "重试仍然失败，请检查 Docker 日志"
            $COMPOSE_CMD logs --tail=20
            exit 1
        fi
    fi
}

cmd_down() {
    log_info "停止 QuickMUD 服务器..."
    $COMPOSE_CMD down
    log_success "服务器已停止"
}

cmd_restart() {
    log_info "重启 QuickMUD 服务器..."
    $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
    $COMPOSE_CMD up -d
    log_success "服务器已重启"
    _wait_healthy
}

cmd_logs() {
    log_info "显示容器日志..."
    $COMPOSE_CMD logs --tail=100
}

cmd_logs_follow() {
    log_info "实时显示容器日志 (Ctrl+C 退出)..."
    $COMPOSE_CMD logs -f
}

cmd_shell() {
    log_info "进入容器 shell..."
    $COMPOSE_CMD exec mud /bin/bash
}

cmd_test() {
    log_info "运行测试..."
    $COMPOSE_CMD exec mud pytest -v
}

cmd_backup() {
    log_info "备份数据库..."
    mkdir -p "$BACKUP_DIR"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/mud_${timestamp}.db"
    if [ -f "./mud.db" ]; then
        cp ./mud.db "$backup_file"
        log_success "数据库已备份到: $backup_file"
    elif [ -f "./data/mud.db" ]; then
        cp ./data/mud.db "$backup_file"
        log_success "数据库已备份到: $backup_file"
    else
        log_error "未找到数据库文件（mud.db 或 data/mud.db）"
        exit 1
    fi
}

cmd_update() {
    log_info "更新服务器..."
    log_info "停止服务..."
    $COMPOSE_CMD down
    log_info "重新构建镜像..."
    if ! $COMPOSE_CMD build; then
        log_error "构建失败，正在清理缓存后重试..."
        docker system prune -f 2>/dev/null || true
        $COMPOSE_CMD build --no-cache || {
            log_error "重新构建仍然失败"
            exit 1
        }
    fi
    log_info "启动服务..."
    $COMPOSE_CMD up -d
    log_success "更新完成"
    _wait_healthy
}

# ── 初始化 ────────────────────────────────────────────────────────
init_compose

# ── 主逻辑 ────────────────────────────────────────────────────────
case "${1:-help}" in
    build)
        cmd_build
        ;;
    up|start)
        cmd_up
        ;;
    down|stop)
        cmd_down
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        if [ "$2" = "-f" ] || [ "$2" = "--follow" ]; then
            cmd_logs_follow
        else
            cmd_logs
        fi
        ;;
    status|ps)
        cmd_status
        ;;
    shell|bash)
        cmd_shell
        ;;
    test)
        cmd_test
        ;;
    backup)
        cmd_backup
        ;;
    update)
        cmd_update
        ;;
    preflight)
        preflight
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        log_error "未知命令: $1"
        show_help
        exit 1
        ;;
esac

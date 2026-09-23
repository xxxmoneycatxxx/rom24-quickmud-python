#!/usr/bin/env bash
#
# QuickMUD Docker 管理脚本
#
# 用法: ./manage.sh <command>
#
# 命令:
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
#   help        显示此帮助信息
#

set -e

# 配置
BACKUP_DIR="./backups"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    cat << 'EOF'

QuickMUD Docker 管理脚本

用法: ./manage.sh <command>

命令:
  build       构建 Docker 镜像
  up          启动服务器 (后台运行)
  down        停止服务器
  restart     重启服务器
  logs        查看日志 (最近100行)
  status      查看容器状态
  shell       进入容器 shell
  test        运行测试套件
  backup      备份数据库
  update      更新并重启服务器
  help        显示此帮助信息

示例:
  ./manage.sh build          # 构建镜像
  ./manage.sh up             # 启动服务器
  ./manage.sh logs           # 查看日志
  ./manage.sh shell          # 进入容器
  ./manage.sh backup         # 备份数据库

EOF
}

cmd_status() {
    log_info "检查容器状态..."
    docker-compose ps
}

cmd_build() {
    log_info "构建 Docker 镜像..."
    docker-compose build --no-cache
    log_success "镜像构建成功"
}

cmd_up() {
    log_info "启动 QuickMUD 服务器..."
    docker-compose up -d
    log_success "服务器已启动"
    log_info "Telnet: localhost:5001"
    log_info "查看日志: ./manage.sh logs"
}

cmd_down() {
    log_info "停止 QuickMUD 服务器..."
    docker-compose down
    log_success "服务器已停止"
}

cmd_restart() {
    log_info "重启 QuickMUD 服务器..."
    docker-compose restart
    log_success "服务器已重启"
}

cmd_logs() {
    log_info "显示容器日志..."
    docker-compose logs --tail=100
}

cmd_logs_follow() {
    log_info "实时显示容器日志 (Ctrl+C 退出)..."
    docker-compose logs -f
}

cmd_shell() {
    log_info "进入容器 shell..."
    docker-compose exec mud /bin/bash
}

cmd_test() {
    log_info "运行测试..."
    docker-compose exec mud pytest -v
}

cmd_backup() {
    log_info "备份数据库..."
    
    # 创建备份目录
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/mud_${timestamp}.db"
    
    # 复制数据库文件
    if [ -f "./mud.db" ]; then
        cp ./mud.db "$backup_file"
        log_success "数据库已备份到: $backup_file"
    else
        log_error "未找到数据库文件 ./mud.db"
        exit 1
    fi
}

cmd_update() {
    log_info "更新服务器..."
    
    # 停止服务
    log_info "停止服务..."
    docker-compose down
    
    # 重新构建
    log_info "重新构建镜像..."
    docker-compose build
    
    # 启动服务
    log_info "启动服务..."
    docker-compose up -d
    
    log_success "更新完成"
}

# 主逻辑
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
    help|-h|--help)
        show_help
        ;;
    *)
        log_error "未知命令: $1"
        show_help
        exit 1
        ;;
esac

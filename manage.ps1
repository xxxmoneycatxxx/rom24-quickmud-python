#!/usr/bin/env pwsh
# QuickMUD Docker 管理脚本
#
# 用法: .\manage.ps1 <command>
#   build       构建 Docker 镜像
#   up          启动服务器
#   down        停止服务器
#   restart     重启服务器
#   logs        查看日志
#   status      查看状态
#   shell       进入容器 shell
#   test        运行测试
#   backup      备份数据库
#   update      更新并重启
#   preflight   环境自检

# ── 强制 UTF-8，防止中文乱码 ──────────────────────────────────────
# NOTE: param() 必须在脚本最前面，编码设置放在其后

param(
    [Parameter(Position=0)]
    [ValidateSet("build", "up", "down", "restart", "logs", "status", "shell", "test", "backup", "update", "preflight", "ps", "help")]
    [string]$Command = "help",

    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

# 强制 UTF-8 输出（必须在 param() 之后）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch { $null }

$ErrorActionPreference = "Stop"

# ── 配置 ──────────────────────────────────────────────────────────
$ContainerName = "quickmud-server"
$ProjectName   = "quickmud"
$BackupDir     = "./backups"
$ServerPort    = 5001

# 从 .env 读取端口（如果存在）
if (Test-Path ".env") {
    foreach ($line in (Get-Content ".env")) {
        if ($line -match "^PORT=(\d+)$") {
            $ServerPort = [int]$Matches[1]
            break
        }
    }
}

# ── 日志函数 ──────────────────────────────────────────────────────
function Write-Info    { param([string]$m); Write-Host "[INFO] $m"    -ForegroundColor Cyan }
function Write-Success { param([string]$m); Write-Host "[OK] $m"      -ForegroundColor Green }
function Write-Warn    { param([string]$m); Write-Host "[WARN] $m"    -ForegroundColor Yellow }
function Write-Err     { param([string]$m); Write-Host "[ERROR] $m"   -ForegroundColor Red }

# ── 自检自修 ──────────────────────────────────────────────────────
function _check_docker {
    $dockerOk = $false
    try {
        $null = docker version 2>&1
        if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
    } catch { $null }
    if (-not $dockerOk) {
        Write-Err "Docker 未安装或不在 PATH 中"
        Write-Host "  请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
        exit 1
    }
    $daemonOk = $false
    try {
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) { $daemonOk = $true }
    } catch { $null }
    if (-not $daemonOk) {
        Write-Err "Docker daemon 未运行，正在尝试启动..."
        Start-Process "docker" -ArgumentList "info" -WindowStyle Hidden -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
        try {
            $null = docker info 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Docker daemon 已启动"
                return
            }
        } catch { $null }
        Write-Err "无法启动 Docker daemon，请手动启动 Docker Desktop"
        exit 1
    }
}

function _check_compose {
    # 检测 docker compose (V2 插件)
    $v2Ok = $false
    try {
        $null = docker compose version 2>&1
        if ($LASTEXITCODE -eq 0) { $v2Ok = $true }
    } catch { $null }
    if ($v2Ok) { return }

    # 回退到 docker-compose (V1 独立二进制)
    $v1Ok = $false
    try {
        $null = docker-compose version 2>&1
        if ($LASTEXITCODE -eq 0) { $v1Ok = $true }
    } catch { $null }
    if ($v1Ok) {
        $script:UseV1 = $true
        return
    }

    Write-Err "docker compose 未安装"
    Write-Host "  请安装 Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
}

# 统一 compose 调用入口（解决 PowerShell & 操作符对数组参数的解析问题）
# docker compose 将进度信息写入 stderr，PowerShell 的 $ErrorActionPreference=Stop
# 会将 stderr 输出视为异常（NativeCommandError），因此需要临时降级处理。
function dc {
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($script:UseV1) {
            & docker-compose @args
        } else {
            & docker compose @args
        }
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function _check_files {
    $required = @("Dockerfile", "docker-compose.yml")
    foreach ($f in $required) {
        if (-not (Test-Path $f)) {
            Write-Err "缺少必要文件: $f"
            exit 1
        }
    }
    if (-not (Test-Path ".env")) {
        Write-Warn ".env 文件不存在，正在创建默认配置..."
        $envContent = @(
            "DATABASE_URL=sqlite:///mud.db",
            "PORT=5001",
            "HOST=0.0.0.0",
            "LANGUAGE=zh"
        ) -join "`n"
        [System.IO.File]::WriteAllText(
            (Resolve-Path ".").Path + "/.env",
            $envContent,
            [System.Text.Encoding]::UTF8
        )
        Write-Success "已创建 .env 文件（默认配置）"
    }
}

function _check_port {
    $portInUse = $false
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("127.0.0.1", $ServerPort)
        $tcp.Close()
        $portInUse = $true
    } catch { $null }
    if ($portInUse) {
        $running = $null
        try {
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $running = docker ps --filter "name=$ContainerName" --filter "status=running" -q 2>&1
            $ErrorActionPreference = $prevEAP
        } catch {
            $ErrorActionPreference = $prevEAP
        }
        if ($running) {
            Write-Info "端口 $ServerPort 已被容器 $ContainerName 占用（服务器正在运行）"
        } else {
            Write-Warn "端口 $ServerPort 被非本容器的进程占用"
            Write-Host "  请释放端口后重试，或修改 .env 中的 PORT"
            exit 1
        }
    }
}

function _cleanup_stale {
    $state = $null
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $state = docker inspect $ContainerName --format "{{.State.Status}}" 2>$null
        $ErrorActionPreference = $prevEAP
    } catch {
        $ErrorActionPreference = $prevEAP
    }
    if (-not $state) { return }  # 容器不存在，无需清理
    if ($state -eq "exited" -or $state -eq "running" -or $state -eq "dead") {
        Write-Warn "检测到残留容器（状态: $state），正在清理..."
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { docker rm -f $ContainerName 2>$null } catch { $null }
        $ErrorActionPreference = $prevEAP
        Write-Success "残留容器已清理"
    }
}

function _wait_healthy {
    param([int]$Timeout = 30)
    Write-Info "等待服务器就绪（超时 ${Timeout}s）..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $Timeout) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $ServerPort)
            $tcp.Close()
            Write-Success "服务器已就绪（$([math]::Round($sw.Elapsed.TotalSeconds, 1))s）"
            return $true
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Err "服务器在 ${Timeout}s 内未就绪"
    Write-Info "正在检查容器状态..."
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        docker ps --filter "name=$ContainerName" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1
        $ErrorActionPreference = $prevEAP
    } catch {
        $ErrorActionPreference = $prevEAP
    }
    Write-Info "最近 10 行日志："
    dc logs --tail=10
    return $false
}

function _preflight {
    Write-Info "===== 环境自检 ====="
    Write-Info "检查 Docker..."
    _check_docker
    Write-Success "Docker 可用"

    Write-Info "检查 Docker Compose..."
    _check_compose
    if ($script:UseV1) {
        Write-Success "Compose 可用 (docker-compose V1)"
    } else {
        Write-Success "Compose 可用 (docker compose V2)"
    }

    Write-Info "检查必要文件..."
    _check_files
    Write-Success "文件检查通过"

    Write-Info "检查端口 $ServerPort..."
    _check_port
    Write-Success "端口可用"

    _cleanup_stale

    if (-not (Test-Path "./data")) {
        New-Item -ItemType Directory -Path "./data" | Out-Null
        Write-Info "已创建 data/ 目录"
    }

    Write-Success "===== 自检全部通过 ====="
}

# ── 业务命令 ──────────────────────────────────────────────────────
function Show-Status {
    Write-Info "容器状态："
    dc ps
}

function Build-Image {
    _preflight
    Write-Info "构建 Docker 镜像..."
    dc build --no-cache
    if ($LASTEXITCODE -eq 0) {
        Write-Success "镜像构建成功"
    } else {
        Write-Err "镜像构建失败"
        exit 1
    }
}

function Start-Server {
    _preflight
    Write-Info "启动 QuickMUD 服务器..."
    dc up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务器已启动"
        if (_wait_healthy) {
            Write-Info "Telnet: localhost:$ServerPort"
            Write-Info "查看日志: .\manage.ps1 logs"
        } else {
            Write-Warn "服务器可能未正常启动，请检查日志"
            Write-Info "修复建议: .\manage.ps1 restart"
        }
    } else {
        Write-Err "启动失败，正在尝试清理后重试..."
        dc down --remove-orphans 2>$null
        dc up -d
        if ($LASTEXITCODE -eq 0) {
            Write-Success "重试成功"
            $null = _wait_healthy
        } else {
            Write-Err "重试仍然失败，请检查 Docker 日志"
            dc logs --tail=20
            exit 1
        }
    }
}

function Stop-Server {
    Write-Info "停止 QuickMUD 服务器..."
    dc down
    Write-Success "服务器已停止"
}

function Restart-Server {
    Write-Info "重启 QuickMUD 服务器..."
    dc down --remove-orphans 2>$null
    dc up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务器已重启"
        $null = _wait_healthy
    } else {
        Write-Err "重启失败"
        exit 1
    }
}

function Show-Logs {
    Write-Info "显示容器日志..."
    dc logs --tail=100
}

function Enter-Shell {
    Write-Info "进入容器 shell..."
    dc exec mud /bin/bash
}

function Run-Tests {
    Write-Info "运行测试..."
    dc exec mud pytest -v
}

function Backup-Database {
    Write-Info "备份数据库..."
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    $timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = "$BackupDir/mud_${timestamp}.db"
    if (Test-Path "./mud.db") {
        Copy-Item "./mud.db" $backupFile
        Write-Success "数据库已备份到: $backupFile"
    } elseif (Test-Path "./data/mud.db") {
        Copy-Item "./data/mud.db" $backupFile
        Write-Success "数据库已备份到: $backupFile"
    } else {
        Write-Err "未找到数据库文件（mud.db 或 data/mud.db）"
        exit 1
    }
}

function Update-Server {
    Write-Info "更新服务器..."
    Write-Info "停止服务..."
    dc down
    Write-Info "重新构建镜像..."
    dc build
    if ($LASTEXITCODE -ne 0) {
        Write-Err "构建失败，正在清理缓存..."
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { $null = docker system prune -f 2>&1 } catch { $null }
        $ErrorActionPreference = $prevEAP
        dc build --no-cache
        if ($LASTEXITCODE -ne 0) {
            Write-Err "重新构建仍然失败"
            exit 1
        }
    }
    Write-Info "启动服务..."
    dc up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "更新完成"
        $null = _wait_healthy
    } else {
        Write-Err "启动失败"
        exit 1
    }
}

function Show-Help {
    Write-Host @"

QuickMUD Docker 管理脚本

用法: .\manage.ps1 <command>

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
  preflight   环境自检（不启动服务）
  help        显示此帮助信息

示例:
  .\manage.ps1 build          # 构建镜像
  .\manage.ps1 up             # 启动服务器
  .\manage.ps1 logs           # 查看日志
  .\manage.ps1 shell          # 进入容器
  .\manage.ps1 backup         # 备份数据库

"@
}

# ── 初始化 ────────────────────────────────────────────────────────
$script:UseV1 = $false

# ── 主逻辑 ───────────────────────────────────────────────────────
switch ($Command) {
    "build"     { Build-Image }
    "up"        { Start-Server }
    "down"      { Stop-Server }
    "restart"   { Restart-Server }
    "logs"      { Show-Logs }
    "status"    { Show-Status }
    "ps"        { Show-Status }
    "shell"     { Enter-Shell }
    "test"      { Run-Tests }
    "backup"    { Backup-Database }
    "update"    { Update-Server }
    "preflight" { _preflight }
    "help"      { Show-Help }
    default     { Show-Help }
}

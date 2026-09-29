#!/usr/bin/env pwsh
# QuickMUD Docker 管理脚本（增强版）
#
# 用法: .\manage.ps1 <command> [options]
#   build       构建 Docker 镜像
#   up          启动服务器
#   down        停止服务器
#   restart     重启服务器
#   logs        查看日志（支持 -f 实时跟踪）
#   status      查看状态（含健康检查）
#   shell       进入容器 shell
#   test        运行测试
#   backup      备份数据库（含自动轮转）
#   update      自动备份 → 更新 → 重启
#   prune       清理无用 Docker 资源
#   preflight   环境自检
#   version     显示版本信息
#   help        显示帮助
#
# 全局选项:
#   -NoColor    禁用彩色输出（CI / 日志采集友好）
#   -Force      跳过确认提示

param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "build", "up", "start", "down", "stop", "restart",
        "logs", "status", "ps", "shell", "bash",
        "test", "backup", "update", "prune",
        "preflight", "version", "help"
    )]
    [string]$Command = "help",

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Args,

    [switch]$NoColor,
    [switch]$Force
)

# ── 强制 UTF-8，防止中文乱码 ──────────────────────────────────────
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch { $null }

$ErrorActionPreference = "Stop"

# ── 颜色开关 ──────────────────────────────────────────────────────
if ($NoColor) {
    function Write-Info     { param([string]$m); Write-Host "[INFO] $m" }
    function Write-Success  { param([string]$m); Write-Host "[OK] $m" }
    function Write-Warn     { param([string]$m); Write-Host "[WARN] $m" }
    function Write-Err      { param([string]$m); Write-Host "[ERROR] $m" }
} else {
    function Write-Info     { param([string]$m); Write-Host "[INFO] $m"    -ForegroundColor Cyan }
    function Write-Success  { param([string]$m); Write-Host "[OK] $m"      -ForegroundColor Green }
    function Write-Warn     { param([string]$m); Write-Host "[WARN] $m"    -ForegroundColor Yellow }
    function Write-Err      { param([string]$m); Write-Host "[ERROR] $m"   -ForegroundColor Red }
}

# ── 配置 ──────────────────────────────────────────────────────────
$ContainerName = "quickmud-server"
$ProjectName   = "quickmud"
$BackupDir     = "./backups"
$ServerPort    = 5100
$WsPort        = 8000
$MaxBackups    = 10   # 备份轮转保留数量

# ── 别名规范化 ────────────────────────────────────────────────────
switch ($Command) {
    "start" { $Command = "up" }
    "stop"  { $Command = "down" }
    "bash"  { $Command = "shell" }
}

# ── 从 .env 读取端口（容错解析） ─────────────────────────────────
function _load_env_port {
    if (-not (Test-Path ".env")) { return }
    try {
        foreach ($raw in (Get-Content ".env" -ErrorAction SilentlyContinue)) {
            $line = $raw.Trim()
            # 跳过空行和注释
            if ([string]::IsNullOrEmpty($line) -or $line.StartsWith("#")) { continue }
            if ($line -match '^\s*PORT\s*=\s*"?(\d+)"?\s*$') {
                $script:ServerPort = [int]$Matches[1]
            }
            if ($line -match '^\s*WS_PORT\s*=\s*"?(\d+)"?\s*$') {
                $script:WsPort = [int]$Matches[1]
            }
        }
    } catch {
        Write-Warn ".env 解析失败，使用默认端口 (telnet=$ServerPort, ws=$WsPort)"
    }
}
_load_env_port

# ── 自检自修 ──────────────────────────────────────────────────────

function _check_docker {
    # docker version/info 会向 stderr 输出警告（如 cgroup 废弃提示），
    # $ErrorActionPreference=Stop 会将其视为异常，因此必须临时降级。
    $dockerOk = $false
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = docker version 2>&1
        if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
    } catch { $null }
    $ErrorActionPreference = $prevEAP
    if (-not $dockerOk) {
        Write-Err "Docker 未安装或不在 PATH 中"
        Write-Host "  请安装 Docker Desktop: https://www.docker.com/products/docker-desktop/"
        exit 1
    }
    $daemonOk = $false
    $ErrorActionPreference = "Continue"
    try {
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) { $daemonOk = $true }
    } catch { $null }
    $ErrorActionPreference = $prevEAP
    if (-not $daemonOk) {
        Write-Err "Docker daemon 未运行，正在尝试启动..."
        # 尝试常见启动路径
        $started = $false
        foreach ($proc in @("Docker Desktop", "com.docker.backend")) {
            try {
                Start-Process $proc -ErrorAction Stop 2>$null
                $started = $true
                break
            } catch { $null }
        }
        if (-not $started) {
            # 回退：尝试直接启动 docker info 触发守护进程
            Start-Process "docker" -ArgumentList "info" -WindowStyle Hidden -ErrorAction SilentlyContinue
        }
        # 轮询等待 daemon 就绪（最多 20s）
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $ErrorActionPreference = "Continue"
        while ($sw.Elapsed.TotalSeconds -lt 20) {
            try {
                $null = docker info 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $ErrorActionPreference = $prevEAP
                    Write-Success "Docker daemon 已启动（$([math]::Round($sw.Elapsed.TotalSeconds, 1))s）"
                    return
                }
            } catch { $null }
            Start-Sleep -Seconds 1
        }
        $ErrorActionPreference = $prevEAP
        Write-Err "无法启动 Docker daemon（等待 20s 超时），请手动启动 Docker Desktop"
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

# 统一 compose 调用入口
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
        # 不 return $LASTEXITCODE——避免退出码混入输出流
        # 调用方通过 $LASTEXITCODE 检查成败
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function _check_files {
    $required = @("Dockerfile", "docker-compose.yml")
    foreach ($f in $required) {
        if (-not (Test-Path $f)) {
            Write-Err "缺少必要文件: $f"
            Write-Host "  请确认在 QuickMUD 项目根目录下运行此脚本"
            exit 1
        }
    }
    if (-not (Test-Path ".env")) {
        Write-Warn ".env 文件不存在，正在创建默认配置..."
        $envContent = @(
            "DATABASE_URL=sqlite:///mud.db",
            "PORT=5100",
            "WS_PORT=8000",
            "HOST=0.0.0.0",
            "LANGUAGE=zh"
        ) -join "`n"
        [System.IO.File]::WriteAllText(
            (Join-Path (Get-Location).Path ".env"),
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
        $state = (docker inspect $ContainerName --format "{{.State.Status}}" 2>$null)
        $ErrorActionPreference = $prevEAP
    } catch {
        $ErrorActionPreference = $prevEAP
    }
    if (-not $state) { return }  # 容器不存在，无需清理
    # 仅清理非运行状态的残留容器（exited / dead），不碰 running 的容器
    if ($state -eq "exited" -or $state -eq "dead") {
        Write-Warn "检测到残留容器（状态: $state），正在清理..."
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { $null = docker rm -f $ContainerName 2>$null } catch { $null }
        $ErrorActionPreference = $prevEAP
        Write-Success "残留容器已清理"
    }
}

function _wait_healthy {
    param([int]$Timeout = 30)
    Write-Info "等待服务器就绪（超时 ${Timeout}s）..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $Timeout) {
        # 优先检查 Docker 健康检查状态
        $health = $null
        try {
            $prevEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $health = (docker inspect $ContainerName --format "{{.State.Health.Status}}" 2>$null)
            $ErrorActionPreference = $prevEAP
        } catch {
            $ErrorActionPreference = $prevEAP
        }
        if ($health -eq "healthy") {
            Write-Success "服务器已就绪（$([math]::Round($sw.Elapsed.TotalSeconds, 1))s）[healthcheck: healthy]"
            return $true
        }
        # 回退：直接探测端口
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

# ── 备份与轮转 ────────────────────────────────────────────────────

function _rotate_backups {
    if (-not (Test-Path $BackupDir)) { return }
    $old = Get-ChildItem -Path $BackupDir -Filter "mud_*.db" -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending |
           Select-Object -Skip $MaxBackups
    if ($old) {
        $old | Remove-Item -Force
        Write-Info "已轮转 $($old.Count) 个旧备份（保留最近 $MaxBackups 个）"
    }
}

function _auto_backup {
    Write-Info "更新前自动备份..."
    try {
        _do_backup | Out-Null
        Write-Success "自动备份完成"
    } catch {
        Write-Warn "自动备份失败: $_"
        if (-not $Force) {
            $confirm = Read-Host "是否继续更新？(y/N)"
            if ($confirm -notin @("y", "Y", "yes")) {
                Write-Err "已取消更新"
                exit 1
            }
        }
    }
}

function _do_backup {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    $timestamp  = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $BackupDir "mud_${timestamp}.db"
    if (Test-Path "./mud.db") {
        Copy-Item "./mud.db" $backupFile
        Write-Success "数据库已备份到: $backupFile"
    } elseif (Test-Path "./data/mud.db") {
        Copy-Item "./data/mud.db" $backupFile
        Write-Success "数据库已备份到: $backupFile"
    } else {
        Write-Warn "未找到数据库文件（mud.db 或 data/mud.db），跳过备份"
        return $null
    }
    _rotate_backups
    return $backupFile
}

# ── 业务命令 ──────────────────────────────────────────────────────

function Show-Status {
    Write-Info "容器状态："
    dc ps
    # 额外显示健康检查信息
    $health = $null
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $health = (docker inspect $ContainerName --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}no healthcheck{{end}}" 2>$null)
        $ErrorActionPreference = $prevEAP
    } catch {
        $ErrorActionPreference = $prevEAP
    }
    if ($health) {
        Write-Info "健康检查: $health"
    }
}

function Build-Image {
    _preflight
    Write-Info "构建 Docker 镜像..."
    dc build --no-cache
    if ($LASTEXITCODE -eq 0) {
        Write-Success "镜像构建成功"
    } else {
        Write-Err "镜像构建失败（exit code: $LASTEXITCODE）"
        exit $LASTEXITCODE
    }
}

function Start-Server {
    _preflight
    Write-Info "启动 QuickMUD 服务器（自动构建）..."
    dc up --build -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务器已启动"
        if (_wait_healthy) {
            Write-Info "Telnet:      localhost:$ServerPort"
            Write-Info "Web 客户端:  http://localhost:$WsPort"
            Write-Info "查看日志:    .\manage.ps1 logs"
        } else {
            Write-Warn "服务器可能未正常启动，请检查日志"
            Write-Info "修复建议: .\manage.ps1 restart"
        }
    } else {
        Write-Err "启动失败（exit code: $LASTEXITCODE），正在尝试清理后重试..."
        dc down --remove-orphans 2>$null
        dc up --build -d
        if ($LASTEXITCODE -eq 0) {
            Write-Success "重试成功"
            $null = _wait_healthy
        } else {
            Write-Err "重试仍然失败（exit code: $LASTEXITCODE），请检查 Docker 日志"
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
    dc up --build -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务器已重启"
        $null = _wait_healthy
    } else {
        Write-Err "重启失败（exit code: $LASTEXITCODE）"
        exit 1
    }
}

function Show-Logs {
    $follow = ($Args -contains "-f") -or ($Args -contains "--follow")
    if ($follow) {
        Write-Info "实时显示容器日志 (Ctrl+C 退出)..."
        dc logs -f
    } else {
        Write-Info "显示容器日志（最近 100 行）..."
        dc logs --tail=100
    }
}

function Enter-Shell {
    Write-Info "进入容器 shell..."
    dc exec mud /bin/bash
}

function Run-Tests {
    Write-Info "运行测试..."
    # 支持透传额外参数: .\manage.ps1 test -- -v -k foo
    $passthrough = @()
    if ($Args) {
        $passthrough = $Args | Where-Object { $_ -ne "--" }
    }
    if ($passthrough.Count -gt 0) {
        dc exec mud pytest @passthrough
    } else {
        dc exec mud pytest -v
    }
}

function Backup-Database {
    Write-Info "备份数据库..."
    $result = _do_backup
    if ($result) {
        Write-Success "备份完成: $result"
    } else {
        Write-Err "未找到数据库文件，无法备份"
        exit 1
    }
}

function Update-Server {
    # 更新前自动备份
    _auto_backup

    Write-Info "停止服务..."
    dc down
    Write-Info "重新构建镜像..."
    dc build
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "构建失败，正在清理缓存后重试..."
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { $null = docker system prune -f 2>&1 } catch { $null }
        $ErrorActionPreference = $prevEAP
        dc build --no-cache
        if ($LASTEXITCODE -ne 0) {
            Write-Err "重新构建仍然失败（exit code: $LASTEXITCODE）"
            exit 1
        }
    }
    Write-Info "启动服务..."
    dc up --build -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "更新完成"
        $null = _wait_healthy
    } else {
        Write-Err "启动失败（exit code: $LASTEXITCODE）"
        exit 1
    }
}

function Invoke-Prune {
    Write-Info "清理无用 Docker 资源..."
    if (-not $Force) {
        $confirm = Read-Host "将清理所有悬空镜像、停止的容器和未使用的网络，继续？(y/N)"
        if ($confirm -notin @("y", "Y", "yes")) {
            Write-Info "已取消"
            return
        }
    }
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        docker system prune -f
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Docker 资源清理完成"
        } else {
            Write-Warn "清理过程中出现警告"
        }
    } catch {
        Write-Warn "清理出现异常: $_"
    } finally {
        $ErrorActionPreference = $prevEAP
    }
}

function Show-Version {
    Write-Info "QuickMUD manage.ps1 v2.0"
    Write-Info "PowerShell: $($PSVersionTable.PSVersion)"
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $dv = (docker version --format "{{.Server.Version}}" 2>$null)
        if ($dv) { Write-Info "Docker Engine: $dv" }
        $cv = (docker compose version --short 2>$null)
        if ($cv) { Write-Info "Docker Compose: $cv" }
        $ErrorActionPreference = $prevEAP
    } catch {
        $ErrorActionPreference = $prevEAP
    }
}

function Show-Help {
    Write-Host @"

QuickMUD Docker 管理脚本 (v2.1)

用法: .\manage.ps1 <command> [options]

命令:
  build       构建 Docker 镜像
  up          启动服务器 (自动构建 + 后台运行)
  down        停止服务器
  restart     重启服务器
  logs        查看日志 (最近100行)
  logs -f     实时跟踪日志 (Ctrl+C 退出)
  status      查看容器状态 (含健康检查)
  shell       进入容器 shell
  test        运行测试套件
  test -- X   透传参数给 pytest
  backup      备份数据库 (自动轮转保留最近10个)
  update      自动备份 → 更新 → 重启
  prune       清理无用 Docker 资源
  preflight   环境自检（不启动服务）
  version     显示版本信息
  help        显示此帮助信息

全局选项:
  -NoColor    禁用彩色输出
  -Force      跳过确认提示

别名:
  start = up, stop = down, bash = shell

端口配置 (.env) — 单容器双协议:
  PORT        Telnet 端口 (默认 5100)
  WS_PORT     WebSocket 端口 (默认 8000)

示例:
  .\manage.ps1 up               # 启动服务器
  .\manage.ps1 logs -f          # 实时查看日志
  .\manage.ps1 backup           # 备份数据库
  .\manage.ps1 update           # 自动备份并更新
  .\manage.ps1 test -- -k login # 运行指定测试
  .\manage.ps1 -NoColor status  # 无彩色输出

连接方式:
  Telnet:       telnet localhost:<PORT>
  Web 客户端:   http://localhost:<WS_PORT>
  SSH:          ssh -p 2222 player@localhost

"@
}

# ── 初始化 ────────────────────────────────────────────────────────
$script:UseV1 = $false

# ── Ctrl+C 优雅处理 ──────────────────────────────────────────────
$null = Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    # 脚本退出时无需特殊清理（Docker 容器独立运行）
} -ErrorAction SilentlyContinue

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
    "prune"     { Invoke-Prune }
    "preflight" { _preflight }
    "version"   { Show-Version }
    "help"      { Show-Help }
    default     { Show-Help }
}

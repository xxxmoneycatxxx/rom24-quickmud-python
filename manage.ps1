#!/usr/bin/env pwsh
<#
.SYNOPSIS
    QuickMUD Docker 管理脚本

.DESCRIPTION
    提供 Docker 容器化部署的便捷管理命令

.EXAMPLE
    .\manage.ps1 build      # 构建镜像
    .\manage.ps1 up         # 启动服务器
    .\manage.ps1 down       # 停止服务器
    .\manage.ps1 restart    # 重启服务器
    .\manage.ps1 logs       # 查看日志
    .\manage.ps1 status     # 查看状态
    .\manage.ps1 shell      # 进入容器 shell
    .\manage.ps1 test       # 运行测试
    .\manage.ps1 backup     # 备份数据库
    .\manage.ps1 update     # 更新并重启
#>

param(
    [Parameter(Position=0)]
    [ValidateSet("build", "up", "down", "restart", "logs", "status", "shell", "test", "backup", "update", "ps", "help")]
    [string]$Command = "help",
    
    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"

# 配置
$ContainerName = "quickmud-server"
$ProjectName = "quickmud"
$BackupDir = "./backups"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Show-Status {
    Write-Info "检查容器状态..."
    docker-compose ps
}

function Build-Image {
    Write-Info "构建 Docker 镜像..."
    docker-compose build --no-cache
    if ($LASTEXITCODE -eq 0) {
        Write-Success "镜像构建成功"
    } else {
        Write-Error "镜像构建失败"
        exit 1
    }
}

function Start-Server {
    Write-Info "启动 QuickMUD 服务器..."
    docker-compose up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Success "服务器已启动"
        Write-Info "Telnet: localhost:5001"
        Write-Info "查看日志: .\manage.ps1 logs"
    } else {
        Write-Error "启动失败"
        exit 1
    }
}

function Stop-Server {
    Write-Info "停止 QuickMUD 服务器..."
    docker-compose down
    Write-Success "服务器已停止"
}

function Restart-Server {
    Write-Info "重启 QuickMUD 服务器..."
    docker-compose restart
    Write-Success "服务器已重启"
}

function Show-Logs {
    param([switch]$Follow)
    Write-Info "显示容器日志..."
    if ($Follow) {
        docker-compose logs -f
    } else {
        docker-compose logs --tail=100
    }
}

function Enter-Shell {
    Write-Info "进入容器 shell..."
    docker-compose exec mud /bin/bash
}

function Run-Tests {
    Write-Info "运行测试..."
    docker-compose exec mud pytest -v
}

function Backup-Database {
    Write-Info "备份数据库..."
    
    # 创建备份目录
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = "$BackupDir/mud_${timestamp}.db"
    
    # 复制数据库文件
    if (Test-Path "./mud.db") {
        Copy-Item "./mud.db" $backupFile
        Write-Success "数据库已备份到: $backupFile"
    } else {
        Write-Error "未找到数据库文件 ./mud.db"
        exit 1
    }
}

function Update-Server {
    Write-Info "更新服务器..."
    
    # 停止服务
    Write-Info "停止服务..."
    docker-compose down
    
    # 重新构建
    Write-Info "重新构建镜像..."
    docker-compose build
    
    # 启动服务
    Write-Info "启动服务..."
    docker-compose up -d
    
    Write-Success "更新完成"
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
  help        显示此帮助信息

示例:
  .\manage.ps1 build          # 构建镜像
  .\manage.ps1 up             # 启动服务器
  .\manage.ps1 logs           # 查看日志
  .\manage.ps1 shell          # 进入容器
  .\manage.ps1 backup         # 备份数据库

"@
}

# 主逻辑
switch ($Command) {
    "build"   { Build-Image }
    "up"      { Start-Server }
    "down"    { Stop-Server }
    "restart" { Restart-Server }
    "logs"    { Show-Logs }
    "status"  { Show-Status }
    "ps"      { Show-Status }
    "shell"   { Enter-Shell }
    "test"    { Run-Tests }
    "backup"  { Backup-Database }
    "update"  { Update-Server }
    "help"    { Show-Help }
    default   { Show-Help }
}

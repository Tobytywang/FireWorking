# 开机自启开关。
#
#   开启：  powershell -ExecutionPolicy Bypass -File autostart.ps1
#   关闭：  powershell -ExecutionPolicy Bypass -File autostart.ps1 -Remove
#
# 刻意走"启动文件夹快捷方式"而不是注册表 Run 键：出问题时在
# shell:startup 里肉眼就能看到、直接删掉，不用去翻注册表。

param([switch]$Remove)

$proj = $PSScriptRoot
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup '键盘热度.lnk'

if ($Remove) {
    if (Test-Path $lnk) {
        Remove-Item $lnk -Force
        Write-Host "已移除开机自启：$lnk"
    } else {
        Write-Host "本来就没设置开机自启。"
    }
    exit 0
}

$pythonw = Join-Path $proj 'venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Host "[x] 找不到 $pythonw"
    Write-Host "    请先运行 setup.bat 安装环境。"
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $pythonw
$sc.Arguments = '"' + (Join-Path $proj 'main.py') + '"'
$sc.WorkingDirectory = $proj
$sc.WindowStyle = 7
$sc.Description = '键盘热度显示器'
$sc.Save()

Write-Host "已设置开机自启：$lnk"
Write-Host "想取消就运行：powershell -ExecutionPolicy Bypass -File autostart.ps1 -Remove"

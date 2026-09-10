# VOICEVOX を起動し、ウィンドウが出たら最小化する。
# Electron はショートカットの「最小化」指定を無視するので、出てきた窓を後から畳む。
$ErrorActionPreference = 'Stop'

$exe = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\HiroshibaKazuyuki.VOICEVOX.CPU_Microsoft.Winget.Source_8wekyb3d8bbwe\VOICEVOX\VOICEVOX.exe'
if (-not (Test-Path $exe)) { exit 1 }

if (-not (Get-Process -Name VOICEVOX -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe)
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public class Win32Min {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
'@

$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $wins = Get-Process -Name VOICEVOX -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 }
    if ($wins) {
        # 描画が落ち着くまで少し待ってから畳む(早すぎると出し直される)
        Start-Sleep -Seconds 3
        foreach ($w in (Get-Process -Name VOICEVOX | Where-Object { $_.MainWindowHandle -ne 0 })) {
            [Win32Min]::ShowWindow($w.MainWindowHandle, 6) | Out-Null   # SW_MINIMIZE
        }
        break
    }
}

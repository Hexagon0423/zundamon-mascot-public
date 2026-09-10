' PowerShell スクリプトをコンソール窓なしで起動するだけのラッパー。
Set sh = CreateObject("WScript.Shell")
ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ _
   & Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\")) _
   & "start_voicevox_minimized.ps1"""
sh.Run ps, 0, False

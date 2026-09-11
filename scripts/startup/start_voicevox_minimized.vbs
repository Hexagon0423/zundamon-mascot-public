' Launch the PowerShell script with no console window.
' Keep this file ASCII-only. WSH reads .vbs in the ANSI code page (CP932 here),
' and a UTF-8 Japanese comment ending in a full stop swallowed the newline after
' it -- the next line, Set sh = ..., became part of the comment and sh was
' never set (2026-09-11: VOICEVOX failed to start on login).
Set sh = CreateObject("WScript.Shell")
ps = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ _
   & Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\")) _
   & "start_voicevox_minimized.ps1"""
sh.Run ps, 0, False

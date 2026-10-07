Option Explicit
Dim shell, root, command
Set shell = CreateObject("WScript.Shell")
root = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\JAV-Channel-Player"
command = "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & root & "\Supervisor.ps1"""
shell.Run command, 0, False

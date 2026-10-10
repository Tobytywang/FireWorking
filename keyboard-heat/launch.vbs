' Keyboard Heat Monitor - launcher that bypasses cmd.exe entirely.
'
' Double-clicking a .vbs runs it through WScript.exe, not the command
' interpreter, so none of the .bat code-page pitfalls apply. Use this
' if run.bat still refuses to start the overlay.
'
' 0 = hidden window, False = do not wait for it to exit.

Dim sh, proj, pyw, main
Set sh = CreateObject("WScript.Shell")

proj = "D:\Workspace\HardWorking\keyboard-heat"
pyw  = proj & "\.pyenv\Scripts\pythonw.exe"
main = proj & "\main.py"

sh.CurrentDirectory = proj
sh.Run """" & pyw & """ """ & main & """", 0, False

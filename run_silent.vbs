Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "P:\ALPHA\project\tapo-controller"
WshShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -aon ^| find "":8765"" ^| find ""LISTENING""') do taskkill /f /pid %a >nul 2>&1", 0, True
WshShell.Run "py -3.13 -m src.main", 0, False
Set WshShell = Nothing

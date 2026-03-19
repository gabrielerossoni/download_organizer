Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "taskkill /f /im pythonw.exe", 0, True
Dim WshShell, fso, ScriptDir, python, ollama
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = ScriptDir

' [1/3] Installazione dipendenze
WshShell.Run "cmd /c pip install -r """ & ScriptDir & "\requirements.txt"" --quiet 2>nul", 0, True

' [2/3] Ollama
Dim oExec
Set oExec = WshShell.Exec("tasklist /fi ""imagename eq ollama.exe""")
Dim output
output = oExec.StdOut.ReadAll()
If InStr(LCase(output), "ollama.exe") = 0 Then
    WshShell.Run "ollama serve", 0, False
    WScript.Sleep 5000
Else
    WScript.Sleep 5000
End If

' [3/3] Kill vecchio organizer e avvia nuovo
WshShell.Run "cmd /c wmic process where ""commandline like '%%organizer.py%%'"" delete >nul 2>&1", 0, True
WshShell.Run "pythonw -W ignore """ & ScriptDir & "\organizer.py""", 0, False
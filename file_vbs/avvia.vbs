On Error Resume Next

Dim WshShell, fso, ScriptDir
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ScriptDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
WshShell.CurrentDirectory = ScriptDir

' [0/2] Installazione dipendenze
WshShell.Run "pythonw -m pip install -r """ & ScriptDir & "\requirements.txt"" --quiet", 0, True
WScript.Sleep 30000

' [1/2] Ollama — check via WMI senza finestre
Dim objWMI, colProc, objProc
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set colProc = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='ollama.exe'")
If colProc.Count = 0 Then
    WshShell.Run "ollama serve", 0, False
    WScript.Sleep 5000
Else
    WScript.Sleep 1000
End If

' [2/2] Kill vecchio organizer e avvia nuovo
Set colProc = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='pythonw.exe' AND CommandLine LIKE '%organizer.py%'")
For Each objProc In colProc
    objProc.Terminate()
Next
WScript.Sleep 1000

WshShell.Run "pythonw -W ignore """ & ScriptDir & "\organizer.py""", 0, False
' Silent browser-mode launcher for Release Deployer.
' Double-click this file (or create a desktop shortcut) to start the app
' in your default browser with no visible terminal window.

Dim appDir, venvStreamlit, cmd, shell, port

Set fso = CreateObject("Scripting.FileSystemObject")
Dim p
p = WScript.ScriptFullName
appDir = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(p)))))
venvStreamlit = appDir & "\.venv\Scripts\streamlit.exe"

Set shell = CreateObject("WScript.Shell")

' Try ports 8501-8505 to avoid collisions
port = "8501"

If CreateObject("Scripting.FileSystemObject").FileExists(venvStreamlit) Then
    cmd = """" & venvStreamlit & """ run """ & appDir & "\orchestrator\entry\app.py"" --server.headless true --server.port " & port
Else
    cmd = "pythonw -m streamlit run """ & appDir & "\orchestrator\entry\app.py"" --server.headless true --server.port " & port
End If

shell.Run cmd, 0, False

WScript.Sleep 4000

shell.Run "http://127.0.0.1:" & port, 1, False

' Silent browser-mode launcher for Release Deployer.
' Double-click this file (or create a desktop shortcut) to start the app
' in your default browser with no visible terminal window.

Dim appDir, venvStreamlit, cmd, shell, port

appDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
venvStreamlit = appDir & "\.venv\Scripts\streamlit.exe"

Set shell = CreateObject("WScript.Shell")

' Try ports 8501-8505 to avoid collisions
port = "8501"

If CreateObject("Scripting.FileSystemObject").FileExists(venvStreamlit) Then
    cmd = """" & venvStreamlit & """ run """ & appDir & "\app.py"" --server.headless true --server.port " & port
Else
    cmd = "pythonw -m streamlit run """ & appDir & "\app.py"" --server.headless true --server.port " & port
End If

shell.Run cmd, 0, False

WScript.Sleep 4000

shell.Run "http://127.0.0.1:" & port, 1, False

$ProjectDir = "$HOME\projects\site-mockup-generator"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("$Desktop\Launch Site Mockup.lnk")
$s.TargetPath = "$ProjectDir\.venv\Scripts\pythonw.exe"
$s.Arguments = "launch.py"
$s.WorkingDirectory = $ProjectDir
$s.Save()
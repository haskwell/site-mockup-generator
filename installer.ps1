<#
.SYNOPSIS
    Studio Zero-Registry Non-Admin Windows GUI Installer & Updater.
.DESCRIPTION
    Installs, updates, and uninstalls Studio in %USERPROFILE%\projects\Studio.
    - Zero Administrator / UAC rights required.
    - Zero Windows Registry keys touched.
    - Preserves existing .env file across updates.
    - Configures Desktop Shortcut.
    - Supports both GitHub Release download and local ZIP testing.
#>

[CmdletBinding()]
param(
    [string]$RepoOwner = "haskwell",
    [string]$RepoName = "site-mockup-generator",
    [string]$AssetName = "Studio-Windows-x64.zip",
    [string]$LocalZipPath = ""
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression.FileSystem

# -------------------------------------------------------------
# Path Configurations (Strictly inside current user profile)
# -------------------------------------------------------------
$UserHome = $env:USERPROFILE
$ProjectsDir = Join-Path $UserHome "projects"
$InstallDir = Join-Path $ProjectsDir "Studio"
$ExePath = Join-Path $InstallDir "Studio.exe"
$EnvPath = Join-Path $InstallDir ".env"
$DesktopDir = [System.Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopDir "Studio.lnk"
$StartMenuDir = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)
$StartMenuShortcut = Join-Path $StartMenuDir "Studio.lnk"
$DownloadUrl = "https://github.com/$RepoOwner/$RepoName/releases/latest/download/$AssetName"

# -------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------
function Test-AppRunning {
    $proc = Get-Process -Name "Studio" -ErrorAction SilentlyContinue
    return ($null -ne $proc)
}

function Stop-AppRunning {
    $procs = Get-Process -Name "Studio" -ErrorAction SilentlyContinue
    if ($procs) {
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

function Create-DesktopShortcut {
    param([string]$Target, [string]$WorkDir, [string]$LinkFile)
    try {
        $wsh = New-Object -ComObject WScript.Shell
        $shortcut = $wsh.CreateShortcut($LinkFile)
        $shortcut.TargetPath = $Target
        $shortcut.WorkingDirectory = $WorkDir
        $shortcut.Description = "Studio Application"
        $shortcut.IconLocation = "$Target,0"
        $shortcut.Save()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wsh) | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Remove-DesktopShortcut {
    param([string]$LinkFile)
    if (Test-Path $LinkFile) {
        Remove-Item -Path $LinkFile -Force -ErrorAction SilentlyContinue
    }
}

function Write-UninstallHelper {
    param([string]$TargetDir, [string]$LnkFile, [string]$StartMenuLnk)
    $script = @"
@echo off
setlocal
echo ========================================================
echo               Studio Uninstaller
echo ========================================================
echo.
echo Closing any running Studio instances...
taskkill /f /im Studio.exe >nul 2>nul
timeout /t 1 /nobreak >nul

if exist "$LnkFile" (
    echo Removing Desktop Shortcut...
    del /f /q "$LnkFile" >nul 2>nul
)

if exist "$StartMenuLnk" (
    echo Removing Start Menu Entry...
    del /f /q "$StartMenuLnk" >nul 2>nul
)

set "KEEP_ENV=1"
if exist "$TargetDir\.env" (
    echo.
    set /p "DEL_ENV=Do you want to DELETE your .env configuration file as well? (y/N): "
    if /i "!DEL_ENV!"=="y" set "KEEP_ENV=0"
)

echo.
echo Removing application files...
if "%KEEP_ENV%"=="1" (
    for /d %%p in ("$TargetDir\*.*") do rmdir /s /q "%%p" >nul 2>nul
    for %%f in ("$TargetDir\*.*") do (
        if /i not "%%~nxf"==".env" (
            del /f /q "%%f" >nul 2>nul
        )
    )
    echo Application files removed. Your .env file was preserved.
) else (
    cd /d "%USERPROFILE%"
    rmdir /s /q "$TargetDir" >nul 2>nul
    echo Application and .env completely removed.
)

echo.
echo [SUCCESS] Studio uninstalled cleanly without touching Windows Registry.
pause
"@
    $uninstBat = Join-Path $TargetDir "uninstall.bat"
    Set-Content -Path $uninstBat -Value $script -Encoding ASCII
}

# -------------------------------------------------------------
# GUI Form Construction
# -------------------------------------------------------------
$form = New-Object System.Windows.Forms.Form
$form.Text = "Studio Installer & Updater"
$form.Size = New-Object System.Drawing.Size(560, 470)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.BackColor = [System.Drawing.Color]::FromArgb(248, 249, 250)

$iconPath = Join-Path $PSScriptRoot "assets\studio.ico"
if (Test-Path $iconPath) {
    try { $form.Icon = New-Object System.Drawing.Icon($iconPath) } catch {}
}

# Header Banner
$panelHeader = New-Object System.Windows.Forms.Panel
$panelHeader.Size = New-Object System.Drawing.Size(560, 75)
$panelHeader.Location = New-Object System.Drawing.Point(0, 0)
$panelHeader.BackColor = [System.Drawing.Color]::FromArgb(24, 30, 42)

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Text = "Studio Setup"
$lblTitle.Font = New-Object System.Drawing.Font("Segoe UI", 16, [System.Drawing.FontStyle]::Bold)
$lblTitle.ForeColor = [System.Drawing.Color]::White
$lblTitle.Location = New-Object System.Drawing.Point(24, 12)
$lblTitle.AutoSize = $true

$lblSubtitle = New-Object System.Windows.Forms.Label
$lblSubtitle.Text = "Non-Admin, Zero-Registry Portable Installer & Updater"
$lblSubtitle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblSubtitle.ForeColor = [System.Drawing.Color]::FromArgb(180, 190, 205)
$lblSubtitle.Location = New-Object System.Drawing.Point(26, 44)
$lblSubtitle.AutoSize = $true

$panelHeader.Controls.AddRange(@($lblTitle, $lblSubtitle))

# Target Directory Box
$grpTarget = New-Object System.Windows.Forms.GroupBox
$grpTarget.Text = "Target Installation Folder"
$grpTarget.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$grpTarget.Location = New-Object System.Drawing.Point(24, 90)
$grpTarget.Size = New-Object System.Drawing.Size(496, 68)

$txtTarget = New-Object System.Windows.Forms.TextBox
$txtTarget.Text = $InstallDir
$txtTarget.ReadOnly = $true
$txtTarget.Location = New-Object System.Drawing.Point(16, 26)
$txtTarget.Size = New-Object System.Drawing.Size(464, 25)
$grpTarget.Controls.Add($txtTarget)

# Status & Options
$chkShortcut = New-Object System.Windows.Forms.CheckBox
$chkShortcut.Text = "Desktop Shortcut"
$chkShortcut.Checked = $true
$chkShortcut.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$chkShortcut.Location = New-Object System.Drawing.Point(24, 168)
$chkShortcut.Size = New-Object System.Drawing.Size(150, 24)

$chkStartMenu = New-Object System.Windows.Forms.CheckBox
$chkStartMenu.Text = "Start Menu Entry"
$chkStartMenu.Checked = $true
$chkStartMenu.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$chkStartMenu.Location = New-Object System.Drawing.Point(180, 168)
$chkStartMenu.Size = New-Object System.Drawing.Size(160, 24)

# Source selector (GitHub vs Local file)
$lblSource = New-Object System.Windows.Forms.Label
$lblSource.Text = "Source: GitHub Releases (latest)"
$lblSource.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$lblSource.ForeColor = [System.Drawing.Color]::FromArgb(100, 110, 125)
$lblSource.Location = New-Object System.Drawing.Point(24, 198)
$lblSource.Size = New-Object System.Drawing.Size(350, 20)

$btnBrowseLocal = New-Object System.Windows.Forms.Button
$btnBrowseLocal.Text = "Use Local ZIP..."
$btnBrowseLocal.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$btnBrowseLocal.Location = New-Object System.Drawing.Point(400, 194)
$btnBrowseLocal.Size = New-Object System.Drawing.Size(120, 26)

# Progress Bar
$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(24, 230)
$progressBar.Size = New-Object System.Drawing.Size(496, 24)
$progressBar.Style = [System.Windows.Forms.ProgressBarStyle]::Blocks
$progressBar.Value = 0

# Status Label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = "Ready to install."
$lblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblStatus.Location = New-Object System.Drawing.Point(24, 262)
$lblStatus.Size = New-Object System.Drawing.Size(496, 38)

# Buttons
$btnAction = New-Object System.Windows.Forms.Button
$btnAction.Text = "Install Studio"
$btnAction.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$btnAction.BackColor = [System.Drawing.Color]::FromArgb(37, 99, 235)
$btnAction.ForeColor = [System.Drawing.Color]::White
$btnAction.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnAction.Location = New-Object System.Drawing.Point(24, 340)
$btnAction.Size = New-Object System.Drawing.Size(160, 42)

$btnUninstall = New-Object System.Windows.Forms.Button
$btnUninstall.Text = "Uninstall"
$btnUninstall.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$btnUninstall.BackColor = [System.Drawing.Color]::FromArgb(239, 68, 68)
$btnUninstall.ForeColor = [System.Drawing.Color]::White
$btnUninstall.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnUninstall.Location = New-Object System.Drawing.Point(194, 340)
$btnUninstall.Size = New-Object System.Drawing.Size(110, 42)
$btnUninstall.Visible = (Test-Path $InstallDir)

$btnLaunch = New-Object System.Windows.Forms.Button
$btnLaunch.Text = "Launch Studio"
$btnLaunch.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$btnLaunch.BackColor = [System.Drawing.Color]::FromArgb(16, 185, 129)
$btnLaunch.ForeColor = [System.Drawing.Color]::White
$btnLaunch.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnLaunch.Location = New-Object System.Drawing.Point(314, 340)
$btnLaunch.Size = New-Object System.Drawing.Size(120, 42)
$btnLaunch.Visible = (Test-Path $ExePath)

$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = "Exit"
$btnClose.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$btnClose.Location = New-Object System.Drawing.Point(444, 340)
$btnClose.Size = New-Object System.Drawing.Size(76, 42)

$form.Controls.AddRange(@(
    $panelHeader, $grpTarget, $chkShortcut, $chkStartMenu, $lblSource, $btnBrowseLocal,
    $progressBar, $lblStatus, $btnAction, $btnUninstall, $btnLaunch, $btnClose
))

# -------------------------------------------------------------
# Detect Initial State
# -------------------------------------------------------------
$script:SelectedLocalZip = $LocalZipPath

# Check if a local zip exists in script directory for effortless local testing
$autoLocalZip = Join-Path $PSScriptRoot $AssetName
$autoDistZip = Join-Path $PSScriptRoot "dist\$AssetName"
if (-not $script:SelectedLocalZip) {
    if (Test-Path $autoLocalZip) {
        $script:SelectedLocalZip = $autoLocalZip
    } elseif (Test-Path $autoDistZip) {
        $script:SelectedLocalZip = $autoDistZip
    }
}

if ($script:SelectedLocalZip -and (Test-Path $script:SelectedLocalZip)) {
    $lblSource.Text = "Source: Local ZIP (" + [System.IO.Path]::GetFileName($script:SelectedLocalZip) + ")"
    $lblSource.ForeColor = [System.Drawing.Color]::FromArgb(16, 149, 100)
}

function Refresh-UIState {
    if (Test-Path $InstallDir) {
        $btnAction.Text = "Update Studio"
        $btnAction.BackColor = [System.Drawing.Color]::FromArgb(13, 148, 136) # Teal
        $btnUninstall.Visible = $true
        if (Test-Path $EnvPath) {
            $lblStatus.Text = "Studio is currently installed. Ready to update.`n(Note: Your .env configuration will be preserved)."
        } else {
            $lblStatus.Text = "Studio is currently installed. Ready to update."
        }
    } else {
        $btnAction.Text = "Install Studio"
        $btnAction.BackColor = [System.Drawing.Color]::FromArgb(37, 99, 235) # Blue
        $btnUninstall.Visible = $false
        $lblStatus.Text = "Ready to install Studio to: " + $InstallDir
    }
    $btnLaunch.Visible = (Test-Path $ExePath)
}

Refresh-UIState

# -------------------------------------------------------------
# Event Handlers
# -------------------------------------------------------------
$btnBrowseLocal.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = "ZIP Packages (*.zip)|*.zip|All Files (*.*)|*.*"
    $dlg.Title = "Select Studio Release ZIP for Local Testing"
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $script:SelectedLocalZip = $dlg.FileName
        $lblSource.Text = "Source: Local ZIP (" + [System.IO.Path]::GetFileName($script:SelectedLocalZip) + ")"
        $lblSource.ForeColor = [System.Drawing.Color]::FromArgb(16, 149, 100)
    }
})

$btnLaunch.Add_Click({
    if (Test-Path $ExePath) {
        Start-Process -FilePath $ExePath -WorkingDirectory $InstallDir
        $form.Close()
    } else {
        [System.Windows.Forms.MessageBox]::Show("Executable not found at: $ExePath", "Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
    }
})

$btnClose.Add_Click({
    $form.Close()
})

$btnUninstall.Add_Click({
    if (Test-AppRunning) {
        $closePrompt = [System.Windows.Forms.MessageBox]::Show(
            "Studio is currently running in the background.`n`nWould you like to close it automatically to proceed with uninstallation?",
            "Close Running Studio",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        if ($closePrompt -eq [System.Windows.Forms.DialogResult]::Yes) {
            Stop-AppRunning
        } else {
            return
        }
    }

    $confirm = [System.Windows.Forms.MessageBox]::Show(
        "Are you sure you want to remove Studio from:`n$InstallDir?",
        "Confirm Uninstallation",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) { return }

    $keepEnv = $true
    if (Test-Path $EnvPath) {
        $envChoice = [System.Windows.Forms.MessageBox]::Show(
            "Do you want to KEEP your .env configuration file?`n`nClick 'Yes' to preserve .env`nClick 'No' to delete everything including .env",
            "Preserve .env File?",
            [System.Windows.Forms.MessageBoxButtons]::YesNoCancel,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        if ($envChoice -eq [System.Windows.Forms.DialogResult]::Cancel) { return }
        $keepEnv = ($envChoice -eq [System.Windows.Forms.DialogResult]::Yes)
    }

    $lblStatus.Text = "Removing Studio..."
    $form.Update()

    # 1. Remove Desktop and Start Menu Shortcuts
    Remove-DesktopShortcut -LinkFile $ShortcutPath
    Remove-DesktopShortcut -LinkFile $StartMenuShortcut

    # 2. Remove Files
    try {
        if ($keepEnv -and (Test-Path $EnvPath)) {
            $tempBackup = Join-Path $env:TEMP "Studio_env_uninst_backup.tmp"
            Copy-Item -Path $EnvPath -Destination $tempBackup -Force
            Remove-Item -Path "$InstallDir\*" -Recurse -Force -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
            Move-Item -Path $tempBackup -Destination $EnvPath -Force
            $lblStatus.Text = "Studio uninstalled cleanly. Your .env file was preserved."
        } else {
            Remove-Item -Path $InstallDir -Recurse -Force
            $lblStatus.Text = "Studio and all files removed cleanly."
        }
    } catch {
        $lblStatus.Text = "Error during file removal: $_"
    }

    $progressBar.Value = 0
    Refresh-UIState
    [System.Windows.Forms.MessageBox]::Show("Uninstallation complete. Zero registry entries were touched.", "Complete", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
})

$btnAction.Add_Click({
    if (Test-AppRunning) {
        $closePrompt = [System.Windows.Forms.MessageBox]::Show(
            "Studio is currently running in the background.`n`nWould you like to close it automatically to proceed with install/update?",
            "Close Running Studio",
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question
        )
        if ($closePrompt -eq [System.Windows.Forms.DialogResult]::Yes) {
            Stop-AppRunning
        } else {
            return
        }
    }

    $btnAction.Enabled = $false
    $btnUninstall.Enabled = $false
    $btnBrowseLocal.Enabled = $false
    $progressBar.Value = 0

    $tempZip = Join-Path $env:TEMP "Studio_Setup_Package.zip"

    # Step 1: Obtain Archive (Local or Download)
    if ($script:SelectedLocalZip -and (Test-Path $script:SelectedLocalZip)) {
        $lblStatus.Text = "Loading local package..."
        $form.Update()
        Copy-Item -Path $script:SelectedLocalZip -Destination $tempZip -Force
        $progressBar.Value = 40
    } else {
        $lblStatus.Text = "Connecting to GitHub Releases..."
        $form.Update()

        try {
            # Use System.Net.WebClient for progress callback
            $wc = New-Object System.Net.WebClient
            
            # Register download progress handler
            $wc.add_DownloadProgressChanged({
                param($sender, $e)
                $progressBar.Value = [Math]::Min(50, [int]($e.ProgressPercentage / 2))
                $lblStatus.Text = ("Downloading release: {0}% ({1:N1} MB / {2:N1} MB)" -f $e.ProgressPercentage, ($e.BytesReceived / 1MB), ($e.TotalBytesToReceive / 1MB))
            })

            $syncDone = $false
            $wc.add_DownloadFileCompleted({
                param($sender, $e)
                $syncDone = $true
            })

            # Synchronous download on background while pumping UI
            $asyncTask = $wc.DownloadFileTaskAsync($DownloadUrl, $tempZip)
            while (-not $asyncTask.IsCompleted) {
                [System.Windows.Forms.Application]::DoEvents()
                Start-Sleep -Milliseconds 50
            }

            if ($asyncTask.IsFaulted) {
                throw $asyncTask.Exception.InnerException.Message
            }
        } catch {
            [System.Windows.Forms.MessageBox]::Show(
                "Failed to download release from GitHub:`n$_`n`nTip: If you haven't published a GitHub release yet, click 'Use Local ZIP...' to test using a local build archive.",
                "Download Error",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Error
            )
            $btnAction.Enabled = $true
            $btnUninstall.Enabled = $true
            $btnBrowseLocal.Enabled = $true
            $progressBar.Value = 0
            $lblStatus.Text = "Download failed."
            return
        }
    }

    # Step 2: Ensure Target Directory Exists
    $lblStatus.Text = "Preparing installation directory..."
    $progressBar.Value = 55
    $form.Update()

    if (-not (Test-Path $ProjectsDir)) {
        New-Item -ItemType Directory -Path $ProjectsDir -Force | Out-Null
    }
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    # Step 3: Safeguard Existing .env
    $envBackup = Join-Path $env:TEMP "Studio_installer_env_backup.tmp"
    $hasExistingEnv = Test-Path $EnvPath
    if ($hasExistingEnv) {
        $lblStatus.Text = "Preserving existing .env configuration..."
        $form.Update()
        Copy-Item -Path $EnvPath -Destination $envBackup -Force
    }

    # Step 4: Extract Package
    $lblStatus.Text = "Extracting files to projects\Studio..."
    $progressBar.Value = 70
    $form.Update()

    try {
        # Open ZIP and extract each item. If root folder in zip is 'Studio', unpack its children.
        $zip = [System.IO.Compression.ZipFile]::OpenRead($tempZip)
        $totalEntries = $zip.Entries.Count
        $entryIdx = 0

        # Check if archive has a single top-level folder 'Studio/'
        $hasSingleRoot = $true
        foreach ($entry in $zip.Entries) {
            $firstSeg = $entry.FullName.Split('/')[0].Split('\')[0]
            if ($firstSeg -ne "Studio" -and $firstSeg -ne "") {
                $hasSingleRoot = $false
                break
            }
        }

        foreach ($entry in $zip.Entries) {
            $entryIdx++
            $relPath = $entry.FullName
            if ($hasSingleRoot) {
                $relPath = $relPath.Substring(7) # Strip 'Studio/' prefix
            }
            if ([string]::IsNullOrWhiteSpace($relPath)) { continue }

            $destPath = Join-Path $InstallDir $relPath

            if ($entry.FullName.EndsWith("/") -or $entry.FullName.EndsWith("\")) {
                if (-not (Test-Path $destPath)) {
                    New-Item -ItemType Directory -Path $destPath -Force | Out-Null
                }
            } else {
                # Never overwrite existing .env with a file from zip
                if ($relPath.Equals(".env", [System.StringComparison]::OrdinalIgnoreCase) -and $hasExistingEnv) {
                    continue
                }

                $parentDir = [System.IO.Path]::GetDirectoryName($destPath)
                if (-not (Test-Path $parentDir)) {
                    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
                }

                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $destPath, $true)
            }

            if ($entryIdx % 20 -eq 0) {
                $progressBar.Value = 70 + [int](($entryIdx / $totalEntries) * 20)
                [System.Windows.Forms.Application]::DoEvents()
            }
        }
        $zip.Dispose()
    } catch {
        [System.Windows.Forms.MessageBox]::Show("Extraction failed:`n$_", "Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        $btnAction.Enabled = $true
        $btnUninstall.Enabled = $true
        $btnBrowseLocal.Enabled = $true
        return
    } finally {
        if (Test-Path $tempZip) { Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue }
    }

    # Step 5: Verify and Restore .env
    if ($hasExistingEnv) {
        if (Test-Path $envBackup) {
            Copy-Item -Path $envBackup -Destination $EnvPath -Force
            Remove-Item -Path $envBackup -Force -ErrorAction SilentlyContinue
        }
    } elseif (-not (Test-Path $EnvPath)) {
        # First-time install: initialize .env from .env.example if present
        $exampleEnv = Join-Path $InstallDir ".env.example"
        if (Test-Path $exampleEnv) {
            Copy-Item -Path $exampleEnv -Destination $EnvPath -Force
        }
    }

    # Step 6: Create Desktop and Start Menu Shortcuts
    $progressBar.Value = 92
    if ($chkShortcut.Checked) {
        $lblStatus.Text = "Creating Desktop Shortcut..."
        $form.Update()
        Create-DesktopShortcut -Target $ExePath -WorkDir $InstallDir -LinkFile $ShortcutPath | Out-Null
    }
    if ($chkStartMenu.Checked) {
        $lblStatus.Text = "Creating Start Menu Entry..."
        $form.Update()
        if (-not (Test-Path $StartMenuDir)) {
            New-Item -ItemType Directory -Path $StartMenuDir -Force | Out-Null
        }
        Create-DesktopShortcut -Target $ExePath -WorkDir $InstallDir -LinkFile $StartMenuShortcut | Out-Null
    }

    # Step 7: Write Standalone Uninstaller Helper
    Write-UninstallHelper -TargetDir $InstallDir -LnkFile $ShortcutPath -StartMenuLnk $StartMenuShortcut

    $progressBar.Value = 100
    $lblStatus.Text = "Setup complete! Studio is ready to use.`nInstalled to: $InstallDir"

    $btnAction.Enabled = $true
    $btnUninstall.Enabled = $true
    $btnBrowseLocal.Enabled = $true
    Refresh-UIState

    [System.Windows.Forms.MessageBox]::Show(
        "Studio has been successfully installed / updated!`n`nLocation: $InstallDir`nRegistry: 0 keys modified`nPermissions: Standard User",
        "Success",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    )
})

# Display Form
[System.Windows.Forms.Application]::Run($form)

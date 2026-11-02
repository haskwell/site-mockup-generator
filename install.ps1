# ==============================================================================
# Studio Windows Installer & Auto-Updater
# Target location: C:\Users\<Username>\projects\Studio
# ==============================================================================

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ErrorActionPreference = "Stop"

$RepoOwner = "haskwell"
$RepoName  = "site-mockup-generator"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "           Studio Windows Installer & Updater          " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Target directory setup (C:\Users\<Username>\projects\Studio)
$projectsDir = Join-Path $env:USERPROFILE "projects"
if (-not (Test-Path $projectsDir)) {
    Write-Host "[*] Creating folder: $projectsDir" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $projectsDir -Force | Out-Null
}

$installDir = Join-Path $projectsDir "Studio"
$versionFile = Join-Path $installDir ".version"
$envPath = Join-Path $installDir ".env"

# 2. Check latest release metadata from GitHub (No token needed for public releases)
$releaseApi = "https://api.github.com/repos/$RepoOwner/$RepoName/releases/latest"
$headers = @{ "User-Agent" = "Studio-Installer" }
$remoteVersion = ""
$downloadUrl = "https://github.com/$RepoOwner/$RepoName/releases/latest/download/Studio-Windows.zip"

Write-Host "[*] Checking for latest release on GitHub..." -ForegroundColor Cyan
try {
    $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers -Method Get
    if ($release.tag_name) {
        $remoteVersion = "$($release.tag_name) ($($release.published_at))"
    }
    # Match asset if available
    $asset = $release.assets | Where-Object { $_.name -like "*Studio-Windows*.zip" -or $_.name -like "*.zip" } | Select-Object -First 1
    if ($asset -and $asset.browser_download_url) {
        $downloadUrl = $asset.browser_download_url
    }
} catch {
    Write-Host "[!] Note: Could not query GitHub API (rate limit or network), falling back to direct release download." -ForegroundColor Yellow
    $remoteVersion = "latest"
}

# 3. Check if already up-to-date
if ((Test-Path $installDir) -and (Test-Path $versionFile) -and ($remoteVersion -ne "latest")) {
    $localVersion = (Get-Content $versionFile -ErrorAction SilentlyContinue).Trim()
    if ($localVersion -eq $remoteVersion) {
        Write-Host ""
        Write-Host "[SUCCESS] Studio is already up to date!" -ForegroundColor Green
        Write-Host "Current version: $localVersion" -ForegroundColor Gray
        Write-Host "Location: $installDir" -ForegroundColor Gray
        Write-Host ""
        
        $choice = Read-Host "Would you like to launch Studio now? (Y/N)"
        if ($choice -match "^[yY]") {
            Start-Process (Join-Path $installDir "Studio.exe")
        }
        exit 0
    }
    Write-Host "[*] Update available: $localVersion -> $remoteVersion" -ForegroundColor Yellow
} else {
    Write-Host "[*] Installing version: $remoteVersion" -ForegroundColor Cyan
}

# 4. Terminate running instance if updating
$runningProc = Get-Process -Name "Studio" -ErrorAction SilentlyContinue
if ($runningProc) {
    Write-Host "[!] Studio is currently running. Stopping process before updating..." -ForegroundColor Yellow
    $runningProc | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# 5. BACKUP .env FILE TO SAFE TEMP DIRECTORY (Ensures it is never nuked)
$envBackupPath = Join-Path $env:TEMP "studio_env_backup_$([Guid]::NewGuid().ToString('N')).env"
$hasExistingEnv = Test-Path $envPath

if ($hasExistingEnv) {
    Write-Host "[*] Safeguarding your existing .env file..." -ForegroundColor Cyan
    Copy-Item -Path $envPath -Destination $envBackupPath -Force
}

# 6. Download release ZIP
$tempZip = Join-Path $env:TEMP "Studio-Windows.zip"
$tempExtract = Join-Path $env:TEMP "Studio-Extract-$([Guid]::NewGuid().ToString('N'))"

Write-Host "[*] Downloading from: $downloadUrl" -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $tempZip -UseBasicParsing
} catch {
    Write-Host "[ERROR] Failed to download release ZIP. Ensure a release exists at:" -ForegroundColor Red
    Write-Host "        https://github.com/$RepoOwner/$RepoName/releases" -ForegroundColor Red
    if ($hasExistingEnv -and (Test-Path $envBackupPath)) {
        Remove-Item -Path $envBackupPath -Force -ErrorAction SilentlyContinue
    }
    exit 1
}

# 7. Extract archive
Write-Host "[*] Extracting files..." -ForegroundColor Cyan
if (Test-Path $tempExtract) { Remove-Item -Path $tempExtract -Recurse -Force }
Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force

# Locate extracted contents (handling nested 'Studio' folder or flat structure)
$extractedStudio = Join-Path $tempExtract "Studio"
$sourceDir = if (Test-Path (Join-Path $extractedStudio "Studio.exe")) { $extractedStudio } else { $tempExtract }

if (-not (Test-Path $installDir)) {
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# 8. Copy updated files over into installation directory
Write-Host "[*] Installing update to $installDir..." -ForegroundColor Cyan
Copy-Item -Path "$sourceDir\*" -Destination $installDir -Recurse -Force

# 9. RESTORE & VERIFY .env FILE
if ($hasExistingEnv) {
    if (Test-Path $envBackupPath) {
        Copy-Item -Path $envBackupPath -Destination $envPath -Force
        Remove-Item -Path $envBackupPath -Force -ErrorAction SilentlyContinue
        Write-Host "[SUCCESS] Your original .env file was preserved and restored intact." -ForegroundColor Green
    }
} else {
    # If first time install and .env doesn't exist, create it from .env.example
    $envExample = Join-Path $installDir ".env.example"
    if (Test-Path $envExample) {
        Copy-Item -Path $envExample -Destination $envPath -Force
        Write-Host "[*] Generated new .env configuration file from template." -ForegroundColor Cyan
    }
}

# 10. Update stored version stamp
if ($remoteVersion) {
    Set-Content -Path $versionFile -Value $remoteVersion -Force
}

# 11. Clean up temporary extraction files
Remove-Item -Path $tempZip -Force -ErrorAction SilentlyContinue
Remove-Item -Path $tempExtract -Recurse -Force -ErrorAction SilentlyContinue

# 12. Create / Update Desktop Shortcut
try {
    $wscript = New-Object -ComObject WScript.Shell
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktopPath "Studio.lnk"
    $shortcut = $wscript.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $installDir "Studio.exe"
    $shortcut.WorkingDirectory = $installDir
    $icoPath = Join-Path $installDir "assets\studio.ico"
    if (Test-Path $icoPath) {
        $shortcut.IconLocation = $icoPath
    }
    $shortcut.Save()
    Write-Host "[✓] Desktop shortcut created." -ForegroundColor Green
} catch {
    # Non-critical if shortcut creation fails
}

# 13. Check agy prerequisite
$agyFound = Get-Command "agy" -ErrorAction SilentlyContinue
if (-not $agyFound) {
    $altAgy = Join-Path $env:LOCALAPPDATA "Programs\agy\bin\agy.exe"
    if (-not (Test-Path $altAgy)) {
        $altAgy = Join-Path $env:LOCALAPPDATA "Programs\agy\agy.exe"
    }
    if (Test-Path $altAgy) { $agyFound = $true }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Studio installation/update complete!         " -ForegroundColor Green
Write-Host " Location: $installDir                                  " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""

if (-not $agyFound) {
    Write-Host "[REMINDER] The 'agy' CLI was not detected on your PATH." -ForegroundColor Yellow
    Write-Host "           Remember to install and log in to 'agy' to build mockups." -ForegroundColor Yellow
    Write-Host ""
}

$choice = Read-Host "Launch Studio now? (Y/N)"
if ($choice -match "^[yY]") {
    Start-Process (Join-Path $installDir "Studio.exe")
}

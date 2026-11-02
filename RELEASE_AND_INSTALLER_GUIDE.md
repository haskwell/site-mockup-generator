# Studio Release & Installer Guide

This guide explains how to package GitHub releases, test the zero-registry non-admin GUI installer on your local Windows machine first, and distribute updates safely to end users.

---

## 1. What Has Been Implemented

1. **GitHub Actions Workflow** ([`.github/workflows/release.yml`](.github/workflows/release.yml)):
   - Automatically builds `dist/Studio` on a Windows runner upon pushing any version tag (e.g., `v1.0.0`).
   - Packages `dist/Studio-Windows-x64.zip`.
   - Compiles the standalone single-file installer `StudioInstaller.exe`.
   - Publishes both to GitHub Releases under your public repository (`haskwell/site-mockup-generator`).

2. **Native Windows GUI Installer & Updater** ([`installer.ps1`](installer.ps1) + [`Studio-Installer.bat`](Studio-Installer.bat)):
   - **Zero Admin / UAC**: Runs as standard user (`asInvoker`).
   - **Zero Registry**: Modifies zero Windows Registry keys (leaves no registry footprint).
   - **Target**: `C:\Users\<username>\projects\Studio`.
   - **Desktop Shortcut**: Creates `%USERPROFILE%\Desktop\Studio.lnk` using shell link API.
   - **Update Safe**: When run again, updates binaries but strictly preserves your `.env` file.
   - **Uninstaller**: Offers one-click uninstallation from the GUI or via `projects\Studio\uninstall.bat`.

3. **Standalone Python GUI Installer** ([`scripts/installer_gui.py`](scripts/installer_gui.py) + [`scripts/build_installer.bat`](scripts/build_installer.bat)):
   - Complete Tkinter-based equivalent that can be compiled into a single `.exe`.

4. **Local Testing Packager** ([`package_release_local.bat`](package_release_local.bat)):
   - Packages your local build into `dist/Studio-Windows-x64.zip` so you can test the installer offline on your Windows machine before publishing anything to GitHub.

---

## 2. Testing on Your Windows Machine (Offline Local Mode)

You can test the entire installation, update, `.env` preservation, and uninstallation workflow right now on your Windows PC:

### Step 1: Package Local Build
Run:
```cmd
package_release_local.bat
```
- If you haven't compiled the app yet, it runs `build_exe.bat` to compile `Studio.exe`.
- It copies `.env.example` to the dist folder.
- It compresses `dist\Studio\*` into `dist\Studio-Windows-x64.zip`.

### Step 2: Run the GUI Installer
Double-click:
```cmd
Studio-Installer.bat
```
*(Or if you prefer Python: `python scripts\installer_gui.py`)*

- The GUI window will open.
- Notice the source indicator in green: `Source: Local ZIP (Studio-Windows-x64.zip)`. The installer automatically detected your local zip!
- Target path displays: `C:\Users\<YourUser>\projects\Studio`.
- Click **Install Studio**:
  - The progress bar fills as it extracts files into `C:\Users\<YourUser>\projects\Studio`.
  - It creates a **Desktop Shortcut** (`Studio.lnk`).
  - It generates `projects\Studio\uninstall.bat`.
  - Zero UAC dialogs appeared and zero registry keys were touched.

### Step 3: Test `.env` Preservation During an Update
1. Navigate to `C:\Users\<YourUser>\projects\Studio`.
2. Notice the `.env` file (copied from `.env.example`).
3. Open `.env` in Notepad and add a custom line at the end, for example:
   ```env
   MY_TEST_TOKEN=12345_do_not_delete_me
   ```
   Save and close the file.
4. Run `Studio-Installer.bat` again:
   - Notice the button now says **Update Studio** (teal color).
   - The status bar notes: *(Note: Your .env configuration will be preserved)*.
5. Click **Update Studio**:
   - The installer overwrites application binaries with the latest files.
   - Open `C:\Users\<YourUser>\projects\Studio\.env` in Notepad.
   - **Verification**: Your `MY_TEST_TOKEN=12345_do_not_delete_me` is completely intact!

### Step 4: Test Clean Uninstallation
You can uninstall through two equivalent zero-registry methods:
- **Method A (From Installer GUI)**: Run `Studio-Installer.bat` and click the red **Uninstall** button.
- **Method B (From Folder)**: Double-click `C:\Users\<YourUser>\projects\Studio\uninstall.bat`.

Both methods will:
1. Ask if you want to keep or delete your `.env` file.
2. Delete the Desktop shortcut (`Studio.lnk`).
3. Clean up the application folder from `projects\`.
4. Leave zero residual registry entries on Windows.

---

## 3. How GitHub Releases Are Created

Once you are ready to publish releases to GitHub:

### Method 1: Git Tag (Automatic CI/CD)
Whenever you push a version tag to GitHub, GitHub Actions handles the rest:
```bash
git add .
git commit -m "Add GitHub release workflow and zero-registry installer"
git push origin master

# Create and push a version tag:
git tag v1.0.0
git push origin v1.0.0
```

1. GitHub Actions spins up a clean `windows-latest` machine.
2. It sets up Python 3.11 and installs requirements.
3. It compiles `Studio.exe` using `studio.spec`.
4. It compresses the output into `Studio-Windows-x64.zip`.
5. It compiles `StudioInstaller.exe` from `scripts/installer_gui.py`.
6. It creates a GitHub Release tagged `v1.0.0` and attaches:
   - `Studio-Windows-x64.zip`
   - `StudioInstaller.exe`

### Method 2: Manual Trigger via GitHub Web UI
You can also trigger a release manually without creating a git tag:
1. Go to your repository on GitHub (`haskwell/site-mockup-generator`).
2. Click **Actions** > **Build & Publish Release**.
3. Click **Run workflow**, enter a tag name (e.g. `v1.0.0`), and run.

---

## 4. How End-Users Install & Update Studio

Once your release is published on GitHub:
1. Direct users to your GitHub Releases page to download **`StudioInstaller.exe`** (or `Studio-Installer.bat` + `installer.ps1`).
2. The user double-clicks the installer.
3. The installer connects to:
   `https://github.com/haskwell/site-mockup-generator/releases/latest/download/Studio-Windows-x64.zip`
4. It downloads the archive and installs it to `C:\Users\<username>\projects\Studio`.
5. A desktop shortcut is created.
6. When you publish `v1.0.1` or later:
   - The user opens the installer again.
   - It downloads the latest release and updates all binaries.
   - Their local `.env` and Cloudflare/R2 credentials are preserved.

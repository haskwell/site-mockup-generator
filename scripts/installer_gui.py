#!/usr/bin/env python3
"""Zero-Registry Non-Admin Windows GUI Installer & Updater for Studio.

Key Guarantees:
- Never touches Windows Registry.
- Never requires Administrator / UAC elevation.
- Installs to %USERPROFILE%\\projects\\Studio.
- Safely preserves .env across updates.
- Creates user-level Desktop shortcut.
- Clean uninstallation (removes files and shortcut only).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

REPO_OWNER = "haskwell"
REPO_NAME = "site-mockup-generator"
ASSET_NAME = "Studio-Windows-x64.zip"
DOWNLOAD_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest/download/{ASSET_NAME}"

# Directories strictly inside current user profile
USER_PROFILE = Path(os.environ.get("USERPROFILE", Path.home()))
PROJECTS_DIR = USER_PROFILE / "projects"
INSTALL_DIR = PROJECTS_DIR / "Studio"
EXE_PATH = INSTALL_DIR / "Studio.exe"
ENV_PATH = INSTALL_DIR / ".env"
DESKTOP_DIR = USER_PROFILE / "Desktop"
SHORTCUT_PATH = DESKTOP_DIR / "Studio.lnk"


def is_app_running() -> bool:
    """Check if Studio.exe is currently active in memory."""
    if sys.platform != "win32":
        return False
    try:
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Studio.exe", "/NH"],
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return "Studio.exe" in output
    except Exception:
        return False


def stop_app_processes() -> None:
    """Forcefully close any lingering Studio.exe processes."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", "Studio.exe"],
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except Exception:
            pass


def create_desktop_shortcut(target: Path, work_dir: Path, shortcut: Path) -> bool:
    """Create a Windows desktop shortcut without registry access."""
    if sys.platform != "win32":
        return False
    ps_cmd = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.WorkingDirectory = '{work_dir}'; "
        f"$s.IconLocation = '{target},0'; "
        f"$s.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return True
    except Exception:
        return False


def remove_desktop_shortcut(shortcut: Path) -> None:
    """Remove desktop shortcut if present."""
    try:
        if shortcut.exists():
            shortcut.unlink(missing_ok=True)
    except Exception:
        pass


def write_uninstall_bat(target_dir: Path, shortcut: Path) -> None:
    """Write an offline, registry-free uninstall.bat file inside the installation folder."""
    script_content = f"""@echo off
setlocal
echo ========================================================
echo                 Studio Uninstaller
echo ========================================================
echo.
echo Closing any running Studio instances...
taskkill /f /im Studio.exe >nul 2>nul
timeout /t 1 /nobreak >nul

if exist "{shortcut}" (
    echo Removing Desktop Shortcut...
    del /f /q "{shortcut}" >nul 2>nul
)

set "KEEP_ENV=1"
if exist "{target_dir}\\.env" (
    echo.
    set /p "DEL_ENV=Do you want to DELETE your .env configuration file as well? (y/N): "
    if /i "!DEL_ENV!"=="y" set "KEEP_ENV=0"
)

echo.
echo Removing Studio application files...
if "%KEEP_ENV%"=="1" (
    for /d %%p in ("{target_dir}\\*.*") do rmdir /s /q "%%p" >nul 2>nul
    for %%f in ("{target_dir}\\*.*") do (
        if /i not "%%~nxf"==".env" del /f /q "%%f" >nul 2>nul
    )
    echo Done. Application removed; .env preserved.
) else (
    cd /d "%USERPROFILE%"
    rmdir /s /q "{target_dir}" >nul 2>nul
    echo Done. Application and .env completely removed.
)

echo.
echo [SUCCESS] Studio uninstalled cleanly without touching Windows Registry.
pause
"""
    try:
        (target_dir / "uninstall.bat").write_text(script_content, encoding="ascii", errors="ignore")
    except Exception:
        pass


class InstallerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Studio Setup & Updater")
        self.geometry("540x440")
        self.resizable(False, False)
        self.configure(bg="#F8F9FA")

        self.local_zip: Path | None = None
        self._find_default_local_zip()

        self._build_ui()
        self._refresh_state()

    def _find_default_local_zip(self) -> None:
        """Check if a release zip exists locally next to script or in dist/."""
        script_dir = Path(__file__).resolve().parent
        parent_dir = script_dir.parent

        candidates = [
            script_dir / ASSET_NAME,
            parent_dir / ASSET_NAME,
            parent_dir / "dist" / ASSET_NAME,
        ]
        for c in candidates:
            if c.is_file():
                self.local_zip = c
                break

    def _build_ui(self) -> None:
        # Header banner
        header = tk.Frame(self, bg="#181E2A", height=75)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        lbl_title = tk.Label(
            header,
            text="Studio Setup",
            font=("Segoe UI", 16, "bold"),
            fg="#FFFFFF",
            bg="#181E2A",
        )
        lbl_title.pack(anchor=tk.W, padx=24, pady=(12, 0))

        lbl_sub = tk.Label(
            header,
            text="Non-Admin, Zero-Registry Portable Installer & Updater",
            font=("Segoe UI", 9),
            fg="#B4BECD",
            bg="#181E2A",
        )
        lbl_sub.pack(anchor=tk.W, padx=24, pady=(2, 0))

        content = tk.Frame(self, bg="#F8F9FA", padx=24, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        # Destination frame
        dest_group = tk.LabelFrame(
            content,
            text=" Target Installation Folder ",
            font=("Segoe UI", 9),
            bg="#F8F9FA",
            fg="#333333",
            padx=10,
            pady=8,
        )
        dest_group.pack(fill=tk.X, pady=(0, 12))

        lbl_path = tk.Label(
            dest_group,
            text=str(INSTALL_DIR),
            font=("Consolas", 9),
            bg="#FFFFFF",
            relief="solid",
            bd=1,
            anchor="w",
            padx=8,
            pady=4,
        )
        lbl_path.pack(fill=tk.X)

        # Desktop shortcut checkbox
        self.var_shortcut = tk.BooleanVar(value=True)
        chk_shortcut = tk.Checkbutton(
            content,
            text="Create Desktop Shortcut (Studio.lnk)",
            variable=self.var_shortcut,
            font=("Segoe UI", 9),
            bg="#F8F9FA",
            activebackground="#F8F9FA",
        )
        chk_shortcut.pack(anchor=tk.W, pady=(0, 8))

        # Source selection
        src_frame = tk.Frame(content, bg="#F8F9FA")
        src_frame.pack(fill=tk.X, pady=(0, 8))

        self.lbl_source = tk.Label(
            src_frame,
            text="Source: GitHub Releases (latest)",
            font=("Segoe UI", 8),
            fg="#64707D",
            bg="#F8F9FA",
            anchor="w",
        )
        self.lbl_source.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_browse = tk.Button(
            src_frame,
            text="Use Local ZIP...",
            font=("Segoe UI", 8),
            command=self._on_browse_local,
            bg="#E2E8F0",
            relief="flat",
            padx=8,
        )
        btn_browse.pack(side=tk.RIGHT)

        if self.local_zip and self.local_zip.is_file():
            self.lbl_source.config(
                text=f"Source: Local ZIP ({self.local_zip.name})",
                fg="#10B981",
            )

        # Progress bar
        self.progress = ttk.Progressbar(content, orient="horizontal", mode="determinate")
        self.progress.pack(fill=tk.X, pady=(8, 6))

        # Status Label
        self.lbl_status = tk.Label(
            content,
            text="Ready.",
            font=("Segoe UI", 9),
            fg="#1F2937",
            bg="#F8F9FA",
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self.lbl_status.pack(fill=tk.X, pady=(0, 16))

        # Action Buttons frame
        btn_frame = tk.Frame(content, bg="#F8F9FA")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.btn_action = tk.Button(
            btn_frame,
            text="Install Studio",
            font=("Segoe UI", 9, "bold"),
            bg="#2563EB",
            fg="#FFFFFF",
            relief="flat",
            padx=14,
            pady=6,
            command=self._start_install_or_update,
        )
        self.btn_action.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_uninstall = tk.Button(
            btn_frame,
            text="Uninstall",
            font=("Segoe UI", 9),
            bg="#EF4444",
            fg="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
            command=self._on_uninstall,
        )
        self.btn_uninstall.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_launch = tk.Button(
            btn_frame,
            text="Launch Studio",
            font=("Segoe UI", 9, "bold"),
            bg="#10B981",
            fg="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
            command=self._on_launch,
        )
        self.btn_launch.pack(side=tk.LEFT, padx=(0, 8))

        btn_exit = tk.Button(
            btn_frame,
            text="Exit",
            font=("Segoe UI", 9),
            relief="flat",
            bg="#E5E7EB",
            padx=12,
            pady=6,
            command=self.destroy,
        )
        btn_exit.pack(side=tk.RIGHT)

    def _refresh_state(self) -> None:
        if INSTALL_DIR.is_dir() and any(INSTALL_DIR.iterdir()):
            self.btn_action.config(text="Update Studio", bg="#0D9488")
            self.btn_uninstall.pack(side=tk.LEFT, padx=(0, 8))
            if ENV_PATH.is_file():
                self.lbl_status.config(
                    text="Studio is currently installed. Ready to update.\n(Note: Your existing .env configuration will be preserved)."
                )
            else:
                self.lbl_status.config(text="Studio is currently installed. Ready to update.")
        else:
            self.btn_action.config(text="Install Studio", bg="#2563EB")
            self.btn_uninstall.pack_forget()
            self.lbl_status.config(text=f"Ready to install Studio to:\n{INSTALL_DIR}")

        if EXE_PATH.is_file():
            self.btn_launch.pack(side=tk.LEFT, padx=(0, 8))
        else:
            self.btn_launch.pack_forget()

    def _on_browse_local(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Select Studio Release ZIP",
            filetypes=[("ZIP Archive", "*.zip"), ("All Files", "*.*")],
        )
        if chosen:
            self.local_zip = Path(chosen)
            self.lbl_source.config(
                text=f"Source: Local ZIP ({self.local_zip.name})",
                fg="#10B981",
            )

    def _on_launch(self) -> None:
        if EXE_PATH.is_file():
            try:
                subprocess.Popen([str(EXE_PATH)], cwd=str(INSTALL_DIR))
                self.destroy()
            except Exception as e:
                messagebox.showerror("Launch Error", f"Failed to launch Studio:\n{e}")
        else:
            messagebox.showerror("Error", f"Executable not found at:\n{EXE_PATH}")

    def _on_uninstall(self) -> None:
        if is_app_running():
            if messagebox.askyesno(
                "Studio Running",
                "Studio is currently running in the background.\n\nWould you like to close it automatically to proceed with uninstallation?",
            ):
                stop_app_processes()
                import time
                time.sleep(0.5)
            else:
                return

        if not messagebox.askyesno(
            "Confirm Uninstall",
            f"Are you sure you want to remove Studio from:\n{INSTALL_DIR}?",
        ):
            return

        keep_env = True
        if ENV_PATH.is_file():
            res = messagebox.askyesnocancel(
                "Preserve .env File?",
                "Do you want to KEEP your .env configuration file?\n\n"
                "• Click [Yes] to remove Studio while keeping .env\n"
                "• Click [No] to delete everything including .env\n"
                "• Click [Cancel] to abort uninstallation",
            )
            if res is None:
                return
            keep_env = res

        remove_desktop_shortcut(SHORTCUT_PATH)

        try:
            if keep_env and ENV_PATH.is_file():
                temp_env = Path(os.environ.get("TEMP", "/tmp")) / "studio_env_uninst.tmp"
                shutil.copy2(ENV_PATH, temp_env)
                shutil.rmtree(INSTALL_DIR, ignore_errors=True)
                INSTALL_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(temp_env, ENV_PATH)
                self.lbl_status.config(text="Studio uninstalled cleanly. Your .env file was preserved.")
            else:
                shutil.rmtree(INSTALL_DIR, ignore_errors=True)
                self.lbl_status.config(text="Studio completely removed.")
            messagebox.showinfo("Success", "Studio uninstalled successfully.\nZero registry keys were touched.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove directory:\n{e}")

        self.progress["value"] = 0
        self._refresh_state()

    def _start_install_or_update(self) -> None:
        if is_app_running():
            if messagebox.askyesno(
                "Studio Running",
                "Studio is currently running in the background.\n\nWould you like to close it automatically to proceed with install/update?",
            ):
                stop_app_processes()
                import time
                time.sleep(0.5)
            else:
                return

        self.btn_action.config(state="disabled")
        self.btn_uninstall.config(state="disabled")
        self.progress["value"] = 0

        thread = threading.Thread(target=self._worker_install, daemon=True)
        thread.start()

    def _worker_install(self) -> None:
        temp_dir = Path(os.environ.get("TEMP", "/tmp"))
        temp_zip = temp_dir / "Studio_Setup_Package.zip"

        try:
            # 1. Fetch file
            if self.local_zip and self.local_zip.is_file():
                self._update_ui_status("Copying local package...", 30)
                shutil.copy2(self.local_zip, temp_zip)
            else:
                self._update_ui_status("Connecting to GitHub Releases...", 10)

                def report_hook(block_num: int, block_size: int, total_size: int) -> None:
                    if total_size > 0:
                        downloaded = block_num * block_size
                        pct = min(50, int((downloaded / total_size) * 50))
                        mb_done = downloaded / (1024 * 1024)
                        mb_tot = total_size / (1024 * 1024)
                        self._update_ui_status(
                            f"Downloading release: {mb_done:.1f} MB / {mb_tot:.1f} MB",
                            pct,
                        )

                try:
                    urllib.request.urlretrieve(DOWNLOAD_URL, temp_zip, reporthook=report_hook)
                except Exception as dl_err:
                    raise RuntimeError(
                        f"Failed to download release from GitHub:\n{dl_err}\n\n"
                        f"Tip: If you have not published a release yet, click 'Use Local ZIP...' to test offline."
                    ) from dl_err

            # 2. Prepare folders
            self._update_ui_status("Preparing installation directory...", 60)
            PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
            INSTALL_DIR.mkdir(parents=True, exist_ok=True)

            # 3. Safeguard existing .env
            env_backup = temp_dir / "studio_env_backup.tmp"
            has_existing_env = ENV_PATH.is_file()
            if has_existing_env:
                self._update_ui_status("Safeguarding .env configuration...", 65)
                shutil.copy2(ENV_PATH, env_backup)

            # 4. Extract archive
            self._update_ui_status("Extracting files to projects\\Studio...", 75)
            with zipfile.ZipFile(temp_zip, "r") as zf:
                entries = zf.infolist()
                total_entries = len(entries)

                # Detect if contents are nested under a single "Studio/" top folder
                has_single_root = all(
                    e.filename.startswith("Studio/") or e.filename.startswith("Studio\\") or e.filename == "Studio"
                    for e in entries
                    if not e.is_dir()
                )

                for idx, entry in enumerate(entries):
                    rel = entry.filename
                    if has_single_root:
                        rel = rel.replace("Studio/", "", 1).replace("Studio\\", "", 1)
                    if not rel or rel.endswith("/") or rel.endswith("\\"):
                        continue

                    # Never overwrite .env during extraction
                    if rel.lower() == ".env" and has_existing_env:
                        continue

                    target_file = INSTALL_DIR / rel
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    with zf.open(entry) as src, open(target_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

                    if idx % 15 == 0 and total_entries > 0:
                        pct = 75 + int((idx / total_entries) * 15)
                        self._update_ui_status("Extracting files...", pct)

            # 5. Restore or Initialize .env
            if has_existing_env:
                if env_backup.is_file():
                    shutil.copy2(env_backup, ENV_PATH)
                    env_backup.unlink(missing_ok=True)
            elif not ENV_PATH.is_file():
                example_env = INSTALL_DIR / ".env.example"
                if example_env.is_file():
                    shutil.copy2(example_env, ENV_PATH)

            # 6. Desktop Shortcut
            if self.var_shortcut.get():
                self._update_ui_status("Creating Desktop shortcut...", 95)
                create_desktop_shortcut(EXE_PATH, INSTALL_DIR, SHORTCUT_PATH)

            # 7. Write Standalone Uninstaller script
            write_uninstall_bat(INSTALL_DIR, SHORTCUT_PATH)

            # Cleanup
            temp_zip.unlink(missing_ok=True)

            self._update_ui_status("Setup complete! Studio is ready to use.", 100)
            self.after(0, self._on_install_success)

        except Exception as e:
            self._update_ui_status(f"Error: {e}", 0)
            self.after(0, lambda: messagebox.showerror("Setup Failed", str(e)))
        finally:
            self.after(0, self._on_install_done)

    def _update_ui_status(self, text: str, progress_val: int) -> None:
        def update():
            self.lbl_status.config(text=text)
            self.progress["value"] = progress_val

        self.after(0, update)

    def _on_install_success(self) -> None:
        messagebox.showinfo(
            "Success",
            f"Studio has been successfully installed / updated!\n\n"
            f"Target: {INSTALL_DIR}\n"
            f"Registry entries modified: 0\n"
            f"Privileges required: Standard User",
        )

    def _on_install_done(self) -> None:
        self.btn_action.config(state="normal")
        self.btn_uninstall.config(state="normal")
        self._refresh_state()


def main() -> int:
    app = InstallerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

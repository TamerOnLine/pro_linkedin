import os
import sys
import time
import json
import socket
import subprocess
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

try:
    import pyperclip
except Exception:
    pyperclip = None

# ===== Brave Auto Configuration =====
BRAVE_PATH = os.environ.get(
    "BRAVE_PATH",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
)
BRAVE_PROFILE_DIR = os.environ.get("BRAVE_PROFILE_DIR", r"C:\BraveDebug")

def find_free_port():
    """Finds a free port for the debugger to attach."""
    import socket as s
    with s.socket() as sock:
        sock.bind(('', 0))
        return sock.getsockname()[1]

def kill_brave():
    """Kills any existing Brave browser processes."""
    try:
        subprocess.run(["taskkill", "/IM", "brave.exe", "/F"], capture_output=True)
    except Exception:
        pass

def start_brave_debug(port: int):
    """Starts Brave with remote debugging enabled on the given port."""
    os.makedirs(BRAVE_PROFILE_DIR, exist_ok=True)
    return subprocess.Popen([
        BRAVE_PATH,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={BRAVE_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_for_devtools(port: int, timeout: float = 15.0) -> bool:
    """Waits for DevTools to become available on the specified port."""
    url = f"http://127.0.0.1:{port}/json/version"
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(url, timeout=0.6) as resp:
                if "webSocketDebuggerUrl" in json.load(resp):
                    return True
        except Exception:
            time.sleep(0.2)
    return False

def make_driver_attached_to(port: int):
    """Attaches a Selenium driver to an existing Brave browser session."""
    opts = webdriver.ChromeOptions()
    opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    opts.add_argument("--remote-allow-origins=*")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=opts)

def boot_brave_and_driver():
    port = find_free_port()
    try:
        # نحاول الاتصال مباشرة (لنفترض Brave شغال بالفعل)
        test_driver = make_driver_attached_to(port)
        return test_driver
    except Exception:
        # إذا فشل، نغلق Brave ونبدأ من جديد
        kill_brave()
        proc = start_brave_debug(port)
        if not wait_for_devtools(port):
            proc.terminate()
            raise RuntimeError(f"Brave Debug لم يجهز على المنفذ {port}")
        return make_driver_attached_to(port)


TITLE_SEL = [
    "h1[data-test-job-title]",
    ".job-details-jobs-unified-top-card__job-title",
    "h1.top-card-layout__title",
    "h1"
]

COMPANY_SEL = [
    "a[data-test-job-company-name]",
    ".job-details-jobs-unified-top-card__company-name a",
    ".topcard__org-name-link",
    ".topcard__flavor a"
]

DESC_SEL = [
    "div[data-test-description]",
    ".jobs-description__container",
    ".show-more-less-html__markup",
    "section.show-more-less-html"
]

SEE_MORE_SEL = [
    "button[aria-label*='See more']",
    "button[aria-label*='\u0639\u0631\u0636 \u0627\u0644\u0645\u0632\u064a\u062f']",
    "button.show-more-less-html__button",
    "button[aria-expanded='false']"
]

def first_or_none(drv, css_list):
    """Returns the first matching element for a list of CSS selectors."""
    for css in css_list:
        els = drv.find_elements(By.CSS_SELECTOR, css)
        if els:
            return els[0]
    return None

def click_see_more(drv):
    """Clicks 'See more' buttons to expand job descriptions."""
    seen = set()
    for _ in range(3):
        buttons = []
        for css in SEE_MORE_SEL:
            try:
                buttons.extend(drv.find_elements(By.CSS_SELECTOR, css))
            except Exception:
                continue

        buttons = [b for b in buttons if b and b not in seen]
        if not buttons:
            break

        for btn in buttons:
            try:
                drv.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                time.sleep(0.4)
                drv.execute_script("arguments[0].click();", btn)
                seen.add(btn)
                time.sleep(1.2)
            except Exception:
                continue

def extract_text(drv):
    """Extracts the job title, company, and description text."""
    title_el = first_or_none(drv, TITLE_SEL)
    company_el = first_or_none(drv, COMPANY_SEL)
    desc_el = first_or_none(drv, DESC_SEL)

    title = title_el.text.strip() if title_el else ""
    company = company_el.text.strip() if company_el else ""

    if desc_el:
        raw_html = drv.execute_script("return arguments[0].innerHTML;", desc_el)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")
        description = soup.get_text(separator="\n").strip()
    else:
        description = drv.find_element(By.TAG_NAME, "body").text.strip()

    parts = []
    if title:
        parts.append(f"# {title}")
    if company:
        parts.append(company)
    parts += ["", "---", "", description]
    return "\n".join(parts), (title or "linkedin-job")

def safe_name(name: str) -> str:
    """Generates a safe file name by replacing invalid characters."""
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip() or "linkedin-job"

def main():
    """Main execution function to extract LinkedIn job post data."""
    print("Running: app.py")
    print("[i] No need to open Brave manually; it will launch automatically.")
    url = input("Paste the LinkedIn job ad URL and press Enter: ").strip()
    if not url:
        print("! No URL entered")
        sys.exit(1)

    try:
        drv = boot_brave_and_driver()
    except FileNotFoundError:
        print("! Could not find Brave. Adjust BRAVE_PATH at the top of the file.")
        sys.exit(2)
    except Exception as e:
        print("! Failed to start/connect to Brave Debug automatically.\n> Details:", e)
        sys.exit(2)

    try:
        drv.get(url)
        WebDriverWait(drv, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.2)
        click_see_more(drv)
        text, base = extract_text(drv)
        fname = safe_name(base) + ".txt"
        Path(fname).write_text(text, encoding="utf-8")
        print(f"[✓] Text saved: {Path(fname).resolve()}")
        if pyperclip:
            try:
                pyperclip.copy(text)
                print("[✓] Text copied to clipboard.")
            except Exception:
                pass
    finally:
        pass

    input("\nDone. Press Enter to close...")

if __name__ == "__main__":
    main()

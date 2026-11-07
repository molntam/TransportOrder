import importlib.util
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from .sap import InputError
from .spotfire import PAGE_NAME, report_url


class SpotfireBrowser:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.lock = threading.RLock()
        self.thread = None
        self.status = {'state': 'idle', 'message': 'Spotfire is ready to start.', 'lastCheckedAt': None}
        self.workspace_url = None

    def snapshot(self):
        with self.lock:
            return dict(self.status)

    def update(self, state, message, **values):
        with self.lock:
            self.status.update(state=state, message=message, **values)

    def start(self, workspace_url=None):
        with self.lock:
            if self.thread and self.thread.is_alive():
                self.wake_event.set()
                return True
            if importlib.util.find_spec('playwright') is None:
                self.update('setup', 'Run setup_spotfire.bat once, then restart the app to connect Spotfire.')
                return False
            self.workspace_url = workspace_url
            self.thread = threading.Thread(target=self.run, daemon=True, name='Spotfire collector')
            self.thread.start()
            return True

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()

    def run(self):
        from playwright.sync_api import sync_playwright
        workspace_opened = False
        try:
            with sync_playwright() as playwright:
                settings = self.store.snapshot()['settings']
                context = playwright.chromium.launch_persistent_context(
                    str(self.store.directory / 'spotfire-browser-profile'),
                    channel=settings['spotfireBrowser'], headless=False, accept_downloads=True,
                    viewport=None, args=['--start-maximized'])
                try:
                    if self.workspace_url:
                        app_page = context.pages[0] if context.pages else context.new_page()
                        app_page.goto(self.workspace_url)
                        workspace_opened = True
                    page = context.new_page()
                    previous_url = None
                    while not self.stop_event.is_set():
                        settings = self.store.snapshot()['settings']
                        if not settings['spotfireEnabled'] or settings['dataSource'] != 'spotfire':
                            self.update('paused', 'Spotfire collection paused. Select Spotfire to resume.')
                            self.wake_event.wait(2)
                            self.wake_event.clear()
                            continue
                        if page.is_closed():
                            self.update('closed', 'Spotfire tab closed. Choose Open report to reconnect.')
                            if self.wake_event.wait(0.25):
                                self.wake_event.clear()
                                page = context.new_page()
                                previous_url = None
                            continue
                        try:
                            url = report_url(settings['spotfireUrl'])
                            self.update('collecting', 'Waiting for the report. Sign in in the Spotfire tab if prompted.')
                            if previous_url != url:
                                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                                previous_url = url
                            elif urlsplit(page.url).hostname == 'spotfire.asml.com':
                                page.reload(wait_until='domcontentloaded', timeout=30000)
                            if self.stop_event.is_set():
                                break
                            content = collect_export(page)
                            if not self.stop_event.is_set():
                                result = self.store.import_spotfire(content, automatic=True)
                                from ..domain import now
                                self.update('connected', f"Checked {result['uniqueHus']} HUs from {result['rowCount']} item rows.", lastCheckedAt=now())
                        except Exception:
                            self.update('attention', 'Waiting for sign-in or table export. Open Data Table Monitor and check Export table access. The last valid data remains loaded.')
                        deadline = time.monotonic() + 60
                        while not self.stop_event.is_set() and time.monotonic() < deadline:
                            if self.wake_event.is_set():
                                self.wake_event.clear()
                                break
                            page.wait_for_timeout(250)
                finally:
                    context.close()
        except Exception:
            if self.workspace_url and not workspace_opened:
                import webbrowser
                webbrowser.open(self.workspace_url)
            self.update('setup', 'Could not start the Spotfire browser. Check Edge/Chrome availability and browser automation policy, then choose Open report again.')


def collect_export(page):
    page.set_default_timeout(12000)
    deadline = time.monotonic() + 30
    selected = None
    while selected is None and time.monotonic() < deadline:
        for frame in page.frames:
            if urlsplit(frame.url).hostname != 'spotfire.asml.com':
                continue
            tab = frame.get_by_role('tab', name=PAGE_NAME, exact=True)
            if tab.count() == 0:
                tab = frame.get_by_text(PAGE_NAME, exact=True)
            if tab.count() == 1 and tab.is_visible():
                tab.click()
                selected = frame
                break
        if selected is None:
            page.wait_for_timeout(250)
    if selected is None:
        raise InputError('Sign in and open Data Table Monitor in the Spotfire tab.')
    header = selected.get_by_text(re.compile(r'^Handling[ _]unit$', re.I))
    header.first.wait_for(state='visible')
    grid = selected.get_by_role('grid').filter(has=header)
    if grid.count() != 1:
        grid = selected.locator('table').filter(has=header)
    if grid.count() != 1:
        grid = selected.locator('[class*="sfc-visual-content"]').filter(has=header)
    if grid.count() != 1:
        raise InputError('Choose the Data Table Monitor table containing Handling unit.')
    with page.expect_download(timeout=30000) as downloaded:
        grid.click(button='right')
        export_table = selected.get_by_text('Export table (without value formatting)', exact=True)
        export_menu = selected.get_by_role('menuitem', name='Export', exact=True)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if export_table.count() == 1 and export_table.is_visible():
                break
            if export_menu.count() == 1 and export_menu.is_visible():
                export_menu.hover()
            page.wait_for_timeout(100)
        if export_table.count() == 1 and export_table.is_visible():
            export_table.click()
        else:
            selected.get_by_text('Export table', exact=True).click()
    download = downloaded.value
    if download.failure():
        raise InputError('Spotfire export download failed.')
    path = Path(download.path())
    try:
        if path.stat().st_size > 20_000_000:
            raise InputError('Spotfire export exceeds 20 MB.')
        return path.read_bytes()
    finally:
        download.delete()

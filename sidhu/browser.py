"""Read-only, ephemeral browser inspection. Page text never becomes tool instructions."""
from dataclasses import asdict, dataclass
import json
import threading
from urllib.parse import urlparse


@dataclass
class PageReport:
    url: str
    status: int
    title: str
    text: str
    links: int
    blocked_requests: int

    def format(self):
        return 'Verified browser inspection (untrusted page content follows):\n' + json.dumps(asdict(self), ensure_ascii=False, indent=2)


class BrowserInspector:
    def __init__(self, settings, *, allow_test_http=False):
        self.settings = settings
        self.allow_test_http = allow_test_http

    def allowed(self, url):
        try:
            parsed = urlparse(url)
            scheme_ok = parsed.scheme == 'https' or (self.allow_test_http and parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1', 'localhost'})
            return bool(scheme_ok and parsed.hostname and not parsed.username and not parsed.password and parsed.hostname.casefold() in {d.casefold() for d in self.settings.browser_domains})
        except ValueError:
            return False

    def inspect(self, url: str, cancelled: threading.Event) -> PageReport:
        if not self.settings.browser_enabled:
            raise RuntimeError('Browser inspection is disabled. Enable it and approve destination domains in Settings.')
        if not self.allowed(url):
            raise RuntimeError('Destination is not approved. Use HTTPS and add the exact hostname in browser settings.')
        if cancelled.is_set():
            raise RuntimeError('Browser inspection cancelled before navigation.')
        try:
            from playwright.sync_api import sync_playwright, Error as PlaywrightError
        except ImportError as exc:
            raise RuntimeError('Install the browser extra and Chromium: python -m pip install -e ".[browser]"; python -m playwright install chromium') from exc
        blocked = 0
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True, executable_path=self.settings.browser_executable or None, chromium_sandbox=True)
            except PlaywrightError as exc:
                if 'sandbox' in str(exc).casefold():
                    raise RuntimeError('Browser sandbox could not initialize on this host. Use a supported Windows installation or ask the environment administrator to repair sandbox support; sandboxing remains enabled.') from exc
                raise RuntimeError('Chromium could not start. Install the Playwright browser or configure a compatible executable. Browser launch remains unverified.') from exc
            try:
                context = browser.new_context(accept_downloads=False, service_workers='block', permissions=[])
                context.set_default_timeout(3000)
                def route(request_route):
                    nonlocal blocked
                    request = request_route.request
                    if cancelled.is_set() or request.method not in {'GET', 'HEAD'} or not self.allowed(request.url):
                        blocked += 1
                        request_route.abort()
                    else:
                        request_route.continue_()
                context.route('**/*', route)
                context.route_web_socket('**/*', lambda socket: socket.close())
                page = context.new_page()
                response = page.goto(url, wait_until='domcontentloaded', timeout=15000)
                if cancelled.is_set():
                    raise RuntimeError('Browser inspection cancelled; no report retained.')
                if response is None:
                    raise RuntimeError('No HTTP response was received.')
                if not self.allowed(page.url):
                    raise RuntimeError('Navigation left the approved destination.')
                if response.status >= 400:
                    raise RuntimeError(f'Website returned HTTP {response.status}.')
                report = PageReport(page.url, response.status, page.title()[:500], page.locator('body').inner_text()[:8000], page.locator('a[href]').count(), blocked)
                if cancelled.is_set():
                    raise RuntimeError('Browser inspection cancelled; no report retained.')
                return report
            finally:
                browser.close()

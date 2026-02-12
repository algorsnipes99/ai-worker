import socket
import ipaddress
import re
from typing import Dict, Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from functions.function import Function


class WebsiteLookupRenderedFunction(Function):
    """Renders a webpage (incl. JS) and returns visible text (token-friendly)."""

    def __init__(self):
        super().__init__(
            name="lookupWebsiteRendered",
            description="Renders a website with a headless browser (JS enabled) and returns extracted visible text (not HTML).",
            parameters={
                "url": {"type": "string", "description": "HTTP(S) URL to fetch"},
                "timeout_seconds": {
                    "type": "number",
                    "default": 30,
                    "description": "Overall navigation timeout"
                },
                "max_chars": {
                    "type": "integer",
                    "default": 12000,
                    "description": "Max characters of extracted text to return"
                },
                "wait_ms": {
                    "type": "integer",
                    "default": 1000,
                    "description": "Extra time to wait after navigation for JS-rendered content (milliseconds)"
                },
                "protect_private_network": {
                    "type": "boolean",
                    "default": True,
                    "description": "Block localhost/private/reserved IPs (SSRF protection)"
                }
            }
        )

    def _is_private_host(self, hostname: str) -> bool:
        """Resolve hostname and check if it points to private/local/reserved IP space."""
        try:
            infos = socket.getaddrinfo(hostname, None)
            for info in infos:
                ip_str = info[4][0]
                ip = ipaddress.ip_address(ip_str)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                    or ip.is_multicast
                ):
                    return True
            return False
        except Exception:
            # fail-closed when protection is on
            return True

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r", "\n")
        text = re.sub(r"[ \t\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
        return text.strip()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        url = args.get("url")
        if not url or not isinstance(url, str):
            return {"error": "Invalid url parameter"}

        timeout_seconds = args.get("timeout_seconds", 30)
        max_chars = args.get("max_chars", 12000)
        wait_ms = args.get("wait_ms", 1000)
        protect_private_network = args.get("protect_private_network", True)

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"error": "Only http:// and https:// URLs are supported"}
        if not parsed.hostname:
            return {"error": "URL must include a hostname"}

        if protect_private_network and self._is_private_host(parsed.hostname):
            return {"error": "Blocked: hostname resolves to private/local/reserved IP space"}

        timeout_ms = int(float(timeout_seconds) * 1000)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                # Navigate and wait for the DOM; then pause briefly for JS content
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_ms and wait_ms > 0:
                    page.wait_for_timeout(int(wait_ms))

                # Extract token-friendly text (no HTML)
                title = ""
                try:
                    title = page.title() or ""
                except Exception:
                    title = ""

                # This is usually the best "what a user can select/copy" text signal
                raw_text = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
                text = self._normalize_text(raw_text)

                truncated = False
                if len(text) > int(max_chars):
                    text = text[: int(max_chars)]
                    truncated = True

                status = None
                if response is not None:
                    try:
                        status = response.status
                    except Exception:
                        status = None

                final_url = page.url

                context.close()
                browser.close()

                return {
                    "status_code": status,
                    "ok": (status is not None and 200 <= status < 400),
                    "final_url": final_url,
                    "title": title.strip(),
                    "truncated_chars": truncated,
                    "text": text,
                }

        except PlaywrightTimeoutError:
            return {"error": "Navigation/render timed out"}
        except Exception as e:
            return {"error": f"Render request failed: {str(e)}"}

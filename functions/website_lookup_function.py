import json
import socket
import ipaddress
import re
from html.parser import HTMLParser
from html import unescape
from typing import Dict, Any, Optional
from urllib.parse import urlparse

import requests
from functions.function import Function


class _HTMLTextExtractor(HTMLParser):
    """
    Lightweight visible-text extractor:
    - ignores <script>, <style>, <noscript>, <svg>, <canvas>
    - collapses whitespace
    """
    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}
    BLOCK_TAGS = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"}

    # Initialize parser state: skip-depth counter, text chunks, and title accumulator.
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks = []
        self._in_title = False
        self.title = ""

    # Track entry into skip tags (script, style, etc.) and insert newlines for block elements.
    # @param tag: Lowercase HTML tag name.
    # @param attrs: List of (name, value) attribute tuples.
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    # Track exit from skip tags and insert newlines for block element closes.
    # @param tag: Lowercase HTML tag name.
    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if self._skip_depth == 0 and tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    # Accumulate visible text, routing <title> content to self.title.
    # @param data: Raw text data from the parser.
    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if not data:
            return
        text = unescape(data)
        if self._in_title:
            self.title += text.strip()
        self._chunks.append(text)

    # Join accumulated chunks and normalize whitespace into clean readable text.
    # @returns: Cleaned visible text string.
    def get_text(self) -> str:
        raw = "".join(self._chunks)
        # normalize whitespace, keep paragraph breaks
        raw = raw.replace("\r", "\n")
        raw = re.sub(r"[ \t\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)  # collapse many blank lines
        return raw.strip()


class WebsiteLookupFunction(Function):
    """Fetches a website and returns extracted visible text (not full HTML)."""

    # Register the lookupWebsite tool with its parameter schema.
    def __init__(self):
        super().__init__(
            name="lookupWebsite",
            description="Fetch a website URL via HTTP(S) GET and return status + extracted visible text (token-friendly).",
            parameters={
                "url": {"type": "string", "description": "HTTP(S) URL to fetch"},
                "timeout_seconds": {"type": "number", "default": 15, "description": "Request timeout in seconds"},
                "follow_redirects": {"type": "boolean", "default": True, "description": "Follow HTTP redirects"},
                "max_bytes": {"type": "integer", "default": 300000, "description": "Max response bytes to read"},
                "max_chars": {"type": "integer", "default": 12000, "description": "Max characters of extracted text to return"},
                "protect_private_network": {
                    "type": "boolean",
                    "default": True,
                    "description": "Block localhost/private/reserved IPs (SSRF protection)"
                },
                "headers": {"type": "object", "description": "Optional additional HTTP headers (e.g., Authorization)"}
            }
        )

    # Resolve the hostname and check whether any of its IPs are private/local/reserved.
    # Fails closed (returns True) if DNS resolution fails, to avoid SSRF.
    # @param hostname: Hostname string to resolve.
    # @returns: True if the host is considered private/unsafe, False otherwise.
    def _is_private_host(self, hostname: str) -> bool:
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
            return True  # fail-closed when protection is on

    # Fetch the URL, extract visible text (or compact JSON), and return it with metadata.
    # Streams response up to max_bytes to avoid memory issues with large pages.
    # @param args: Dict with 'url', optional 'timeout_seconds', 'follow_redirects',
    #              'max_bytes', 'max_chars', 'protect_private_network', 'headers'.
    # @returns: Dict with 'status_code', 'ok', 'final_url', 'content_type', 'title',
    #           'bytes_read', 'truncated_bytes', 'truncated_chars', 'text', or 'error'.
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        url = args.get("url")
        if not url or not isinstance(url, str):
            return {"error": "Invalid url parameter"}

        timeout_seconds = args.get("timeout_seconds", 15)
        follow_redirects = args.get("follow_redirects", True)
        max_bytes = args.get("max_bytes", 300000)
        max_chars = args.get("max_chars", 12000)
        protect_private_network = args.get("protect_private_network", True)
        extra_headers = args.get("headers") or {}

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"error": "Only http:// and https:// URLs are supported"}
        if not parsed.hostname:
            return {"error": "URL must include a hostname"}

        if protect_private_network and self._is_private_host(parsed.hostname):
            return {"error": "Blocked: hostname resolves to private/local/reserved IP space"}

        headers = {
            "User-Agent": "WebsiteLookupFunction/1.0",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            **(extra_headers if isinstance(extra_headers, dict) else {})
        }

        try:
            with requests.get(
                url,
                headers=headers,
                timeout=timeout_seconds,
                allow_redirects=follow_redirects,
                stream=True
            ) as r:
                chunks = []
                total = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        break

                raw = b"".join(chunks)
                truncated_bytes = total > max_bytes

                content_type = (r.headers.get("Content-Type") or "").lower()

                # decode text best-effort
                encoding = r.encoding or "utf-8"
                html = raw.decode(encoding, errors="replace")

                title = ""
                extracted_text = ""

                # If JSON, return a compact text form (still token-friendly)
                if "application/json" in content_type:
                    try:
                        obj = json.loads(html)
                        extracted_text = json.dumps(obj, ensure_ascii=False, indent=2)
                    except Exception:
                        extracted_text = html
                else:
                    parser = _HTMLTextExtractor()
                    parser.feed(html)
                    title = parser.title.strip()
                    extracted_text = parser.get_text()

                # hard cap output
                truncated_chars = False
                if isinstance(extracted_text, str) and len(extracted_text) > max_chars:
                    extracted_text = extracted_text[:max_chars]
                    truncated_chars = True

                return {
                    "status_code": r.status_code,
                    "ok": r.ok,
                    "final_url": str(r.url),
                    "content_type": content_type,
                    "title": title,
                    "bytes_read": len(raw),
                    "truncated_bytes": truncated_bytes,
                    "truncated_chars": truncated_chars,
                    "text": extracted_text,
                }

        except requests.exceptions.Timeout:
            return {"error": "Request timed out"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}

"""Pure HTML-parsing helpers.

These functions have no I/O so they can be unit-tested with fixture strings
shaped like the pages phpRedisAdmin emits.
"""

from __future__ import annotations

import html as html_mod
import re
from dataclasses import dataclass
from urllib.parse import unquote

# Key links in the index.php sidebar look like:
#   <a href="?view&amp;s=0&amp;d=0&amp;key=urlencoded...">name</a>
_KEY_HREF_RE = re.compile(r'[?&;]key=([^"&#]+)')

_SERVER_SELECT_RE = re.compile(r'<select id="server">(.*?)</select>', re.S)
# <option value="0" selected="selected">localhost:6379</option>
_OPTION_RE = re.compile(r'<option value="(\d+)"([^>]*)>([^<]+)</option>')

_CSRF_RE = re.compile(r'name="csrf"\s+value="([^"]+)"')


@dataclass(frozen=True)
class ServerOption:
    value: str
    selected: bool
    name: str


def extract_csrf(html: str) -> str | None:
    """Return the csrf token embedded in a page, or None if absent."""
    m = _CSRF_RE.search(html)
    return m.group(1) if m else None


def extract_keys(html: str) -> list[str]:
    """Pull key names out of an index.php page (sidebar hrefs), deduplicated."""
    keys = set()
    for m in _KEY_HREF_RE.finditer(html):
        keys.add(unquote(m.group(1)))
    return sorted(keys)


def find_server_select(html: str) -> str | None:
    """Return the inner HTML of the server <select>, or None if not found."""
    m = _SERVER_SELECT_RE.search(html)
    return m.group(1) if m else None


def parse_server_options(select_html: str) -> list[ServerOption]:
    """Parse the <option> entries of the server selector."""
    out = []
    for m in _OPTION_RE.finditer(select_html):
        value, attrs, name = m.group(1), m.group(2), m.group(3)
        out.append(
            ServerOption(
                value=value,
                selected="selected" in attrs,
                name=html_mod.unescape(name).strip(),
            )
        )
    return out


def strip_html(text: str) -> str:
    """Drop script/style blocks and tags, unescape entities, squeeze spaces."""
    text = re.sub(r"<script.*?</script>", "", text, flags=re.S)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t]+", " ", html_mod.unescape(text)).strip()

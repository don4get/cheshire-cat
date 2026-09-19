"""Small rotating proxy pool for Yahoo requests.

Public proxy lists are unreliable and should only be used for low-volume,
non-sensitive research. The pool validates no traffic beyond choosing and
retiring endpoints; production deployments should supply owned proxies.
"""

from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from html.parser import HTMLParser

import requests

DEFAULT_PROXY_SOURCE = "https://free-proxy-list.net/"


@dataclass
class ProxyPool:
    proxies: list[str] = field(default_factory=list)
    _cursor: itertools.cycle[str] | None = field(default=None, init=False, repr=False)
    _failures: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    max_failures: int = 2

    def __post_init__(self) -> None:
        self.proxies = list(dict.fromkeys(_normalise_proxy(proxy) for proxy in self.proxies if proxy))
        self._cursor = itertools.cycle(self.proxies) if self.proxies else None

    @classmethod
    def from_free_proxy_list(
        cls,
        source_url: str = DEFAULT_PROXY_SOURCE,
        session: requests.Session | None = None,
        allowed_countries: set[str] | None = None,
    ) -> ProxyPool:
        return cls(get_proxies(source_url, session, allowed_countries))

    def next(self) -> str | None:
        """Return the next endpoint that has not exceeded its failure budget."""

        with self._lock:
            if self._cursor is None or not self.proxies:
                return None
            for _ in range(len(self.proxies)):
                proxy = next(self._cursor)
                if self._failures.get(proxy, 0) < self.max_failures:
                    return proxy
            return None

    def mark_success(self, proxy: str | None) -> None:
        if proxy:
            with self._lock:
                self._failures.pop(proxy, None)

    def mark_failure(self, proxy: str | None) -> None:
        if proxy:
            with self._lock:
                self._failures[proxy] = self._failures.get(proxy, 0) + 1

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


def get_proxies(
    url: str = DEFAULT_PROXY_SOURCE,
    session: requests.Session | None = None,
    allowed_countries: set[str] | None = None,
) -> list[str]:
    """Fetch HTTPS proxies from an HTML table."""

    session = session or requests.Session()
    session.headers.update(
        {"User-Agent": "cheshire-cat/0.1 research client", "Accept": "text/html, */*"}
    )
    response = session.get(url, timeout=30)
    response.raise_for_status()
    parser = _ProxyTableParser()
    parser.feed(response.text)
    return [
        f"{row['ip']}:{row['port']}"
        for row in parser.rows
        if row.get("https", "").lower() == "yes"
        and (allowed_countries is None or row.get("country", "") in allowed_countries)
    ]


class _ProxyTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._cells: list[str] = []
        self._text: list[str] = []
        self._in_row = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._in_row = True
            self._cells = []
        elif tag == "td" and self._in_row:
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._in_row:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_row:
            self._cells.append("".join(self._text).strip())
            self._text = []
        elif tag == "tr" and self._in_row:
            if len(self._cells) >= 7 and self._cells[0].lower() != "ip address":
                self.rows.append(
                    {
                        "ip": self._cells[0],
                        "port": self._cells[1],
                        "country": self._cells[2],
                        "https": self._cells[6],
                    }
                )
            self._in_row = False


def _normalise_proxy(proxy: str) -> str:
    return proxy if "://" in proxy else f"http://{proxy}"

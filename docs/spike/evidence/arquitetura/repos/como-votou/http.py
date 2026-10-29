"""Polite HTTP downloader with an on-disk cache under data/raw/."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import config


@dataclass(frozen=True)
class Fetched:
    url: str
    path: Path
    accessed_at: str
    sha256: str
    from_cache: bool

    def text(self, encoding: str = "utf-8") -> str:
        return self.path.read_bytes().decode(encoding, errors="replace")

    def json(self) -> dict:
        return json.loads(self.path.read_bytes().decode("utf-8", errors="replace"))


class Downloader:
    """GET/POST with caching keyed on (method, url, body). One request per second."""

    def __init__(
        self, raw_dir: Path = config.RAW_DIR, delay_s: float = config.REQUEST_DELAY_S, offline: bool = False
    ) -> None:
        self.raw_dir = raw_dir
        self.delay_s = delay_s
        self.offline = offline  # True: never touch the network (cache misses raise)
        self.requests_made = 0
        self._last = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT},
            verify=str(config.CA_BUNDLE),
            timeout=config.TIMEOUT_S,
            follow_redirects=True,
        )
        self.sources: dict[str, Fetched] = {}

    def _key(self, method: str, url: str, data: dict[str, str] | None) -> Path:
        host = urlsplit(url).hostname or "unknown"
        raw = method + "\n" + url + "\n" + json.dumps(data or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha1(raw.encode()).hexdigest()[:20]
        return self.raw_dir / host / h

    def _throttle(self) -> None:
        wait = self.delay_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def fetch(self, url: str, *, data: dict[str, str] | None = None, refresh: bool = False) -> Fetched:
        method = "POST" if data is not None else "GET"
        base = self._key(method, url, data)
        body, meta = base.with_suffix(".body"), base.with_suffix(".json")
        cached = body.exists() and meta.exists()
        if cached and (not refresh or self.offline):
            m = json.loads(meta.read_text())
            f = Fetched(url, body, m["accessed_at"], m["sha256"], True)
        elif self.offline:
            raise FileNotFoundError(f"offline and not cached: {method} {url}")
        else:
            self._throttle()
            self.requests_made += 1
            r = self._client.post(url, data=data) if data is not None else self._client.get(url)
            r.raise_for_status()
            base.parent.mkdir(parents=True, exist_ok=True)
            body.write_bytes(r.content)
            accessed = datetime.now(timezone.utc).isoformat(timespec="seconds")
            sha = hashlib.sha256(r.content).hexdigest()
            meta.write_text(
                json.dumps(
                    {
                        "url": url,
                        "method": method,
                        "data": data,
                        "accessed_at": accessed,
                        "sha256": sha,
                        "status": r.status_code,
                        "content_type": r.headers.get("content-type"),
                    },
                    ensure_ascii=False,
                    indent=1,
                )
            )
            f = Fetched(url, body, accessed, sha, False)
        self.sources[f"{method} {url}"] = f
        return f

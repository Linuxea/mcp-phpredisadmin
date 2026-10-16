"""HTTP client for the phpRedisAdmin web UI.

Owns the requests session, auth, the csrf token, and the current
server/db selection. Previously these were module-level globals; they
live on the class now so tests can instantiate their own client.
"""

from __future__ import annotations

import re

import requests

from .config import Config
from .parsing import extract_csrf


class PraClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "mcp-phpredisadmin/1.0"
        self._csrf: str | None = None
        self.server_id = cfg.server_id
        self.db = cfg.db

    # -- request helpers -------------------------------------------------

    def qs(self) -> dict[str, str]:
        return {"s": self.server_id, "d": self.db}

    def get(self, path: str, params: dict | None = None, timeout: int = 30):
        return self.session.get(
            f"{self.cfg.url}/{path}", params=params or self.qs(), timeout=timeout
        )

    def post(self, path: str, params: dict | None = None, data: dict | None = None):
        data = dict(data or {})
        token = self.csrf_token()
        if token:
            data["csrf"] = token
        r = self.session.post(
            f"{self.cfg.url}/{path}",
            params=params or self.qs(),
            data=data,
            timeout=60,
        )
        r.raise_for_status()
        return r

    # -- auth & csrf ------------------------------------------------------

    def _login_form(self) -> None:
        r = self.session.post(
            f"{self.cfg.url}/login.php",
            data={"username": self.cfg.user, "password": self.cfg.password},
            timeout=15,
            allow_redirects=True,
        )
        if "login.php" in r.url and r.status_code == 200:
            if 'name="csrf"' not in r.text:
                raise RuntimeError("form login failed: still on login page")

    def ensure_auth_and_csrf(self) -> None:
        if self.cfg.user and self.cfg.login == "form":
            self._login_form()
        r = self.get("edit.php", timeout=15)
        if r.status_code == 401:
            raise RuntimeError(
                "HTTP auth failed (401). Check PRA_USER/PRA_PASS or set PRA_LOGIN=form."
            )
        if "login.php" in r.url and 'name="csrf"' not in r.text:
            raise RuntimeError(
                "login required: set PRA_USER/PRA_PASS and PRA_LOGIN=form"
            )
        self._csrf = extract_csrf(r.text) or ""

    def csrf_token(self) -> str:
        if self._csrf is None:
            self.ensure_auth_and_csrf()
        return self._csrf


_client: PraClient | None = None


def get_client() -> PraClient:
    """Lazily-created process-wide client (reads PRA_* env vars on first use)."""
    global _client
    if _client is None:
        _client = PraClient(Config.from_env())
    return _client


def reset_client() -> None:
    """Drop the cached client so the next get_client() re-reads the environment."""
    global _client
    _client = None

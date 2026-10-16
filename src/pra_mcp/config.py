"""Configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Everything the client needs to reach a phpRedisAdmin installation."""

    url: str  # base url, no trailing slash
    user: str
    password: str
    login: str  # "basic" (HTTP Basic or no auth) or "form" (login.php)
    server_id: str
    db: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            url=os.environ.get("PRA_URL", "").rstrip("/"),
            user=os.environ.get("PRA_USER", ""),
            password=os.environ.get("PRA_PASS", ""),
            login=os.environ.get("PRA_LOGIN", "basic"),
            server_id=os.environ.get("PRA_SERVER_ID", "0"),
            db=os.environ.get("PRA_DB", "0"),
        )

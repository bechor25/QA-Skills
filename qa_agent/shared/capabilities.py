"""Shared capability classification.

Single source of truth for the keyword → capability mapping used by:

  - `context.kg_builder` when bucketing API routes and UI pages into
    features.
  - `scanners.ui_selectors` when assigning each UI source file to the
    capabilities whose tests will reference its selectors.

Keeping the dictionary here avoids drift between the analyzer and the
scanner — when a project's KG knows that `/users` belongs to
`user-mgmt`, the selector scanner must agree, or ui scaffolds end up
pointing at the wrong capability.
"""

from __future__ import annotations


# Order matters only when two hits collide: the first match wins.
# Keep lowercase. Substrings, not regex.
CAPABILITY_HINTS: list[tuple[str, list[str]]] = [
    ("auth",        ["login", "logout", "signin", "signup", "register", "auth", "oauth", "session", "token", "mfa", "sso"]),
    ("payments",    ["payment", "charge", "invoice", "subscription", "checkout", "billing"]),
    ("permissions", ["permission", "role", "acl", "rbac", "grant", "revoke"]),
    ("user-mgmt",   ["user", "profile", "account"]),
    ("data-export", ["export", "download", "report"]),
    ("file-upload", ["upload", "attachment", "media"]),
    ("search",      ["search", "query", "find"]),
    ("admin",       ["admin", "internal", "ops"]),
    ("api-public",  ["api/v1", "api/v2", "public"]),
]


def classify_capability(hint_str: str) -> str:
    """Return the first matching capability, or "other".

    `hint_str` is a free-form string built from the file path, route
    pattern, or symbol name. Callers commonly concatenate path +
    route + handler when more signal is available.
    """
    lower = hint_str.lower()
    for cap, hints in CAPABILITY_HINTS:
        if any(h in lower for h in hints):
            return cap
    return "other"


def classify_capabilities(hint_str: str, limit: int = 3) -> list[str]:
    """Return up to `limit` matching capabilities for a hint string.

    Unlike `classify_capability`, this allows a file to belong to more
    than one capability bucket. Useful for UI source files that
    legitimately serve multiple features (e.g. a layout shared by
    `auth` and `user-mgmt` flows).
    """
    lower = hint_str.lower()
    out: list[str] = []
    for cap, hints in CAPABILITY_HINTS:
        if any(h in lower for h in hints):
            out.append(cap)
            if len(out) >= limit:
                break
    return out or ["other"]

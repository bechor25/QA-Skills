"""Deterministic capability clustering.

The hardcoded keyword classifier in `shared.capabilities` works for the
9-or-so canonical buckets it knows about (auth, admin, payments, …) but
everything else collapses into a single `other` capability. On any
real-world project that bucket grows large enough to crash a downstream
sub-agent (it ends up reading every uncategorized route file).

This module replaces the hardcoded classifier for clustering purposes
with a project-shaped one:

  * Walk the scanned API routes and group by URL path prefix (top one
    or two segments after `/api[/v<n>]`).
  * Walk the scanned UI pages and group by top-level directory under
    a known frontend root (`pages/`, `app/`, `routes/`, `features/`).
  * Optionally merge the two halves of the same capability (route
    cluster `candidates` ↔ UI cluster `candidates`).
  * Emit a `RawCapabilityMap` with `route_globs`, `ui_globs`,
    `sample_*`, `route_count`, `ui_count`, and a coarse `score_hint`.

The result feeds the strategy builder and gives the qa-enricher sub-
agent a concrete, bounded scope (`route_globs` + `ui_globs`) instead
of having it guess which files to read.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..scanners.api_scanner import ApiInventory, RouteEntry
from ..scanners.ui_scanner import UIInventory, UIPage
from ..shared.logging import get_logger
from ..state import schemas

log = get_logger("qa_agent.quality.capability_discovery")


# Path segments stripped before we look at "real" content. These tell
# us nothing about a capability — they are framework or version noise.
_API_PREFIX_NOISE = {"api", "v1", "v2", "v3", "v4", "internal", "rest", "graphql"}

# Frontend root names — the segment under which we look for "real"
# top-level page folders. A path like apps/web/src/pages/Candidates/X.tsx
# becomes capability `candidates`.
_UI_ROOT_HINTS = {"pages", "app", "routes", "features", "views", "screens", "modules"}

# Path-segment noise inside the frontend tree that should be peeled
# until we hit something meaningful.
_UI_DROP_SEGMENTS = {
    "apps", "src", "packages", "web", "client", "frontend", "ui",
    "components", "shared", "common", "lib", "hooks", "utils",
}

# Maximum number of capabilities to emit. Lots of one-off route prefixes
# can otherwise produce a long noisy tail.
_MAX_CAPABILITIES = 20

# Below this route count, the prefix is treated as noise and merged
# into the parent ("misc" cluster).
_MIN_ROUTES_FOR_CAPABILITY = 2

_PLURAL_RE = re.compile(r"(ies|es|s)$")


def discover_capabilities(
    project_root: Path,
    project_map: schemas.ProjectMap,
    api: ApiInventory,
    ui: UIInventory,
) -> schemas.RawCapabilityMap:
    """Cluster routes and pages, return a `RawCapabilityMap`."""
    route_clusters = _cluster_routes(api.routes)
    ui_clusters = _cluster_ui(ui.pages, project_map)

    merged_keys = sorted(set(route_clusters) | set(ui_clusters))
    capabilities: list[schemas.DiscoveredCapability] = []

    for key in merged_keys:
        routes = route_clusters.get(key, [])
        pages = ui_clusters.get(key, [])
        if len(routes) < _MIN_ROUTES_FOR_CAPABILITY and not pages:
            # Fold orphan single-route prefixes into a misc bucket.
            continue
        capabilities.append(_build_capability(key, routes, pages))

    # Anything that fell below the threshold lands in a single misc
    # bucket so the strategy builder still has the option to test it.
    orphans_routes: list[RouteEntry] = []
    for key, routes in route_clusters.items():
        if key not in {c.name for c in capabilities}:
            orphans_routes.extend(routes)
    if orphans_routes:
        capabilities.append(_build_capability("misc", orphans_routes, []))

    # Sort by score_hint desc and cap at _MAX_CAPABILITIES.
    capabilities.sort(key=lambda c: c.score_hint, reverse=True)
    capabilities = capabilities[:_MAX_CAPABILITIES]

    log.info(
        "capability_discovery: %d clusters from %d routes / %d pages",
        len(capabilities), len(api.routes), len(ui.pages),
    )
    return schemas.RawCapabilityMap(
        built_at=datetime.now(timezone.utc),
        capabilities=capabilities,
    )


# ---------------------------------------------------------------------
# Route clustering
# ---------------------------------------------------------------------

def _cluster_routes(routes: list[RouteEntry]) -> dict[str, list[RouteEntry]]:
    clusters: dict[str, list[RouteEntry]] = defaultdict(list)
    for r in routes:
        key = _route_capability_key(r.pattern)
        if not key:
            continue
        clusters[key].append(r)
    return clusters


def _route_capability_key(pattern: str) -> str | None:
    """Pull the most informative segment from a route pattern.

    Examples:
      /api/v1/candidates/{id}/applications → candidates
      /api/auth/login                        → auth
      /health/ready                          → health
      /                                      → None
    """
    segs = [s for s in pattern.strip("/").split("/") if s]
    # Walk past the noise prefixes (api, v1, …) until we hit something
    # informative — but never further than 3 hops.
    informative: str | None = None
    for seg in segs[:4]:
        clean = seg.split("?", 1)[0].split(":", 1)[0]
        clean = clean.replace("{", "").replace("}", "").lower()
        if not clean or clean in _API_PREFIX_NOISE:
            continue
        informative = _normalize_capability_name(clean)
        break
    return informative


def _normalize_capability_name(raw: str) -> str:
    """Light normalization: lowercase, dashes for separators."""
    name = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return name


# ---------------------------------------------------------------------
# UI clustering
# ---------------------------------------------------------------------

def _cluster_ui(
    pages: list[UIPage],
    project_map: schemas.ProjectMap,
) -> dict[str, list[UIPage]]:
    clusters: dict[str, list[UIPage]] = defaultdict(list)

    # Index pages by source_path for cheap lookups.
    for p in pages:
        key = _ui_capability_key(p.source_path) or _ui_capability_key(p.route)
        if not key:
            continue
        clusters[key].append(p)

    # Also walk UI source files in project_map that the scanner did not
    # promote to a UIPage (e.g. modal/widget components). Those don't
    # form their own capabilities but reinforce existing ones.
    for entry in project_map.files:
        if entry.is_test:
            continue
        if not any(entry.path.endswith(ext) for ext in (".tsx", ".jsx", ".vue", ".svelte")):
            continue
        key = _ui_capability_key(entry.path)
        if not key or key not in clusters:
            continue
        # Reinforce: register the file under the existing cluster as a
        # synthetic page entry so downstream globs see it.
        clusters[key].append(UIPage(
            framework="component", route=key, source_path=entry.path,
        ))
    return clusters


def _ui_capability_key(path_or_route: str) -> str | None:
    """Pull the first directory under a frontend root as the cluster.

    Falls back to the filename stem if no recognized root is found.
    """
    parts = [s for s in path_or_route.replace("\\", "/").split("/") if s]
    # Find a frontend root (pages/app/features/routes) and take the
    # segment right after it.
    for i, seg in enumerate(parts):
        if seg.lower() in _UI_ROOT_HINTS and i + 1 < len(parts):
            candidate = parts[i + 1]
            stem = _stem(candidate)
            if stem.lower() in _UI_DROP_SEGMENTS:
                continue
            return _normalize_capability_name(stem)
    # No frontend root in path → strip extension from filename.
    last = parts[-1] if parts else ""
    stem = _stem(last)
    if not stem or stem.lower() in _UI_DROP_SEGMENTS:
        return None
    return _normalize_capability_name(stem)


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0]


# ---------------------------------------------------------------------
# Build DiscoveredCapability
# ---------------------------------------------------------------------

def _build_capability(
    name: str,
    routes: list[RouteEntry],
    pages: list[UIPage],
) -> schemas.DiscoveredCapability:
    route_files = sorted({r.module_path for r in routes if r.module_path})
    ui_files = sorted({p.source_path for p in pages if p.source_path})

    return schemas.DiscoveredCapability(
        name=name,
        summary=_summarize(name, routes, pages),
        route_globs=_compress_to_globs(route_files),
        ui_globs=_compress_to_globs(ui_files),
        route_count=len(routes),
        ui_count=len(pages),
        sample_routes=sorted({_method_path(r) for r in routes})[:8],
        sample_ui_files=ui_files[:8],
        score_hint=_score_hint(routes, pages),
    )


def _summarize(name: str, routes: list[RouteEntry], pages: list[UIPage]) -> str:
    bits: list[str] = []
    if routes:
        bits.append(f"{len(routes)} routes")
    if pages:
        bits.append(f"{len(pages)} ui files")
    return f"{name}: " + ", ".join(bits) if bits else name


def _method_path(r: RouteEntry) -> str:
    return f"{r.method} {r.pattern}".strip()


def _score_hint(routes: list[RouteEntry], pages: list[UIPage]) -> float:
    # Coarse: routes weigh more than pages because backend bugs tend to
    # carry higher business impact. Cap so a single huge cluster does
    # not dominate the strategy ordering.
    return min(50.0, 2.0 * len(routes) + 1.0 * len(pages))


def _compress_to_globs(files: list[str]) -> list[str]:
    """Collapse a flat file list into directory + filename-prefix globs.

    Strategy:
      * Group by (dir, ext).
      * Within each group, find a shared filename prefix; if it covers
        all members, emit `<dir>/<prefix>*.<ext>`.
      * Otherwise keep the literal paths so we never widen the glob to
        unrelated capabilities (e.g. emit two patterns rather than
        `<dir>/*.ts`).
    """
    by_dir_ext: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in files:
        if "/" in f:
            d, name = f.rsplit("/", 1)
        else:
            d, name = "", f
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
        by_dir_ext[(d, ext)].append(f)

    out: list[str] = []
    for (d, ext), members in sorted(by_dir_ext.items()):
        if len(members) == 1 or not ext:
            out.extend(sorted(members))
            continue
        stems = [m.rsplit("/", 1)[-1].rsplit(".", 1)[0] for m in members]
        prefix = _common_prefix(stems)
        if prefix and len(prefix) >= 3:
            out.append(f"{d}/{prefix}*.{ext}" if d else f"{prefix}*.{ext}")
        else:
            out.extend(sorted(members))
    return out


def _common_prefix(stems: list[str]) -> str:
    """Return the shared leading substring across all stems, lowercased.

    Stops at the first non-alphanumeric mismatch so we never emit a
    glob that crosses naming boundaries (e.g. `candidate*` is fine,
    but `cand*` is too aggressive when stems are `candidates`,
    `candidate-files`, `candle-X`).
    """
    if not stems:
        return ""
    s0 = stems[0]
    cutoff = len(s0)
    for s in stems[1:]:
        n = min(cutoff, len(s))
        i = 0
        while i < n and s0[i].lower() == s[i].lower():
            i += 1
        cutoff = i
        if cutoff == 0:
            break
    prefix = s0[:cutoff]
    # Trim trailing non-alphanumeric so we never emit `candidate-*`
    # when the union of files starts diverging at that hyphen.
    while prefix and not prefix[-1].isalnum():
        prefix = prefix[:-1]
    return prefix.lower()

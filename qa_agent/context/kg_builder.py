"""Knowledge Graph builder.

Composes project → module → feature → symbol from the scanner outputs.
A "feature" is a capability cluster (auth, payments, search…) derived
from naming heuristics on the route/symbol inventories. The KG is the
input the risk engine reasons over.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..scanners.api_scanner import ApiInventory, RouteEntry
from ..scanners.ui_scanner import UIInventory
from ..shared.logging import get_logger
from ..state import schemas
from .summarizer import summarize_modules, summarize_project

log = get_logger("qa_agent.context.kg_builder")


# Naming heuristics — substrings in route paths or handler names map to
# a capability. Keep lowercase. Order matters only when two hits collide:
# the first wins.
_CAPABILITY_HINTS: list[tuple[str, list[str]]] = [
    ("auth",       ["login", "logout", "signin", "signup", "register", "auth", "oauth", "session", "token"]),
    ("payments",   ["payment", "charge", "invoice", "subscription", "checkout", "billing"]),
    ("permissions",["permission", "role", "acl", "rbac", "grant", "revoke"]),
    ("user-mgmt",  ["user", "profile", "account"]),
    ("data-export",["export", "download", "report"]),
    ("file-upload",["upload", "attachment", "media"]),
    ("search",     ["search", "query", "find"]),
    ("admin",      ["admin", "internal", "ops"]),
    ("api-public", ["api/v1", "api/v2", "public"]),
]


def build_knowledge_graph(
    pm: schemas.ProjectMap,
    dep: schemas.DependencyGraph,
    api: ApiInventory,
    ui: UIInventory,
) -> schemas.KnowledgeGraph:
    project_summary = summarize_project(pm, dep)
    modules = summarize_modules(pm, dep)
    features = _build_features(api, ui, modules)

    # Wire module → feature membership
    module_index = {m.id: m for m in modules}
    for feat in features:
        for mid in feat.module_ids:
            mod = module_index.get(mid)
            if mod and feat.id not in mod.features:
                mod.features.append(feat.id)

    log.info(
        "kg: %d modules, %d features", len(modules), len(features),
    )
    return schemas.KnowledgeGraph(
        built_at=datetime.now(timezone.utc),
        project_summary=project_summary,
        modules=modules,
        features=features,
    )


def _build_features(
    api: ApiInventory,
    ui: UIInventory,
    modules: list[schemas.ModuleSummary],
) -> list[schemas.FeatureEntry]:
    bucket: dict[str, dict] = {}

    def _push(cap: str, name: str, module_id: str, sym: schemas.SymbolEntry) -> None:
        entry = bucket.setdefault(cap, {"name": name, "modules": set(), "symbols": []})
        entry["modules"].add(module_id)
        entry["symbols"].append(sym)

    for r in api.routes:
        cap = _classify_capability(f"{r.pattern} {r.handler}")
        sym = schemas.SymbolEntry(
            name=f"{r.method} {r.pattern} -> {r.handler}",
            kind="route",
            path=r.module_path,
            line=r.line,
        )
        _push(cap, _humanize(cap), _top_dir(r.module_path), sym)

    for p in ui.pages:
        cap = _classify_capability(p.route)
        sym = schemas.SymbolEntry(
            name=f"{p.framework} page {p.route}",
            kind="component",
            path=p.source_path,
        )
        _push(cap, _humanize(cap), _top_dir(p.source_path), sym)

    out: list[schemas.FeatureEntry] = []
    for cap, blob in bucket.items():
        out.append(
            schemas.FeatureEntry(
                id=f"feat::{cap}",
                name=blob["name"],
                summary=f"{blob['name']} surface: {len(blob['symbols'])} routes/pages.",
                module_ids=sorted(blob["modules"]),
                symbols=blob["symbols"],
                capabilities=[cap],
            )
        )
    return out


def _classify_capability(hint_str: str) -> str:
    lower = hint_str.lower()
    for cap, hints in _CAPABILITY_HINTS:
        if any(h in lower for h in hints):
            return cap
    return "other"


def _humanize(cap: str) -> str:
    return cap.replace("-", " ").title()


def _top_dir(path: str) -> str:
    return path.split("/", 1)[0] or "."

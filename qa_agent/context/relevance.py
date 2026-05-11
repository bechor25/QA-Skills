"""Relevance engine.

Given a feature/capability/query, return ranked module IDs from the
knowledge graph. Used to scope LLM prompts (Phases 2-3) and to scope
incremental reruns (Phase 5) to the modules that matter.
"""

from __future__ import annotations

from collections import Counter

from ..state import schemas


def relevant_modules(
    kg: schemas.KnowledgeGraph,
    feature_id: str | None = None,
    capability: str | None = None,
    keywords: list[str] | None = None,
    top_n: int = 10,
) -> list[str]:
    """Return ranked module IDs relevant to the query.

    Ranking signals (added together):
      1. module appears in the matching feature's `module_ids` (+10)
      2. module's summary contains any keyword (+1 per hit)
      3. module's listed features include the capability (+5)
    """
    scores: Counter[str] = Counter()

    matched_feature: schemas.FeatureEntry | None = None
    if feature_id:
        matched_feature = next((f for f in kg.features if f.id == feature_id), None)
    elif capability:
        matched_feature = next((f for f in kg.features if capability in f.capabilities), None)

    if matched_feature:
        for mid in matched_feature.module_ids:
            scores[mid] += 10

    if capability:
        for m in kg.modules:
            if capability in m.features:
                scores[m.id] += 5

    if keywords:
        kws = [k.lower() for k in keywords if k]
        for m in kg.modules:
            summary = m.summary.lower()
            scores[m.id] += sum(1 for k in kws if k in summary)

    return [mid for mid, _ in scores.most_common(top_n)]

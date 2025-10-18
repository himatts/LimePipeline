"""
Material name quality evaluation utilities.

Provides heuristics to score how well an existing material name preserves
taxonomy semantics and conforms to Lime Pipeline conventions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .material_naming import PREFIX, parse_name, strip_numeric_suffix
from .material_taxonomy import (
    get_allowed_material_types,
    get_finish_synonyms,
    get_taxonomy_context,
)
from .material_reconciliation import (
    find_closest_type_match as _recon_find_closest_type_match,
    find_closest_finish_match as _recon_find_closest_finish_match,
    similarity_score,
)


QUALITY_LABELS = ("invalid", "poor", "fair", "good", "excellent")


@dataclass(frozen=True)
class MaterialQualityResult:
    """Structured result describing quality assessment for a material name."""

    score: float
    label: str
    issues: List[str]
    parsed: Optional[Dict[str, object]]
    type_similarity: float
    finish_similarity: float
    hint_similarity: float
    finish_hint_similarity: float
    taxonomy_match: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "score": self.score,
            "label": self.label,
            "issues": list(self.issues),
            "parsed": dict(self.parsed) if self.parsed else None,
            "type_similarity": self.type_similarity,
            "finish_similarity": self.finish_similarity,
            "hint_similarity": self.hint_similarity,
            "finish_hint_similarity": self.finish_hint_similarity,
            "taxonomy_match": self.taxonomy_match,
        }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def evaluate_material_name(
    name: str,
    *,
    texture_basenames: Optional[Iterable[str]] = None,
    object_hints: Optional[Iterable[str]] = None,
    collection_hints: Optional[Iterable[str]] = None,
    principled: Optional[Dict[str, float]] = None,
    taxonomy_context: Optional[Dict[str, object]] = None,
) -> MaterialQualityResult:
    """
    Evaluate how well an existing material name aligns with taxonomy hints.

    Returns:
        MaterialQualityResult with a normalized score (0�?"1) and qualitative label.
    """
    sanitized = strip_numeric_suffix(name or "")
    issues: List[str] = []

    parsed = parse_name(sanitized)
    if not parsed:
        issues.append("Name does not match expected MAT_* schema")
        if not sanitized.startswith(PREFIX + "_"):
            issues.append("Missing MAT_ prefix")
        return MaterialQualityResult(
            score=0.0,
            label="invalid",
            issues=issues,
            parsed=None,
            type_similarity=0.0,
            finish_similarity=0.0,
            hint_similarity=0.0,
            finish_hint_similarity=0.0,
            taxonomy_match="",
        )

    if not taxonomy_context:
        taxonomy_context = get_taxonomy_context(
            sanitized,
            list(texture_basenames or []),
            list(object_hints or []),
            list(collection_hints or []),
            principled or {},
        )

    allowed_types: List[str] = taxonomy_context.get("allowed_material_types") or get_allowed_material_types()
    finish_synonyms = taxonomy_context.get("finish_synonyms") or get_finish_synonyms()
    type_hint = taxonomy_context.get("material_type_hint")
    finish_candidates = taxonomy_context.get("finish_candidates") or []

    # Similarity versus canonical taxonomy
    type_match, type_similarity = _recon_find_closest_type_match(parsed["material_type"], allowed_types)
    finish_match, finish_similarity = _recon_find_closest_finish_match(parsed["finish"], finish_synonyms)

    hint_similarity = similarity_score(parsed["material_type"], type_hint) if type_hint else 0.5

    if finish_candidates:
        finish_hint_similarity = max(
            similarity_score(parsed["finish"], candidate) for candidate in finish_candidates
        )
    else:
        finish_hint_similarity = 0.5

    # Weighted aggregate score
    score = 0.45  # valid schema baseline
    score += 0.2 * _clamp(type_similarity)
    score += 0.1 * _clamp(hint_similarity)
    score += 0.15 * _clamp(finish_similarity)
    score += 0.05 * _clamp(finish_hint_similarity)

    version_idx = parsed.get("version_index") or 0
    score += 0.05 * (1.0 if version_idx >= 1 else 0.0)

    has_scene_tag = bool(parsed.get("scene_tag"))
    if has_scene_tag:
        score += 0.05  # Reward fully qualified names

    score = _clamp(score)

    if score >= 0.85:
        label = "excellent"
    elif score >= 0.7:
        label = "good"
    elif score >= 0.55:
        label = "fair"
    elif score >= 0.4:
        label = "poor"
    else:
        label = "invalid"

    if label in ("poor", "invalid"):
        if type_hint and hint_similarity < 0.6:
            issues.append(f"Type '{parsed['material_type']}' diverges from hint '{type_hint}'")
        if finish_candidates and finish_hint_similarity < 0.6:
            issues.append("Finish may not match detected context")

    taxonomy_match = f"{type_match}/{finish_match}"

    return MaterialQualityResult(
        score=round(score, 3),
        label=label,
        issues=issues,
        parsed=parsed,
        type_similarity=round(_clamp(type_similarity), 3),
        finish_similarity=round(_clamp(finish_similarity), 3),
        hint_similarity=round(_clamp(hint_similarity), 3),
        finish_hint_similarity=round(_clamp(finish_hint_similarity), 3),
        taxonomy_match=taxonomy_match,
    )


__all__ = [
    "MaterialQualityResult",
    "QUALITY_LABELS",
    "evaluate_material_name",
]

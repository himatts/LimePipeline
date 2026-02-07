"""Deterministic collection destination resolver for AI Asset Organizer.

This module is Blender-agnostic and can be unit-tested outside Blender.
It scores collection path candidates for an object and marks ambiguous cases.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional, Sequence, Tuple


_SHOT_ROOT_RE = re.compile(r"^SHOT \d{2,3}$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_GENERIC_LEAFS = {"collection", "asset", "object"}
_TOKEN_ALIASES = {
    "bg": {"background", "backdrop", "environment"},
    "background": {"bg", "backdrop", "environment"},
    "fg": {"foreground"},
    "foreground": {"fg"},
    "fx": {"effects", "vfx"},
    "effects": {"fx", "vfx"},
    "lighting": {"lights", "light"},
    "lights": {"lighting", "light"},
    "annotations": {"notes", "labels", "text"},
    "text": {"annotations", "labels"},
}


@dataclass(frozen=True)
class CollectionCandidate:
    """Candidate destination collection represented by its full path."""

    path: str
    name: str
    depth: int
    shot_root_name: Optional[str]
    is_shot_root: bool
    is_read_only: bool
    object_count: int
    path_tokens: Tuple[str, ...]
    name_tokens: Tuple[str, ...]
    exists: bool = True


@dataclass(frozen=True)
class ResolverWeights:
    """Scoring weights for collection destination ranking."""

    name_overlap: float = 3.0
    path_overlap: float = 1.2
    shot_match: float = 4.0
    shot_other: float = -3.0
    shot_global: float = -1.5
    current_membership: float = 5.0
    hint_exact: float = 5.0
    hint_leaf: float = 1.0
    last_used_exact: float = 2.0
    depth_bonus: float = 0.2
    generic_leaf_penalty: float = -0.8
    intent_leaf_match_bonus: float = 3.5
    read_only_penalty: float = -100.0
    missing_path_penalty: float = -0.5


@dataclass(frozen=True)
class RankedCandidate:
    """A ranked candidate with final score."""

    path: str
    score: float
    exists: bool


@dataclass(frozen=True)
class ResolveResult:
    """Result of destination resolution."""

    status: str
    selected_path: str
    confidence: float
    candidates: Tuple[RankedCandidate, ...]


DEFAULT_WEIGHTS = ResolverWeights()


def tokenize(value: str) -> Tuple[str, ...]:
    """Tokenize value to lowercase alphanumeric tokens."""

    if not value:
        return tuple()
    return tuple(t.lower() for t in _TOKEN_RE.findall(value))


def extract_shot_root_from_path(path: str) -> Optional[str]:
    """Return first SHOT root segment found in a slash-separated path."""

    for segment in (path or "").split("/"):
        segment = (segment or "").strip()
        if _SHOT_ROOT_RE.match(segment):
            return segment
    return None


def make_virtual_candidate(path: str) -> CollectionCandidate:
    """Build a virtual (non-existing) candidate from a path."""

    parts = [p for p in (path or "").split("/") if p]
    leaf = parts[-1] if parts else ""
    return CollectionCandidate(
        path=path,
        name=leaf,
        depth=max(0, len(parts) - 1),
        shot_root_name=extract_shot_root_from_path(path),
        is_shot_root=bool(_SHOT_ROOT_RE.match(leaf)),
        is_read_only=False,
        object_count=0,
        path_tokens=tokenize(path),
        name_tokens=tokenize(leaf),
        exists=False,
    )


def _normalize_path(path: str) -> str:
    return (path or "").strip().lower()


def _is_light_bucket_path(path: str) -> bool:
    tokens = set(tokenize(path))
    return bool(tokens.intersection({"light", "lights", "lighting"}))


def _is_camera_bucket_path(path: str) -> bool:
    tokens = set(tokenize(path))
    return bool(tokens.intersection({"cam", "camera", "cameras"}))


def _matches_object_bucket(path: str, object_type: str) -> bool:
    kind = (object_type or "").strip().upper()
    if kind == "LIGHT":
        return _is_light_bucket_path(path)
    if kind == "CAMERA":
        return _is_camera_bucket_path(path)
    return False


def _pick_preferred_current_path(
    paths: Sequence[str],
    preferred_shot_roots: set[str],
) -> str:
    candidates = [p for p in paths if (p or "").strip()]
    if preferred_shot_roots:
        filtered = [p for p in candidates if extract_shot_root_from_path(p) in preferred_shot_roots]
        if filtered:
            candidates = filtered
    candidates.sort(key=lambda p: (-p.count("/"), p.lower()))
    return candidates[0] if candidates else ""


def _expand_tokens(tokens: Iterable[str]) -> set[str]:
    expanded = {t for t in tokens if t}
    for token in list(expanded):
        expanded.update(_TOKEN_ALIASES.get(token, set()))
    return expanded


def _leaf_intent_match(object_tokens: Tuple[str, ...], leaf_tokens: Tuple[str, ...]) -> bool:
    if not object_tokens or not leaf_tokens:
        return False
    object_expanded = _expand_tokens(object_tokens)
    leaf_expanded = _expand_tokens(leaf_tokens)
    return bool(object_expanded.intersection(leaf_expanded))


def _score_candidate(
    *,
    object_tokens: Tuple[str, ...],
    object_token_set: set[str],
    candidate: CollectionCandidate,
    current_paths: set[str],
    preferred_shot_roots: set[str],
    hint_path: str,
    hint_leaf: str,
    last_used_path: str,
    weights: ResolverWeights,
) -> float:
    score = 0.0

    if candidate.is_read_only:
        score += weights.read_only_penalty

    object_expanded = _expand_tokens(object_token_set)
    name_tokens_expanded = _expand_tokens(candidate.name_tokens)
    path_tokens_expanded = _expand_tokens(candidate.path_tokens)
    name_overlap = len(object_expanded.intersection(name_tokens_expanded))
    path_overlap = len(object_expanded.intersection(path_tokens_expanded))
    score += float(name_overlap) * weights.name_overlap
    score += float(path_overlap) * weights.path_overlap

    if _normalize_path(candidate.path) in current_paths:
        score += weights.current_membership

    normalized_path = _normalize_path(candidate.path)
    if hint_path:
        if normalized_path == hint_path:
            score += weights.hint_exact
        elif hint_leaf and (candidate.name or "").strip().lower() == hint_leaf:
            score += weights.hint_leaf

    if last_used_path and normalized_path == last_used_path:
        score += weights.last_used_exact

    if preferred_shot_roots:
        if candidate.shot_root_name in preferred_shot_roots:
            score += weights.shot_match
        elif candidate.shot_root_name:
            score += weights.shot_other
        else:
            score += weights.shot_global

    score += float(max(0, candidate.depth)) * weights.depth_bonus

    leaf = (candidate.name or "").strip().lower()
    if leaf in _GENERIC_LEAFS:
        score += weights.generic_leaf_penalty

    if not candidate.exists:
        score += weights.missing_path_penalty

    if object_tokens and leaf and leaf == object_tokens[0]:
        score += 0.5
    if _leaf_intent_match(object_tokens, candidate.name_tokens):
        score += weights.intent_leaf_match_bonus

    return score


def resolve_collection_destination(
    *,
    object_name: str,
    candidates: Sequence[CollectionCandidate],
    object_type: str = "",
    current_collection_paths: Iterable[str] = (),
    preferred_shot_roots: Iterable[str] = (),
    hint_path: str = "",
    last_used_path: str = "",
    min_auto_score: float = 2.5,
    auto_score_gap: float = 1.2,
    top_n: int = 3,
    weights: ResolverWeights = DEFAULT_WEIGHTS,
) -> ResolveResult:
    """Resolve the best destination path and ambiguity state."""

    shot_roots = {s for s in preferred_shot_roots if s}
    object_tokens = tokenize(object_name)
    object_token_set = set(object_tokens)
    raw_current_paths = [p for p in current_collection_paths if (p or "").strip()]
    current_paths = {_normalize_path(p) for p in raw_current_paths}
    hint_path_norm = _normalize_path(hint_path)
    hint_leaf = ""
    if hint_path:
        parts = [p for p in hint_path.split("/") if p]
        if parts:
            hint_leaf = parts[-1].strip().lower()

    candidates_list: List[CollectionCandidate] = list(candidates or [])

    # Deterministic guard rail: keep LIGHT/CAMERA objects in their functional bucket
    # when they are already correctly placed there.
    current_bucket_paths = [p for p in raw_current_paths if _matches_object_bucket(p, object_type)]
    if current_bucket_paths:
        chosen = _pick_preferred_current_path(current_bucket_paths, shot_roots)
        if chosen:
            ranked: List[RankedCandidate] = [RankedCandidate(path=chosen, score=999.0, exists=True)]
            for cand in candidates_list:
                if (cand.path or "") == chosen:
                    continue
                if _matches_object_bucket(cand.path, object_type):
                    ranked.append(RankedCandidate(path=cand.path, score=0.0, exists=bool(cand.exists)))
            if top_n > 0:
                ranked = ranked[: max(1, top_n)]
            return ResolveResult(
                status="AUTO",
                selected_path=chosen,
                confidence=1.0,
                candidates=tuple(ranked),
            )

    bucket_candidates = [c for c in candidates_list if _matches_object_bucket(c.path, object_type)]
    if bucket_candidates:
        candidates_list = bucket_candidates
        if hint_path and not _matches_object_bucket(hint_path, object_type):
            hint_path = ""
            hint_path_norm = ""
            hint_leaf = ""

    if hint_path and all(_normalize_path(c.path) != hint_path_norm for c in candidates_list):
        candidates_list.append(make_virtual_candidate(hint_path))

    if not candidates_list:
        return ResolveResult(status="NONE", selected_path="", confidence=0.0, candidates=tuple())

    ranked: List[RankedCandidate] = []
    for cand in candidates_list:
        score = _score_candidate(
            object_tokens=object_tokens,
            object_token_set=object_token_set,
            candidate=cand,
            current_paths=current_paths,
            preferred_shot_roots=shot_roots,
            hint_path=hint_path_norm,
            hint_leaf=hint_leaf,
            last_used_path=_normalize_path(last_used_path),
            weights=weights,
        )
        ranked.append(RankedCandidate(path=cand.path, score=score, exists=bool(cand.exists)))

    ranked.sort(key=lambda item: (-item.score, (item.path or "").lower()))
    if top_n > 0:
        ranked = ranked[: max(1, top_n)]

    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    gap = top.score - second.score if second else top.score

    if top.score <= 0.0:
        confidence = 0.0
    elif second:
        confidence = max(0.0, min(1.0, gap / max(1.0, abs(top.score))))
    else:
        confidence = max(0.0, min(1.0, top.score / 8.0))

    ambiguous = top.score < min_auto_score or (second is not None and gap < auto_score_gap)
    status = "AMBIGUOUS" if ambiguous else "AUTO"
    return ResolveResult(
        status=status,
        selected_path=top.path or "",
        confidence=confidence,
        candidates=tuple(ranked),
    )

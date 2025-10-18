"""
Material Reconciliation Logic

Evaluates AI-proposed material names against the taxonomy index and determines
reconciliation actions (Accept, Normalize, or Manual Review).

Key functions:
- reconcile_proposal(): Compare proposal vs taxonomy, return action and reasoning
- find_closest_taxonomy_match(): Find nearest taxonomy type/finish by similarity
- is_experimental(): Determine if proposal is plausible but non-indexed
- apply_batch_normalization(): Intelligently normalize groups of non-indexed materials
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from .material_taxonomy import (
    get_allowed_material_types,
    get_finish_synonyms,
    get_token_material_type_mapping,
    extract_tokens,
)


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein distance between two strings (case-insensitive)."""
    s1, s2 = s1.lower(), s2.lower()
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def similarity_score(s1: str, s2: str) -> float:
    """
    Compute normalized similarity score (0–1).
    1.0 = identical, 0.0 = completely different.
    """
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    distance = _levenshtein_distance(s1, s2)
    return max(0.0, 1.0 - (distance / max_len))


def find_closest_type_match(proposed_type: str, allowed_types: List[str]) -> Tuple[str, float]:
    """
    Find the closest allowed material type by similarity.
    
    Returns: (matched_type, similarity_score 0–1)
    """
    if not proposed_type or not allowed_types:
        return ("Plastic", 0.0)
    
    best_match = allowed_types[0]
    best_score = 0.0
    
    for allowed in allowed_types:
        score = similarity_score(proposed_type, allowed)
        if score > best_score:
            best_score = score
            best_match = allowed
    
    return best_match, best_score


def find_closest_finish_match(
    proposed_finish: str,
    finish_synonyms: Optional[Dict[str, List[str]]] = None
) -> Tuple[str, float]:
    """
    Find the closest canonical finish by similarity and synonym matching.
    
    Returns: (matched_finish, similarity_score 0–1)
    """
    if not proposed_finish:
        return ("Generic", 0.0)
    
    if finish_synonyms is None:
        finish_synonyms = get_finish_synonyms()
    
    # First pass: exact match in synonyms
    for canonical, synonyms in finish_synonyms.items():
        if proposed_finish.lower() in [s.lower() for s in synonyms]:
            return (canonical, 1.0)
    
    # Second pass: similarity matching
    best_match = "Generic"
    best_score = 0.0
    
    for canonical in finish_synonyms.keys():
        score = similarity_score(proposed_finish, canonical)
        if score > best_score:
            best_score = score
            best_match = canonical
    
    return best_match, best_score


def is_plausible_experimental(
    proposed_name: str,
    confidence_from_ai: float,
    allow_non_indexed: bool,
) -> bool:
    """
    Determine if proposal is plausible as experimental (non-indexed but acceptable).
    
    Criteria:
    - confidence > 0.7 (AI is confident)
    - allow_non_indexed = True (user permits flexibility)
    - Follows naming convention (MAT_Type_Finish_VXX pattern)
    """
    if not allow_non_indexed or confidence_from_ai < 0.7:
        return False
    
    parts = proposed_name.split("_")
    if len(parts) < 4 or parts[0] != "MAT":
        return False
    
    version_token = parts[-1]
    if not (version_token.startswith("V") and version_token[1:].isdigit()):
        return False
    
    return True


def reconcile_proposal(
    proposed_name: str,
    proposed_type: str,
    proposed_finish: str,
    confidence_from_ai: float,
    allow_non_indexed: bool,
    taxonomy_context: Optional[Dict] = None,
) -> Dict[str, object]:
    """
    Reconcile AI proposal against taxonomy. Return action and metadata.
    
    Args:
        proposed_name: Full material name from AI (e.g., "MAT_Tissue_Eyeball_V01")
        proposed_type: Material type from proposal
        proposed_finish: Finish from proposal
        confidence_from_ai: Confidence score (0–1) from AI
        allow_non_indexed: User toggle for flexibility
        taxonomy_context: Dict with allowed_material_types, finish_synonyms (optional)
    
    Returns: Dict with keys:
        - is_indexed: bool (True if matches taxonomy)
        - taxonomy_type: str (canonical type, or proposed if experimental)
        - taxonomy_finish: str (canonical finish, or proposed if experimental)
        - confidence_final: float (potentially adjusted)
        - action: str ("accept" | "normalize" | "review")
        - reason: str (human-readable explanation)
        - suggested_normalized: str (normalized name if action is "normalize")
    """
    if taxonomy_context is None:
        taxonomy_context = {
            "allowed_material_types": get_allowed_material_types(),
            "finish_synonyms": get_finish_synonyms(),
        }
    
    allowed_types = taxonomy_context.get("allowed_material_types", [])
    finish_synonyms = taxonomy_context.get("finish_synonyms", {})
    
    # Step 1: Check if proposed type is in allowed list
    type_match, type_similarity = find_closest_type_match(proposed_type, allowed_types)
    is_type_indexed = type_similarity >= 0.95  # High threshold for exact/near-exact match
    
    # Step 2: Check if proposed finish is canonical
    finish_match, finish_similarity = find_closest_finish_match(proposed_finish, finish_synonyms)
    is_finish_indexed = finish_similarity >= 0.95
    
    is_fully_indexed = is_type_indexed and is_finish_indexed
    
    # Step 3: Determine action
    if is_fully_indexed:
        # Proposal matches taxonomy
        action = "accept"
        reason = "Proposal matches taxonomy standards"
        confidence_final = confidence_from_ai
        taxonomy_type = type_match
        taxonomy_finish = finish_match
        suggested_normalized = ""
    elif is_plausible_experimental(proposed_name, confidence_from_ai, allow_non_indexed):
        # Experimental proposal: high confidence + flexibility enabled
        action = "accept"
        reason = f"Experimental proposal (confidence {confidence_from_ai:.2f}, allow_non_indexed=True)"
        confidence_final = confidence_from_ai
        taxonomy_type = proposed_type
        taxonomy_finish = proposed_finish
        suggested_normalized = ""
    else:
        # Normalize to closest match
        action = "normalize"
        reason = f"Proposal outside taxonomy (type sim={type_similarity:.2f}, finish sim={finish_similarity:.2f})"
        confidence_final = max(0.0, confidence_from_ai - 0.2)  # Slightly reduce confidence
        taxonomy_type = type_match
        taxonomy_finish = finish_match
        # Build normalized name
        suggested_normalized = f"MAT_{type_match}_{finish_match}"
        # Preserve version token if valid
        parts = proposed_name.split("_")
        if len(parts) >= 4:
            version_token = parts[-1]
            if version_token.startswith("V") and version_token[1:].isdigit():
                suggested_normalized = f"{suggested_normalized}_{version_token}"
    
    return {
        "is_indexed": is_fully_indexed,
        "taxonomy_type": taxonomy_type,
        "taxonomy_finish": taxonomy_finish,
        "confidence_final": confidence_final,
        "action": action,
        "reason": reason,
        "suggested_normalized": suggested_normalized,
        "type_similarity": type_similarity,
        "finish_similarity": finish_similarity,
    }


def apply_batch_normalization(
    rows: List,  # List[LimeAIMatRow]
    policy: Optional[Dict] = None,
) -> List[Tuple]:  # List[Tuple[row, action]]
    """
    Apply intelligent batch normalization to groups of non-indexed materials.
    
    Groups by (material_type, finish) and applies consistent versioning.
    
    Args:
        rows: Collection of LimeAIMatRow objects
        policy: Dict with keys:
            - allow_experimental: bool
            - confidence_threshold: float (0–1)
    
    Returns: List of (row, new_proposed_name) tuples for rows that were modified
    """
    if policy is None:
        policy = {"allow_experimental": False, "confidence_threshold": 0.5}
    
    results = []
    groups: Dict[Tuple[str, str], List] = {}
    
    # Group rows by (type, finish)
    for row in rows:
        if getattr(row, "read_only", False):
            continue
        if not getattr(row, "selected_for_apply", False):
            continue
        
        status = (getattr(row, "status", "") or "").upper()
        if not (status.startswith("NEEDS_RENAME") or status.startswith("NAME_COLLISION")):
            continue
        
        taxonomy_type = getattr(row, "material_type", "Plastic") or "Plastic"
        taxonomy_finish = getattr(row, "finish", "Generic") or "Generic"
        key = (taxonomy_type, taxonomy_finish)
        
        if key not in groups:
            groups[key] = []
        groups[key].append(row)
    
    # For each group, assign sequential versions
    for (mat_type, finish), group_rows in groups.items():
        group_rows.sort(key=lambda r: getattr(r, "material_name", "").lower())
        
        for idx, row in enumerate(group_rows, start=1):
            new_version = f"V{idx:02d}"
            new_name = f"MAT_{mat_type}_{finish}_{new_version}"
            results.append((row, new_name))
    
    return results


__all__ = [
    "similarity_score",
    "find_closest_type_match",
    "find_closest_finish_match",
    "is_plausible_experimental",
    "reconcile_proposal",
    "apply_batch_normalization",
]

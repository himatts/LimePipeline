"""
Material taxonomy utilities for Lime Pipeline AI Material Renamer.

Provides external taxonomy loading and inference functions for material classification.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Fallback taxonomy if external file is not found
FALLBACK_TAXONOMY = {
    "families": ["Plastic", "Metal", "Glass", "Rubber", "Paint", "Wood", "Fabric", "Ceramic", "Emissive", "Stone", "Concrete", "Paper", "Leather", "Liquid"],
    "map_tokens_to_family": {
        "ABS": "Plastic",
        "PC": "Plastic",
        "PP": "Plastic",
        "HDPE": "Plastic",
        "LDPE": "Plastic",
        "PET": "Plastic",
        "Nylon": "Plastic",
        "PVC": "Plastic",
        "Acrylic": "Plastic",
        "PEEK": "Plastic",
        "Bakelite": "Plastic",
        "CarbonFiber": "Plastic",
        "Gold": "Metal",
        "Silver": "Metal",
        "Copper": "Metal",
        "Bronze": "Metal",
        "Steel": "Metal",
        "Alu": "Metal",
        "Galvanized": "Metal",
        "Brick": "Ceramic",
        "Tile": "Ceramic",
        "Tiles": "Ceramic",
        "Herringbone": "Ceramic",
        "Hex": "Ceramic",
        "Marble": "Stone",
        "Granite": "Stone",
        "Slate": "Stone",
        "Limestone": "Stone",
        "Travertine": "Stone",
        "Terrazzo": "Ceramic",
        "Plaster": "Ceramic",
        "Concrete": "Concrete",
        "Asphalt": "Concrete",
        "Glass": "Glass",
        "Tint": "Glass",
        "Dispersion": "Glass",
        "Velvet": "Fabric",
        "Jean": "Fabric",
        "Knitting": "Fabric",
        "Embroidery": "Fabric",
        "Sequin": "Fabric",
        "Leather": "Leather",
        "PU": "Leather",
        "Paper": "Paper",
        "Cardboard": "Paper",
        "Water": "Liquid",
        "Ocean": "Liquid",
        "Puddle": "Liquid",
        "Underwater": "Liquid",
        "Waterfall": "Liquid"
    },
    "finish_synonyms": {
        "Brushed": ["Brushed", "Brushing"],
        "Polished": ["Polished", "Polish"],
        "Rough": ["Rough", "Coarse"],
        "Anodized": ["Anodized", "Anod"],
        "Galvanized": ["Galvanized", "Zinc"],
        "Rusty": ["Rust", "Rusty"],
        "Herringbone": ["Herringbone", "Chevron"],
        "TilesHex": ["Hex", "Hexagonal"],
        "TilesOffset": ["Offset"],
        "TilesGrid": ["Grid"],
        "Old": ["Old", "Worn", "Aged"],
        "Generic": ["Generic", "Base", "Default"]
    }
}


def load_taxonomy() -> Dict[str, object]:
    """Load taxonomy from external JSON file or return fallback."""
    taxonomy_path = Path(__file__).parent.parent.parent / "openspec" / "changes" / "2025-10-04-add-ai-material-renamer" / "taxonomy" / "material_taxonomy.json"

    if taxonomy_path.exists():
        try:
            with open(taxonomy_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass

    return FALLBACK_TAXONOMY


def get_token_family_mapping() -> Dict[str, str]:
    """Get token to family mapping from taxonomy."""
    taxonomy = load_taxonomy()
    return taxonomy.get("map_tokens_to_family", {})


def get_finish_synonyms() -> Dict[str, List[str]]:
    """Get finish synonyms from taxonomy."""
    taxonomy = load_taxonomy()
    return taxonomy.get("finish_synonyms", {})


def get_allowed_families() -> List[str]:
    """Get list of allowed families from taxonomy."""
    taxonomy = load_taxonomy()
    return taxonomy.get("families", [])


def extract_tokens(text: str) -> Set[str]:
    """Extract tokens from text (material names, texture names, hints)."""
    if not text:
        return set()

    # Split by common separators and extract alphanumeric tokens
    tokens = set()
    for part in text.replace("_", " ").replace("-", " ").split():
        # Extract alphanumeric sequences
        for token in part.split():
            cleaned = "".join(c for c in token if c.isalnum())
            if cleaned and len(cleaned) > 2:  # Filter very short tokens
                tokens.add(cleaned.lower())

    return tokens


def infer_family_and_candidates(
    material_name: str,
    texture_basenames: List[str],
    object_hints: List[str],
    collection_hints: List[str],
    principled: Dict[str, float]
) -> Tuple[str, List[str]]:
    """
    Infer family hint and finish candidates from available data.

    Returns:
        Tuple of (family_hint, finish_candidates)
    """
    taxonomy = load_taxonomy()
    token_to_family = taxonomy.get("map_tokens_to_family", {})
    finish_synonyms = taxonomy.get("finish_synonyms", {})

    # Collect all tokens from available sources
    all_tokens = set()

    # Extract from material name
    all_tokens.update(extract_tokens(material_name))

    # Extract from texture basenames
    for texture in texture_basenames:
        all_tokens.update(extract_tokens(texture))

    # Extract from object hints
    for hint in object_hints:
        all_tokens.update(extract_tokens(hint))

    # Extract from collection hints
    for hint in collection_hints:
        all_tokens.update(extract_tokens(hint))

    # Apply heuristics for family inference
    family_scores = {}

    # Principled-based heuristics
    metallic = principled.get("metallic", 0.0)
    roughness = principled.get("roughness", 0.5)
    transmission = principled.get("transmission", 0.0)
    emission = principled.get("emission_strength", 0.0)

    if metallic >= 0.5:
        family_scores["Metal"] = family_scores.get("Metal", 0) + 3
    if transmission >= 0.3:
        family_scores["Glass"] = family_scores.get("Glass", 0) + 3
    if emission > 0:
        family_scores["Emissive"] = family_scores.get("Emissive", 0) + 3
    if roughness >= 0.6 and metallic < 0.5:
        family_scores["Rubber"] = family_scores.get("Rubber", 0) + 2
        family_scores["Plastic"] = family_scores.get("Plastic", 0) - 1

    # Token-based scoring
    for token in all_tokens:
        if token in token_to_family:
            family = token_to_family[token]
            family_scores[family] = family_scores.get(family, 0) + 2

    # Default fallback
    if not family_scores:
        family_scores["Plastic"] = 1

    # Select best family
    family_hint = max(family_scores.items(), key=lambda x: x[1])[0]

    # Collect finish candidates
    finish_candidates = set()

    # Add all synonyms for tokens found in text
    for token in all_tokens:
        for finish, synonyms in finish_synonyms.items():
            if token in [s.lower() for s in synonyms]:
                finish_candidates.add(finish)

    # If no specific finishes found, add common defaults
    if not finish_candidates:
        finish_candidates.update(["Generic", "Brushed", "Polished", "Rough"])

    return family_hint, sorted(list(finish_candidates))


def get_taxonomy_context(material_name: str, texture_basenames: List[str], object_hints: List[str], collection_hints: List[str], principled: Dict[str, float]) -> Dict[str, object]:
    """
    Get taxonomy context for AI prompt.

    Returns:
        Dictionary with allowed_families, family_hint, and finish_candidates
    """
    taxonomy = load_taxonomy()
    family_hint, finish_candidates = infer_family_and_candidates(
        material_name, texture_basenames, object_hints, collection_hints, principled
    )

    return {
        "allowed_families": taxonomy.get("families", []),
        "family_hint": family_hint,
        "finish_candidates": finish_candidates
    }


__all__ = [
    "load_taxonomy",
    "get_token_family_mapping",
    "get_finish_synonyms",
    "get_allowed_families",
    "extract_tokens",
    "infer_family_and_candidates",
    "get_taxonomy_context",
]

"""
Material taxonomy utilities for Lime Pipeline AI Material Renamer.

Provides external taxonomy loading and inference helpers for material classification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

FALLBACK_TAXONOMY = {
    "material_types": [
        "Plastic",
        "Metal",
        "Glass",
        "Rubber",
        "Paint",
        "Wood",
        "Fabric",
        "Ceramic",
        "Emissive",
        "Stone",
        "Concrete",
        "Paper",
        "Leather",
        "Liquid",
    ],
    "map_tokens_to_material_type": {
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
        "Waterfall": "Liquid",
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
        "Generic": ["Generic", "Base", "Default"],
    },
}


def _taxonomy_path() -> Path:
    return (
        Path(__file__).parent.parent.parent
        / "openspec"
        / "changes"
        / "2025-10-04-add-ai-material-renamer"
        / "taxonomy"
        / "material_taxonomy.json"
    )


def load_taxonomy() -> Dict[str, object]:
    path = _taxonomy_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass
    return FALLBACK_TAXONOMY


def get_token_material_type_mapping() -> Dict[str, str]:
    taxonomy = load_taxonomy()
    return taxonomy.get("map_tokens_to_material_type", {})


def get_finish_synonyms() -> Dict[str, List[str]]:
    taxonomy = load_taxonomy()
    return taxonomy.get("finish_synonyms", {})


def get_allowed_material_types() -> List[str]:
    taxonomy = load_taxonomy()
    materials = taxonomy.get("material_types", [])
    return materials or FALLBACK_TAXONOMY["material_types"]


def extract_tokens(text: str) -> Set[str]:
    if not text:
        return set()
    tokens: Set[str] = set()
    sanitized = text.replace("_", " ").replace("-", " ")
    for chunk in sanitized.split():
        cleaned = "".join(c for c in chunk if c.isalnum())
        if cleaned and len(cleaned) > 2:
            tokens.add(cleaned.lower())
    return tokens


def infer_material_type_and_finishes(
    material_name: str,
    texture_basenames: List[str],
    object_hints: List[str],
    collection_hints: List[str],
    principled: Dict[str, float],
) -> Tuple[str, List[str]]:
    taxonomy = load_taxonomy()
    token_map = {k.lower(): v for k, v in taxonomy.get("map_tokens_to_material_type", {}).items()}
    finish_synonyms = taxonomy.get("finish_synonyms", {})

    all_tokens: Set[str] = set()
    all_tokens.update(extract_tokens(material_name))
    for value in texture_basenames:
        all_tokens.update(extract_tokens(value))
    for value in object_hints:
        all_tokens.update(extract_tokens(value))
    for value in collection_hints:
        all_tokens.update(extract_tokens(value))

    scores: Dict[str, int] = {}
    metallic = principled.get("metallic", 0.0) if principled else 0.0
    roughness = principled.get("roughness", 0.5) if principled else 0.5
    transmission = principled.get("transmission", 0.0) if principled else 0.0
    emission = principled.get("emission_strength", 0.0) if principled else 0.0

    if metallic >= 0.5:
        scores["Metal"] = scores.get("Metal", 0) + 3
    if transmission >= 0.3:
        scores["Glass"] = scores.get("Glass", 0) + 3
    if emission > 0:
        scores["Emissive"] = scores.get("Emissive", 0) + 3
    if roughness >= 0.6 and metallic < 0.5:
        scores["Rubber"] = scores.get("Rubber", 0) + 2
        scores["Plastic"] = scores.get("Plastic", 0) - 1

    for token in all_tokens:
        mapped = token_map.get(token.lower())
        if mapped:
            scores[mapped] = scores.get(mapped, 0) + 2

    if not scores:
        scores["Plastic"] = 1

    material_type = max(scores.items(), key=lambda item: item[1])[0]

    finish_candidates: Set[str] = set()
    lower_tokens = {token.lower() for token in all_tokens}
    for finish, synonyms in finish_synonyms.items():
        for synonym in synonyms:
            if synonym.lower() in lower_tokens:
                finish_candidates.add(finish)
                break

    if not finish_candidates:
        finish_candidates.update(["Generic", "Brushed", "Polished", "Rough"])

    return material_type, sorted(finish_candidates)


def get_taxonomy_context(
    material_name: str,
    texture_basenames: List[str],
    object_hints: List[str],
    collection_hints: List[str],
    principled: Dict[str, float],
) -> Dict[str, object]:
    material_type_hint, finish_candidates = infer_material_type_and_finishes(
        material_name, texture_basenames, object_hints, collection_hints, principled
    )
    return {
        "allowed_material_types": get_allowed_material_types(),
        "material_type_hint": material_type_hint,
        "finish_candidates": finish_candidates,
    }


__all__ = [
    "extract_tokens",
    "get_allowed_material_types",
    "get_finish_synonyms",
    "get_taxonomy_context",
    "get_token_material_type_mapping",
    "infer_material_type_and_finishes",
    "load_taxonomy",
]

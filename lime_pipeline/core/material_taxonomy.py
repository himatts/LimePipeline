"""
Material taxonomy utilities for Lime Pipeline AI Asset Organizer.

Provides external taxonomy loading and inference helpers for material classification.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

FALLBACK_TAXONOMY = {
    "material_types": [
        "Plastic",
        "Metal",
        "Glass",
        "Rubber",
        "Silicone",
        "Background",
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
        # Extended families for organic/anatomical and text/annotation materials
        "Organic",
        "Tissue",
        "Tooth",
        "Text",
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
        "Rubber": "Rubber",
        "Latex": "Rubber",
        "Silicone": "Silicone",
        "Siloxane": "Silicone",
        "Silastic": "Silicone",
        "SiliconeRubber": "Silicone",
        "LSR": "Silicone",
        "VMQ": "Silicone",
        "Background": "Background",
        "Sky": "Background",
        "Skybox": "Background",
        "Skydome": "Background",
        "Backplate": "Background",
        "Backdrop": "Background",
        "Environment": "Background",
        "Env": "Background",
        "Annotation": "Text",  # For simple flat annotations, labels
        "Label": "Text",
        "Decal": "Plastic",  # For decals, often plastic/vinyl adhesive
        "Sticker": "Plastic",  # For stickers, often plastic-based
        "Water": "Liquid",
        "Ocean": "Liquid",
        "Puddle": "Liquid",
        "Underwater": "Liquid",
        "Waterfall": "Liquid",
        # Human/organic tokens → Tissue/Organic/Tooth
        "Skin": "Tissue",
        "Epidermis": "Tissue",
        "Dermis": "Tissue",
        "Iris": "Tissue",
        "Eye": "Tissue",
        "Sclera": "Tissue",
        "Cornea": "Tissue",
        "Pupil": "Tissue",
        "Gum": "Tissue",
        "Tongue": "Tissue",
        "Nail": "Tissue",
        "Fingernail": "Tissue",
        "Toenail": "Tissue",
        "Hair": "Organic",
        "Beard": "Organic",
        "Eyebrow": "Organic",
        "Eyelash": "Organic",
        "Tooth": "Tooth",
        "Teeth": "Tooth",
        "Enamel": "Tooth",
        "Molar": "Tooth",
        "Premolar": "Tooth",
        "Incisor": "Tooth",
        "Canine": "Tooth",
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
    # Organic/anatomical finishes (semantic preservation in Finish block)
    "HumanSkin": ["Skin", "Epidermis", "Dermis", "HumanSkin"],
    "Iris": ["Iris"],
    "Sclera": ["Sclera"],
    "Cornea": ["Cornea"],
    "Pupil": ["Pupil"],
    "Eyelash": ["Eyelash", "Lash"],
    "Eyebrow": ["Eyebrow", "Brow"],
    "Hair": ["Hair", "HairMat", "HairAniso", "HairBase"],  # Preserve Hair-specific terms
    "HairStraight": ["HairStraight", "StraightHair", "Straight"],
    "HairCurly": ["HairCurly", "CurlyHair", "Curly"],
    "Eyeball": ["Eyeball", "Eye", "EyeSphere"],  # Preserve Eyeball-specific terms
    "Fingernail": ["Fingernail", "Nail"],
    "Toenail": ["Toenail"],
    "Gum": ["Gum"],
    "Tongue": ["Tongue"],
    "ToothEnamel": ["Enamel", "Tooth", "Teeth"],
        "Generic": ["Generic", "Base", "Default"],
    },
}


SILICONE_TOKEN_HINTS: Set[str] = {
    "silicone",
    "siliconerubber",
    "silastic",
    "siloxane",
    "lsr",
    "vmq",
}

RUBBER_TOKEN_HINTS: Set[str] = {
    "rubber",
    "latex",
    "neoprene",
    "nitrile",
}

BACKGROUND_TOKEN_HINTS: Set[str] = {
    "background",
    "sky",
    "skybox",
    "skydome",
    "backdrop",
    "backplate",
    "environment",
    "env",
}


def load_taxonomy() -> Dict[str, object]:
    # OpenSpec-based external taxonomy was removed; keep stable in-code defaults.
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

    lower_tokens = {token.lower() for token in all_tokens}

    has_silicone_hint = any(hint in lower_tokens for hint in SILICONE_TOKEN_HINTS)
    has_rubber_hint = any(hint in lower_tokens for hint in RUBBER_TOKEN_HINTS)
    has_background_hint = any(hint in lower_tokens for hint in BACKGROUND_TOKEN_HINTS)

    if roughness >= 0.6 and metallic < 0.5:
        if has_silicone_hint:
            scores["Silicone"] = scores.get("Silicone", 0) + 2
        else:
            scores["Rubber"] = scores.get("Rubber", 0) + 2
        scores["Plastic"] = scores.get("Plastic", 0) - 1

    for token in all_tokens:
        mapped = token_map.get(token.lower())
        if mapped:
            scores[mapped] = scores.get(mapped, 0) + 2

    if has_silicone_hint:
        scores["Silicone"] = scores.get("Silicone", 0) + 4

    if has_rubber_hint:
        scores["Rubber"] = scores.get("Rubber", 0) + 2

    if has_background_hint:
        scores["Background"] = scores.get("Background", 0) + 5

    if not scores:
        scores["Plastic"] = 1

    material_type = max(scores.items(), key=lambda item: item[1])[0]

    finish_candidates: Set[str] = set()
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


def find_closest_type_match(proposed_type: str, allowed_types: List[str] = None) -> Tuple[str, float]:
    """
    Find closest allowed material type by simple similarity.
    Returns (matched_type, similarity_score 0–1).
    
    Note: For more advanced matching, use material_reconciliation.find_closest_type_match.
    """
    from .material_reconciliation import similarity_score
    
    if allowed_types is None:
        allowed_types = get_allowed_material_types()
    
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


def find_closest_finish_match(proposed_finish: str, finish_synonyms: Dict[str, List[str]] = None) -> Tuple[str, float]:
    """
    Find closest canonical finish by synonym matching or similarity.
    Returns (matched_finish, similarity_score 0–1).
    
    Note: For more advanced matching, use material_reconciliation.find_closest_finish_match.
    """
    from .material_reconciliation import similarity_score
    
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


__all__ = [
    "extract_tokens",
    "find_closest_finish_match",
    "find_closest_type_match",
    "get_allowed_material_types",
    "get_finish_synonyms",
    "get_taxonomy_context",
    "get_token_material_type_mapping",
    "infer_material_type_and_finishes",
    "load_taxonomy",
]

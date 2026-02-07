"""AI Asset Organizer package.

Public export surface for operators and runtime helpers.
"""

from __future__ import annotations

from .runtime_api import (
    is_preview_suspended,
    on_name_changed,
    refresh_ai_asset_preview,
    refresh_preview,
    sync_planned_rows,
    sync_row_selection,
)
from .operators_suggest import LIME_TB_OT_ai_asset_suggest_names
from .operators_apply import (
    LIME_TB_OT_ai_asset_apply_names,
    LIME_TB_OT_ai_asset_scope_preset,
    LIME_TB_OT_ai_asset_refresh_targets,
)
from .operators_targets import (
    LIME_TB_OT_ai_asset_resolve_target,
    LIME_TB_OT_ai_asset_set_target_for_item,
    LIME_TB_OT_ai_asset_set_target_for_selected,
)
from .operators_misc import (
    LIME_TB_OT_ai_asset_clear,
    LIME_TB_OT_open_ai_asset_manager,
    LIME_TB_OT_ai_asset_test_connection,
    LIME_TB_OT_ai_asset_material_debug_report,
    LIME_TB_OT_ai_asset_collection_debug_report,
)

__all__ = [
    "is_preview_suspended",
    "on_name_changed",
    "refresh_preview",
    "sync_row_selection",
    "refresh_ai_asset_preview",
    "LIME_TB_OT_ai_asset_suggest_names",
    "sync_planned_rows",
    "LIME_TB_OT_ai_asset_apply_names",
    "LIME_TB_OT_ai_asset_scope_preset",
    "LIME_TB_OT_ai_asset_refresh_targets",
    "LIME_TB_OT_ai_asset_resolve_target",
    "LIME_TB_OT_ai_asset_set_target_for_item",
    "LIME_TB_OT_ai_asset_set_target_for_selected",
    "LIME_TB_OT_ai_asset_clear",
    "LIME_TB_OT_open_ai_asset_manager",
    "LIME_TB_OT_ai_asset_test_connection",
    "LIME_TB_OT_ai_asset_material_debug_report",
    "LIME_TB_OT_ai_asset_collection_debug_report",
]

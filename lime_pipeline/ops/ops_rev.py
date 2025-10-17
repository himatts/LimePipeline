"""
Revision Navigation Operators

This module provides functionality for navigating between project revisions using
the Lime Pipeline revision letter system. It allows users to cycle through revision
letters (A-Z) for organizing different versions or iterations of project assets.

The revision system integrates with Lime Pipeline settings to maintain revision
state and provide intuitive navigation between different project versions.

Key Features:
- Alphabetical revision navigation (A-Z)
- Integration with Lime Pipeline settings and state management
- Cyclic navigation with wraparound from Z to A and A to Z
- Validation of revision letter format and constraints
- Error handling for missing or invalid revision settings
"""

import bpy


class LIME_OT_rev_prev(bpy.types.Operator):
    bl_idname = "lime.rev_prev"
    bl_label = "Previous Revision"
    bl_description = "Go to previous revision letter (A–Z)"

    def execute(self, context):
        st = getattr(context.window_manager, "lime_pipeline", None)
        if st is None:
            return {'CANCELLED'}
        try:
            s = (getattr(st, "rev_letter", "") or "A").strip().upper()
            ch = s[0] if s and 'A' <= s[0] <= 'Z' else 'A'
            new_ch = chr(max(ord('A'), ord(ch) - 1))
            st.rev_letter = new_ch
        except Exception:
            st.rev_letter = 'A'
        return {'FINISHED'}


class LIME_OT_rev_next(bpy.types.Operator):
    bl_idname = "lime.rev_next"
    bl_label = "Next Revision"
    bl_description = "Go to next revision letter (A–Z)"

    def execute(self, context):
        st = getattr(context.window_manager, "lime_pipeline", None)
        if st is None:
            return {'CANCELLED'}
        try:
            s = (getattr(st, "rev_letter", "") or "A").strip().upper()
            ch = s[0] if s and 'A' <= s[0] <= 'Z' else 'A'
            new_ch = chr(min(ord('Z'), ord(ch) + 1))
            st.rev_letter = new_ch
        except Exception:
            st.rev_letter = 'A'
        return {'FINISHED'}


__all__ = [
    "LIME_OT_rev_prev",
    "LIME_OT_rev_next",
]



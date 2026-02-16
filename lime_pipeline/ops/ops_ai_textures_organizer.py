"""Operators for AI Textures Organizer staged workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import bpy
from bpy.types import Operator

from ..core.texture_naming import sanitize_filename_stem
from .texture_workflow_common import (
    ai_suggest_texture_name,
    blend_dir,
    canonical_filename_for_item,
    collect_image_usages_from_materials,
    collect_materials_from_selected_objects,
    copy_texture_file,
    deduce_project_root,
    exists_for_scan,
    infer_scan_classification,
    project_token_for_naming,
    protected_roots_for_context,
    read_sha256_index,
    relpath_for_blender,
    resolve_abs_image_path,
    resolve_texture_root_for_context,
    safe_mkdir,
    sha256_file,
    unique_destination,
    usage_socket_targets,
    utc_now_iso,
    utc_timestamp,
    write_sha256_index,
)
from .ai_http import has_openrouter_api_key


_ADOPTABLE_CLASSES = {"EXTERNAL_ADOPTABLE", "IN_PROJECT_ADOPTABLE", "ADOPTABLE"}


def _state_from_context(context):
    scene = getattr(context, "scene", None)
    if scene is None:
        return None
    return getattr(scene, "lime_ai_textures", None)


def _iter_scope_materials(context, scan_scope: str) -> List[Any]:
    if (scan_scope or "ALL_SCENE").upper() == "SELECTED_ONLY":
        return collect_materials_from_selected_objects(context)
    return list(getattr(bpy.data, "materials", []) or [])


def _socket_targets_json(values: Sequence[str]) -> str:
    try:
        return json.dumps(list(values), ensure_ascii=False)
    except Exception:
        return "[]"


def _socket_targets_from_item(item) -> List[str]:
    raw = (getattr(item, "socket_targets_json", "") or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(v) for v in data if str(v).strip()]
    except Exception:
        pass
    return []


def _item_issue_summary(classification: str, reasons: Sequence[str]) -> str:
    class_text = (classification or "").replace("_", " ").title()
    if reasons:
        return f"{class_text}: {reasons[0]}"
    return class_text


def _mark_busy(state, value: bool) -> None:
    try:
        state.is_busy = bool(value)
    except Exception:
        pass


def _update_state_counts(state) -> None:
    total = 0
    adoptable = 0
    protected = 0
    missing = 0
    selected_ready = 0
    for item in list(getattr(state, "items", []) or []):
        total += 1
        classification = (getattr(item, "classification", "") or "").upper()
        status = (getattr(item, "status", "") or "").upper()
        if classification in _ADOPTABLE_CLASSES:
            adoptable += 1
        if classification == "PROTECTED":
            protected += 1
        if classification == "MISSING":
            missing += 1
        if bool(getattr(item, "selected_for_apply", False)) and status == "READY":
            selected_ready += 1
    state.total_count = total
    state.adoptable_count = adoptable
    state.protected_count = protected
    state.missing_count = missing
    state.selected_ready_count = selected_ready
    if selected_ready > 0 and not bool(getattr(state, "ai_blocked", False)):
        state.phase = "READY_TO_APPLY"


def _reset_state(state) -> None:
    state.items.clear()
    state.active_index = 0
    state.phase = "IDLE"
    state.ai_blocked = False
    state.last_error = ""
    state.total_count = 0
    state.adoptable_count = 0
    state.protected_count = 0
    state.missing_count = 0
    state.selected_ready_count = 0
    state.analysis_report_path = ""
    state.refine_report_path = ""
    state.apply_manifest_path = ""


def _item_lookup_key(item) -> tuple[str, str, str]:
    return (
        (getattr(item, "image_name", "") or "").strip(),
        (getattr(item, "raw_filepath", "") or "").strip(),
        (getattr(item, "abs_filepath", "") or "").strip(),
    )


def _usage_lookup_key(image: Any) -> tuple[str, str, str]:
    image_name = (getattr(image, "name", "") or "").strip()
    raw = (getattr(image, "filepath", "") or "").strip()
    abs_path, _ = resolve_abs_image_path(image)
    return image_name, raw, str(abs_path) if abs_path is not None else ""


def _resolve_image_for_item(item, usage_by_image: Dict[int, Tuple[Any, List[Any]]]):
    image_ref = getattr(item, "image_ref", None)
    if image_ref is not None:
        try:
            image_ref.name
            return image_ref
        except Exception:
            pass

    target_key = _item_lookup_key(item)
    for _img_key, (image, _usages) in usage_by_image.items():
        if _usage_lookup_key(image) == target_key:
            return image
    return None


def _make_report_dir(dest_root: Path) -> tuple[Optional[Path], Optional[str]]:
    report_dir = dest_root / "_manifests"
    err = safe_mkdir(report_dir)
    if err:
        return None, err
    return report_dir, None


def _write_json(path: Path, payload: Dict[str, object]) -> Optional[str]:
    try:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return None
    except Exception as ex:
        return str(ex)


class _ModalRunnerMixin:
    _timer = None
    _runner = None
    _runner_result = None

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        self._runner_result = None
        self._runner = self._run_generator(context)
        wm = context.window_manager
        try:
            self._timer = wm.event_timer_add(0.05, window=context.window)
            wm.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception:
            while True:
                try:
                    next(self._runner)
                except StopIteration:
                    break
            return self._runner_result or {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC":
            try:
                context.window_manager.progress_end()
            except Exception:
                pass
            if self._timer is not None:
                try:
                    context.window_manager.event_timer_remove(self._timer)
                except Exception:
                    pass
                self._timer = None
            self._runner = None
            self._runner_result = {"CANCELLED"}
            self.report({"WARNING"}, "Operation cancelled by user")
            return {"CANCELLED"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        if self._runner is None:
            if self._timer is not None:
                try:
                    context.window_manager.event_timer_remove(self._timer)
                except Exception:
                    pass
                self._timer = None
            return self._runner_result or {"CANCELLED"}

        try:
            next(self._runner)
        except StopIteration:
            self._runner = None
        except Exception as ex:
            self._runner = None
            self._runner_result = {"CANCELLED"}
            self.report({"ERROR"}, str(ex))
        return {"RUNNING_MODAL"}


class LIME_OT_texture_analyze(_ModalRunnerMixin, Operator):
    bl_idname = "lime.texture_analyze"
    bl_label = "Analyze Textures"
    bl_description = "Analyze scene textures and generate initial AI suggestions without applying changes"
    bl_options = {"REGISTER"}

    def _run_generator(self, context):
        state = _state_from_context(context)
        if state is None:
            self.report({"ERROR"}, "AI Textures state is unavailable")
            self._runner_result = {"CANCELLED"}
            return

        _mark_busy(state, True)
        state.last_error = ""
        state.ai_blocked = False
        state.phase = "IDLE"
        state.items.clear()
        state.active_index = 0
        state.refine_report_path = ""
        state.apply_manifest_path = ""

        materials = _iter_scope_materials(context, getattr(state, "scan_scope", "ALL_SCENE"))
        if (getattr(state, "scan_scope", "ALL_SCENE") or "").upper() == "SELECTED_ONLY" and not materials:
            _mark_busy(state, False)
            self.report({"ERROR"}, "No selected object materials found for selected-only scan scope")
            self._runner_result = {"CANCELLED"}
            return

        usage_by_image = collect_image_usages_from_materials(materials)
        project_root, local_mode = deduce_project_root(context)
        protected_roots = protected_roots_for_context(context)
        dest_root = resolve_texture_root_for_context(project_root, local_mode=local_mode)
        project_token = project_token_for_naming(project_root=project_root) or "Project"

        report_dir, err = _make_report_dir(dest_root)
        if err:
            _mark_busy(state, False)
            self.report({"ERROR"}, f"Cannot create manifest folder: {err}")
            self._runner_result = {"CANCELLED"}
            return

        ai_error = ""
        ai_runtime_ok = has_openrouter_api_key()
        if not ai_runtime_ok:
            ai_error = "OpenRouter API key not found in .env"
            state.ai_blocked = True
            state.last_error = ai_error

        analysis_items: List[Dict[str, object]] = []
        wm = context.window_manager
        total_jobs = max(1, int(len(usage_by_image)))
        try:
            wm.progress_begin(0, total_jobs)
        except Exception:
            pass

        for idx, (_img_key, (image, usages)) in enumerate(usage_by_image.items(), 1):
            yield None
            try:
                wm.progress_update(idx)
            except Exception:
                pass
            if (idx % 3) == 0:
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:
                    pass

            raw_filepath = (getattr(image, "filepath", "") or "").strip()
            abs_path, path_reasons = resolve_abs_image_path(image)
            exists = exists_for_scan(abs_path, raw_filepath=raw_filepath)

            classification, reasons = infer_scan_classification(
                image=image,
                usages=usages,
                abs_path=abs_path,
                raw_filepath=raw_filepath,
                exists=exists,
                project_root=project_root,
                protected_roots=protected_roots,
                dest_root=dest_root,
            )
            reasons = list(path_reasons) + list(reasons)
            is_adoptable = classification in _ADOPTABLE_CLASSES
            read_only = not is_adoptable

            first = usages[0] if usages else None
            map_type = getattr(first, "map_type", "") or "Generic"
            socket_targets = usage_socket_targets(usages)
            ext = ((abs_path.suffix if abs_path is not None else "") or ".png").lower()
            source_stem = sanitize_filename_stem(abs_path.stem if abs_path is not None else "") or "Texture"

            initial_suggestion = ""
            refined_suggestion = ""
            final_filename = ""
            dest_preview_path = ""
            item_status = "ANALYZED"
            item_error = ""

            if is_adoptable:
                if ai_runtime_ok:
                    ai_box: Dict[str, tuple[str, str | None, str | None, str | None, Dict[str, object] | None, str | None]] = {}

                    def _run_ai() -> None:
                        try:
                            ai_box["result"] = ai_suggest_texture_name(
                                context=context,
                                original_filename=(abs_path.name if abs_path is not None else getattr(image, "name", "") or "texture.png"),
                                material_name=getattr(first, "material_name", "") if first is not None else "",
                                map_type=map_type,
                                socket_targets=socket_targets,
                                manual_hint="",
                                prior_suggestion="",
                                include_preview=bool(getattr(state, "ai_include_preview", False)),
                                image=image,
                            )
                        except Exception as ex:
                            ai_box["result"] = ("", None, None, None, None, f"OpenRouter request failed: {ex}")

                    ai_thread = threading.Thread(target=_run_ai, daemon=True)
                    ai_thread.start()
                    while ai_thread.is_alive():
                        try:
                            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                        except Exception:
                            pass
                        yield None

                    suggested, ai_map_type, _explanation, _image_summary, _preview_meta, ai_err = ai_box.get(
                        "result",
                        ("", None, None, None, None, "OpenRouter request returned no result"),
                    )
                    if suggested:
                        map_for_name = ai_map_type or map_type
                        initial_suggestion = suggested
                        final_filename = canonical_filename_for_item(
                            project_token=project_token,
                            source_stem=suggested,
                            map_type=map_for_name,
                            ext=ext,
                        )
                        item_status = "READY"
                    else:
                        ai_runtime_ok = False
                        ai_error = ai_err or "OpenRouter request failed"
                        state.ai_blocked = True
                        state.last_error = ai_error
                        item_status = "AI_BLOCKED"
                        item_error = ai_error
                else:
                    item_status = "AI_BLOCKED"
                    item_error = ai_error or "AI unavailable"

                if not final_filename:
                    final_filename = canonical_filename_for_item(
                        project_token=project_token,
                        source_stem=source_stem,
                        map_type=map_type,
                        ext=ext,
                    )
                dest_preview_path = str(dest_root / final_filename)

            material_set = {str(getattr(u, "material_name", "") or "").strip() for u in usages}
            material_set.discard("")
            material_names = sorted(material_set)
            materials_summary = ", ".join(material_names[:4])
            if len(material_names) > 4:
                materials_summary = f"{materials_summary}, ..."

            item = state.items.add()
            item.item_id = f"{hash((getattr(image, 'name', ''), raw_filepath, str(abs_path) if abs_path else '')):x}"
            try:
                item.image_ref = image
            except Exception:
                pass
            item.image_name = getattr(image, "name", "") or ""
            item.raw_filepath = raw_filepath
            item.abs_filepath = str(abs_path) if abs_path is not None else ""
            item.classification = classification
            item.issue_summary = _item_issue_summary(classification, reasons)
            item.map_type = map_type
            item.materials_summary = materials_summary
            item.socket_targets_json = _socket_targets_json(socket_targets)
            item.hint_text = ""
            item.initial_suggestion = initial_suggestion
            item.refined_suggestion = refined_suggestion
            item.final_filename = final_filename
            item.dest_preview_path = dest_preview_path
            item.status = item_status
            item.last_error = item_error
            item.read_only = read_only
            item.selected_for_apply = bool(is_adoptable and item_status == "READY")

            analysis_items.append(
                {
                    "image_name": item.image_name,
                    "raw_filepath": item.raw_filepath,
                    "abs_filepath": item.abs_filepath,
                    "classification": classification,
                    "reasons": reasons,
                    "map_type": map_type,
                    "socket_targets": socket_targets,
                    "initial_suggestion": initial_suggestion,
                    "final_filename": final_filename,
                    "status": item_status,
                    "last_error": item_error,
                }
            )

        _update_state_counts(state)
        if len(state.items) > 0:
            state.phase = "ANALYZED" if state.ai_blocked else ("READY_TO_APPLY" if state.selected_ready_count > 0 else "ANALYZED")
        else:
            state.phase = "IDLE"

        payload = {
            "generated_at": utc_now_iso(),
            "blend_filepath": (getattr(bpy.data, "filepath", "") or "").strip(),
            "blend_dir": str(blend_dir()),
            "scan_scope": getattr(state, "scan_scope", "ALL_SCENE"),
            "project_root": str(project_root) if project_root is not None else None,
            "texture_root": str(dest_root),
            "ai_blocked": bool(state.ai_blocked),
            "ai_error": ai_error or "",
            "summary": {
                "total": int(state.total_count),
                "adoptable": int(state.adoptable_count),
                "protected": int(state.protected_count),
                "missing": int(state.missing_count),
                "selected_ready": int(state.selected_ready_count),
            },
            "items": analysis_items,
        }
        report_path = report_dir / f"texture_analysis_{utc_timestamp()}.json"
        write_err = _write_json(report_path, payload)
        if write_err:
            state.last_error = f"Failed writing analysis report: {write_err}"
            self.report({"ERROR"}, state.last_error)
            self._runner_result = {"CANCELLED"}
        else:
            state.analysis_report_path = str(report_path)
            if state.ai_blocked:
                self.report(
                    {"WARNING"},
                    (
                        f"Texture analysis completed with AI blocked. Adoptable: {state.adoptable_count}, "
                        f"Protected: {state.protected_count}, Missing: {state.missing_count}."
                    ),
                )
            else:
                self.report(
                    {"INFO"},
                    (
                        f"Texture analysis completed. Adoptable: {state.adoptable_count}, "
                        f"Protected: {state.protected_count}, Missing: {state.missing_count}."
                    ),
                )
            self._runner_result = {"FINISHED"}

        try:
            wm.progress_end()
        except Exception:
            pass
        _mark_busy(state, False)
        return


class LIME_OT_texture_refine(_ModalRunnerMixin, Operator):
    bl_idname = "lime.texture_refine"
    bl_label = "Refine Suggestions (AI)"
    bl_description = "Regenerate texture naming suggestions using user hints and AI"
    bl_options = {"REGISTER"}

    def _run_generator(self, context):
        state = _state_from_context(context)
        if state is None:
            self.report({"ERROR"}, "AI Textures state is unavailable")
            self._runner_result = {"CANCELLED"}
            return
        if not getattr(state, "items", None):
            self.report({"ERROR"}, "No analyzed textures available")
            self._runner_result = {"CANCELLED"}
            return
        if bool(getattr(state, "ai_blocked", False)):
            self.report({"ERROR"}, "AI is currently blocked. Re-run Analyze after fixing connectivity.")
            self._runner_result = {"CANCELLED"}
            return
        if not has_openrouter_api_key():
            state.ai_blocked = True
            state.last_error = "OpenRouter API key not found in .env"
            self.report({"ERROR"}, state.last_error)
            self._runner_result = {"CANCELLED"}
            return

        _mark_busy(state, True)
        state.last_error = ""
        selected_items = [
            item
            for item in list(state.items or [])
            if bool(getattr(item, "selected_for_apply", False))
            and not bool(getattr(item, "read_only", False))
            and (getattr(item, "classification", "") or "").upper() in _ADOPTABLE_CLASSES
        ]
        if not selected_items:
            _mark_busy(state, False)
            self.report({"ERROR"}, "No selected adoptable textures to refine")
            self._runner_result = {"CANCELLED"}
            return

        project_root, local_mode = deduce_project_root(context)
        dest_root = resolve_texture_root_for_context(project_root, local_mode=local_mode)
        project_token = project_token_for_naming(project_root=project_root) or "Project"
        report_dir, err = _make_report_dir(dest_root)
        if err:
            _mark_busy(state, False)
            self.report({"ERROR"}, f"Cannot create manifest folder: {err}")
            self._runner_result = {"CANCELLED"}
            return

        refine_rows: List[Dict[str, object]] = []
        wm = context.window_manager
        total_jobs = max(1, len(selected_items))
        try:
            wm.progress_begin(0, total_jobs)
        except Exception:
            pass

        global_error = ""
        for idx, item in enumerate(selected_items, 1):
            yield None
            try:
                wm.progress_update(idx)
            except Exception:
                pass

            image = getattr(item, "image_ref", None)
            original_name = Path((getattr(item, "abs_filepath", "") or "").strip()).name or (getattr(item, "image_name", "") or "texture.png")
            socket_targets = _socket_targets_from_item(item)
            map_type = (getattr(item, "map_type", "") or "Generic").strip() or "Generic"
            prior = (getattr(item, "refined_suggestion", "") or "").strip() or (getattr(item, "initial_suggestion", "") or "").strip()
            hint = (getattr(item, "hint_text", "") or "").strip()

            ai_box: Dict[str, tuple[str, str | None, str | None, str | None, Dict[str, object] | None, str | None]] = {}

            def _run_ai() -> None:
                try:
                    ai_box["result"] = ai_suggest_texture_name(
                        context=context,
                        original_filename=original_name,
                        material_name=(getattr(item, "materials_summary", "") or "").split(",")[0].strip(),
                        map_type=map_type,
                        socket_targets=socket_targets,
                        manual_hint=hint,
                        prior_suggestion=prior,
                        include_preview=bool(getattr(state, "ai_include_preview", False)),
                        image=image,
                    )
                except Exception as ex:
                    ai_box["result"] = ("", None, None, None, None, f"OpenRouter request failed: {ex}")

            ai_thread = threading.Thread(target=_run_ai, daemon=True)
            ai_thread.start()
            while ai_thread.is_alive():
                try:
                    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
                except Exception:
                    pass
                yield None

            suggested, ai_map_type, explanation, image_summary, preview_meta, ai_err = ai_box.get(
                "result",
                ("", None, None, None, None, "OpenRouter request returned no result"),
            )
            if not suggested:
                global_error = ai_err or "OpenRouter request failed"
                item.status = "AI_BLOCKED"
                item.last_error = global_error
                refine_rows.append(
                    {
                        "item_id": item.item_id,
                        "status": "AI_BLOCKED",
                        "error": global_error,
                    }
                )
                break

            ext = Path((getattr(item, "final_filename", "") or "")).suffix or Path((getattr(item, "abs_filepath", "") or "")).suffix or ".png"
            map_for_name = ai_map_type or map_type
            final_filename = canonical_filename_for_item(
                project_token=project_token,
                source_stem=suggested,
                map_type=map_for_name,
                ext=ext,
            )
            item.refined_suggestion = suggested
            item.final_filename = final_filename
            item.dest_preview_path = str(dest_root / final_filename)
            item.status = "READY"
            item.last_error = ""
            refine_rows.append(
                {
                    "item_id": item.item_id,
                    "status": "READY",
                    "hint": hint,
                    "suggested": suggested,
                    "map_type": map_for_name,
                    "final_filename": final_filename,
                    "ai_explanation": explanation,
                    "ai_image_summary": image_summary,
                    "ai_preview_meta": preview_meta,
                }
            )

        if global_error:
            state.ai_blocked = True
            state.last_error = global_error
            for item in list(state.items or []):
                if bool(getattr(item, "selected_for_apply", False)) and (getattr(item, "status", "") or "").upper() not in {"APPLIED", "SKIPPED"}:
                    item.status = "AI_BLOCKED"
                    if not getattr(item, "last_error", ""):
                        item.last_error = global_error
            self.report({"ERROR"}, f"Refine stopped because AI failed: {global_error}")
        else:
            state.phase = "REFINED"
            self.report({"INFO"}, f"Texture refine completed for {len(refine_rows)} item(s)")

        _update_state_counts(state)

        payload = {
            "generated_at": utc_now_iso(),
            "blend_filepath": (getattr(bpy.data, "filepath", "") or "").strip(),
            "scan_scope": getattr(state, "scan_scope", "ALL_SCENE"),
            "ai_blocked": bool(state.ai_blocked),
            "ai_error": state.last_error if state.ai_blocked else "",
            "items": refine_rows,
        }
        report_path = report_dir / f"texture_refine_{utc_timestamp()}.json"
        write_err = _write_json(report_path, payload)
        if write_err:
            self.report({"ERROR"}, f"Failed writing refine report: {write_err}")
            self._runner_result = {"CANCELLED"}
        else:
            state.refine_report_path = str(report_path)
            self._runner_result = {"CANCELLED"} if global_error else {"FINISHED"}

        try:
            wm.progress_end()
        except Exception:
            pass
        _mark_busy(state, False)
        return


class LIME_OT_texture_apply(_ModalRunnerMixin, Operator):
    bl_idname = "lime.texture_apply"
    bl_label = "Apply Texture Plan"
    bl_description = "Apply selected texture plan entries by copying files and relinking Blender images"
    bl_options = {"REGISTER", "UNDO"}

    def _run_generator(self, context):
        state = _state_from_context(context)
        if state is None:
            self.report({"ERROR"}, "AI Textures state is unavailable")
            self._runner_result = {"CANCELLED"}
            return
        if bool(getattr(state, "ai_blocked", False)):
            self.report({"ERROR"}, "AI is blocked. Re-run Analyze/Refine after restoring AI connectivity.")
            self._runner_result = {"CANCELLED"}
            return
        if not getattr(state, "items", None):
            self.report({"ERROR"}, "No analyzed textures to apply")
            self._runner_result = {"CANCELLED"}
            return

        selected_ready = [
            item
            for item in list(state.items or [])
            if bool(getattr(item, "selected_for_apply", False))
            and (getattr(item, "status", "") or "").upper() == "READY"
            and not bool(getattr(item, "read_only", False))
            and (getattr(item, "classification", "") or "").upper() in _ADOPTABLE_CLASSES
        ]
        if not selected_ready:
            self.report({"ERROR"}, "No selected READY items to apply")
            self._runner_result = {"CANCELLED"}
            return

        _mark_busy(state, True)
        state.last_error = ""

        project_root, local_mode = deduce_project_root(context)
        protected_roots = protected_roots_for_context(context)
        dest_root = resolve_texture_root_for_context(project_root, local_mode=local_mode)
        report_dir, err = _make_report_dir(dest_root)
        if err:
            _mark_busy(state, False)
            self.report({"ERROR"}, f"Cannot create manifest folder: {err}")
            self._runner_result = {"CANCELLED"}
            return

        err = safe_mkdir(dest_root)
        if err:
            _mark_busy(state, False)
            self.report({"ERROR"}, f"Cannot create texture destination folder: {err}")
            self._runner_result = {"CANCELLED"}
            return

        usage_by_image = collect_image_usages_from_materials(getattr(bpy.data, "materials", []) or [])
        hash_to_dest: Dict[str, Path] = {}
        index_path = report_dir / "texture_sha256_index.json"
        sha256_index = read_sha256_index(index_path)

        changes: List[Dict[str, object]] = []
        skipped: List[Dict[str, object]] = []
        relinked_images: Set[int] = set()
        stats = {
            "total_selected_ready": len(selected_ready),
            "adopted": 0,
            "relinked_existing": 0,
            "skipped": 0,
            "errors": 0,
        }

        wm = context.window_manager
        total_jobs = max(1, len(selected_ready))
        try:
            wm.progress_begin(0, total_jobs)
        except Exception:
            pass

        for idx, item in enumerate(selected_ready, 1):
            yield None
            try:
                wm.progress_update(idx)
            except Exception:
                pass

            image = _resolve_image_for_item(item, usage_by_image)
            if image is None:
                item.status = "ERROR"
                item.last_error = "Image datablock not found for this plan item"
                stats["errors"] += 1
                skipped.append(
                    {
                        "item_id": item.item_id,
                        "classification": "IMAGE_NOT_FOUND",
                        "reason": item.last_error,
                    }
                )
                continue

            raw_filepath = (getattr(image, "filepath", "") or "").strip()
            source_kind = (getattr(image, "source", "") or "").upper()
            abs_path, path_reasons = resolve_abs_image_path(image)
            exists = exists_for_scan(abs_path, raw_filepath=raw_filepath)
            usages = []
            try:
                key = int(image.as_pointer())
                usages = usage_by_image.get(key, (None, []))[1]
            except Exception:
                pass

            classification, reasons = infer_scan_classification(
                image=image,
                usages=usages,
                abs_path=abs_path,
                raw_filepath=raw_filepath,
                exists=exists,
                project_root=project_root,
                protected_roots=protected_roots,
                dest_root=dest_root,
            )
            reasons = list(path_reasons) + list(reasons)
            if classification not in _ADOPTABLE_CLASSES:
                item.status = "SKIPPED"
                item.last_error = reasons[0] if reasons else f"Skipped ({classification})"
                stats["skipped"] += 1
                skipped.append(
                    {
                        "item_id": item.item_id,
                        "classification": classification,
                        "reasons": reasons,
                    }
                )
                continue

            if abs_path is None or not os.path.isfile(str(abs_path)):
                item.status = "ERROR"
                item.last_error = "Resolved source file does not exist"
                stats["errors"] += 1
                skipped.append(
                    {
                        "item_id": item.item_id,
                        "classification": "MISSING",
                        "reasons": ["Resolved source file does not exist"],
                    }
                )
                continue

            try:
                digest, byte_count = sha256_file(abs_path)
            except Exception as ex:
                item.status = "ERROR"
                item.last_error = f"Failed hashing file: {ex}"
                stats["errors"] += 1
                skipped.append(
                    {
                        "item_id": item.item_id,
                        "classification": "HASH_ERROR",
                        "reasons": [item.last_error],
                    }
                )
                continue

            filename_raw = (getattr(item, "final_filename", "") or "").strip()
            stem = sanitize_filename_stem(Path(filename_raw).stem) or sanitize_filename_stem(abs_path.stem) or "Texture"
            ext = (abs_path.suffix or ".png").lower()
            filename = f"{stem}{ext}"

            existing = hash_to_dest.get(digest)
            if existing is None:
                indexed = (sha256_index.get(digest) or "").strip()
                if indexed:
                    candidate = dest_root / indexed
                    if candidate.exists():
                        existing = candidate

            if existing is not None:
                dest_path = existing
                action = "RELINK_EXISTING"
            else:
                dest_path = unique_destination(dest_root, filename, digest)
                try:
                    copy_texture_file(abs_path, dest_path)
                except Exception as ex:
                    item.status = "ERROR"
                    item.last_error = f"Failed copying file: {ex}"
                    stats["errors"] += 1
                    skipped.append(
                        {
                            "item_id": item.item_id,
                            "classification": "COPY_ERROR",
                            "reasons": [item.last_error],
                        }
                    )
                    continue
                try:
                    if not dest_path.exists():
                        raise FileNotFoundError("Destination file not found after copy")
                    if dest_path.stat().st_size != int(byte_count):
                        raise OSError("Destination file size mismatch after copy")
                except Exception as ex:
                    item.status = "ERROR"
                    item.last_error = f"Copy verification failed: {ex}"
                    stats["errors"] += 1
                    skipped.append(
                        {
                            "item_id": item.item_id,
                            "classification": "COPY_VERIFY_FAILED",
                            "reasons": [item.last_error],
                        }
                    )
                    continue
                action = "COPIED"

            hash_to_dest[digest] = dest_path
            sha256_index[digest] = dest_path.name

            try:
                img_key = int(image.as_pointer())
            except Exception:
                img_key = id(image)

            if img_key not in relinked_images:
                blender_path, rel_reasons = relpath_for_blender(dest_path, project_root=project_root)
                try:
                    image.filepath = blender_path
                    try:
                        image.filepath_raw = blender_path  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    image.name = dest_path.stem
                    image.reload()
                    relinked_images.add(img_key)
                except Exception as ex:
                    item.status = "ERROR"
                    item.last_error = f"Failed relinking image: {ex}"
                    stats["errors"] += 1
                    skipped.append(
                        {
                            "item_id": item.item_id,
                            "classification": "RELINK_ERROR",
                            "reasons": [item.last_error],
                        }
                    )
                    continue
            else:
                blender_path, rel_reasons = relpath_for_blender(dest_path, project_root=project_root)

            item.status = "APPLIED"
            item.last_error = ""
            item.dest_preview_path = str(dest_path)
            if action == "COPIED":
                stats["adopted"] += 1
            else:
                stats["relinked_existing"] += 1

            changes.append(
                {
                    "item_id": item.item_id,
                    "image_name": getattr(image, "name", "") or "",
                    "image_source": source_kind,
                    "original_raw_filepath": raw_filepath,
                    "original_abs_filepath": str(abs_path),
                    "content_sha256": digest,
                    "bytes": int(byte_count),
                    "action": action,
                    "dest_abs_filepath": str(dest_path),
                    "dest_blender_filepath": blender_path,
                    "relpath_notes": rel_reasons,
                }
            )

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "blend_filepath": (getattr(bpy.data, "filepath", "") or "").strip(),
            "blend_dir": str(blend_dir()),
            "project_root": str(project_root) if project_root is not None else None,
            "texture_root": str(dest_root),
            "scan_scope": getattr(state, "scan_scope", "ALL_SCENE"),
            "stats": stats,
            "changes": changes,
            "skipped": skipped,
        }
        manifest_path = report_dir / f"texture_apply_{utc_timestamp()}.json"
        write_err = _write_json(manifest_path, payload)
        if write_err:
            self.report({"ERROR"}, f"Failed writing texture apply manifest: {write_err}")
            self._runner_result = {"CANCELLED"}
        else:
            try:
                write_sha256_index(index_path, sha256_index)
            except Exception:
                pass
            state.apply_manifest_path = str(manifest_path)
            state.phase = "APPLIED"
            self.report(
                {"INFO"},
                (
                    f"Texture apply complete. Copied: {stats['adopted']}, Relinked existing: {stats['relinked_existing']}, "
                    f"Skipped: {stats['skipped']}, Errors: {stats['errors']}."
                ),
            )
            self._runner_result = {"FINISHED"}

        _update_state_counts(state)
        try:
            wm.progress_end()
        except Exception:
            pass
        _mark_busy(state, False)
        return


class LIME_OT_texture_clear_session(Operator):
    bl_idname = "lime.texture_clear_session"
    bl_label = "Clear Texture Session"
    bl_description = "Clear current AI Textures Organizer session state"
    bl_options = {"REGISTER"}

    def execute(self, context):
        state = _state_from_context(context)
        if state is None:
            self.report({"ERROR"}, "AI Textures state is unavailable")
            return {"CANCELLED"}
        if bool(getattr(state, "is_busy", False)):
            self.report({"WARNING"}, "Cannot clear while an operation is running")
            return {"CANCELLED"}
        _reset_state(state)
        self.report({"INFO"}, "Texture session cleared")
        return {"FINISHED"}


__all__ = [
    "LIME_OT_texture_analyze",
    "LIME_OT_texture_refine",
    "LIME_OT_texture_apply",
    "LIME_OT_texture_clear_session",
]

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
REPO_PARENT = ROOT.parent
if str(REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(REPO_PARENT))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _make_temp_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.new("LP_Smoke_Image", width=4, height=4, alpha=True)
    try:
        image.filepath_raw = path.as_posix()
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def run() -> dict[str, object]:
    report: dict[str, object] = {
        "blender_version": bpy.app.version_string,
        "repo_root": str(ROOT),
        "checks": [],
    }

    import lime_pipeline

    report["checks"].append("import lime_pipeline")
    lime_pipeline.register()
    report["checks"].append("register addon")

    wm_state = getattr(bpy.context.window_manager, "lime_pipeline", None)
    _assert(wm_state is not None, "WindowManager.lime_pipeline was not registered")

    scene = bpy.context.scene
    ai_state = getattr(scene, "lime_ai_render", None)
    _assert(ai_state is not None, "Scene.lime_ai_render was not registered")
    report["checks"].append("property groups registered")

    seq = scene.sequence_editor_create()
    _assert(seq is not None, "Failed to create sequence editor")
    strips = getattr(seq, "strips", None)
    strips_all = getattr(seq, "strips_all", None)
    _assert(strips is not None, "SequenceEditor.strips not available in Blender 5")
    _assert(strips_all is not None, "SequenceEditor.strips_all not available in Blender 5")
    report["checks"].append("sequence editor strips API available")

    temp_png = ROOT / "tools" / "_tmp_blender5_smoke.png"
    _make_temp_image(temp_png)
    strip = strips.new_image(name="LP_SMOKE", filepath=temp_png.as_posix(), channel=1, frame_start=1)
    _assert(strip is not None, "Failed to create image strip through strips API")
    report["checks"].append("create strip with strips.new_image")

    fmt = scene.render.image_settings
    _assert(hasattr(fmt, "media_type"), "ImageFormatSettings.media_type not available")
    fmt.media_type = "IMAGE"
    report["checks"].append("image_settings.media_type")

    from lime_pipeline.ops.ops_alpha_manager import create_event, evaluate_event

    event = create_event(scene, "Smoke")
    event.frame_start = 1
    event.frame_end = 11
    value_mid = evaluate_event(scene, event, 6.0)
    _assert(abs(value_mid - 0.5) < 1e-6, f"Unexpected alpha interpolation value: {value_mid}")
    _assert(event.slug in scene, "Alpha event scene property was not created")
    report["checks"].append("alpha event evaluation without legacy fcurves")

    from lime_pipeline.ops.ops_dimensions import enable_dimension_live_updates, disable_dimension_live_updates
    from lime_pipeline.ops.ops_auto_camera_bg import ensure_auto_bg_live_updates

    enable_dimension_live_updates()
    disable_dimension_live_updates()
    ensure_auto_bg_live_updates(scene=scene, force_update=False)
    report["checks"].append("handlers callable in Blender 5")

    lime_pipeline.unregister()
    report["checks"].append("unregister addon")

    try:
        temp_png.unlink(missing_ok=True)
    except Exception:
        pass

    return report


if __name__ == "__main__":
    try:
        result = run()
        print("LIME_PIPELINE_BLENDER5_SMOKE_OK")
        print(json.dumps(result, indent=2, sort_keys=True))
    except Exception as exc:
        print("LIME_PIPELINE_BLENDER5_SMOKE_FAILED")
        print(str(exc))
        traceback.print_exc()
        raise

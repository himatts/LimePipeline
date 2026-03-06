---
name: blender-dev-reload-addons-terminal
description: Audit what Blender Development executes for `Blender: Reload Addons` and trigger the same reload flow from terminal for Blender 5.0.
---

# Blender Development `Reload Addons` (Terminal)

## Goal
Understand and reproduce `Blender: Reload Addons` in Blender 5.0 without using the VS Code command.

## Source of truth
1) `out/extension.js`
- `COMMAND_reloadAddons` saves files and sends `{ type: "reload", names, dirs }` to responsive Blender instances.
2) `pythonFiles/include/blender_vscode/operators/addon_update.py`
- Registers handler for `"reload"`.
- Resolves addon module names (legacy/extension paths).
- Calls `bpy.ops.dev.update_addon(module_name=...)`.
3) `UpdateAddonOperator.execute`
- `bpy.ops.preferences.addon_disable(...)`
- Deletes addon modules from `sys.modules`
- `bpy.ops.preferences.addon_enable(...)`
- Sends `"addonUpdated"` callback.

## Workflow
1) Ensure target Blender instance is running and has the Blender Development HTTP server active.
2) Prepare reload payload:
- `names`: module names (for Lime Pipeline: `lime_pipeline`).
- `dirs`: source directories (absolute path to addon package directory).
3) POST the payload to the Blender server endpoint.
4) Validate addon re-enabled and UI/operators available.

## Command
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" tools\blender_dev_reload_http.py --port <BLENDER_SERVER_PORT> --module-name lime_pipeline --source-dir "C:\Users\Usuario\Documents\Blender Addons\LimePipeline\lime_pipeline"
```

## Port discovery
- If started by Blender Development, inspect the VS Code output channel for `Flask server started on port ...`.
- Verify reachability:
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:<BLENDER_SERVER_PORT>/ping"
```

## Validation
- Reload request returns HTTP 200.
- Blender console shows disable/enable cycle without exceptions.
- Addon panels/operators remain available after reload.

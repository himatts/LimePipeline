---
name: blender-dev-start-terminal
description: Audit what Blender Development executes for `Blender: Start` and run an equivalent Blender 5.0 terminal flow without relying on the VS Code command.
---

# Blender Development `Start` (Terminal)

## Goal
Understand and reproduce `Blender: Start` for Blender 5.0 from terminal commands/scripts.

## Source of truth
1) `out/extension.js`
- `COMMAND_start` delegates to launch helpers.
2) `out/blender_executable.js`
- Builds process execution: `blender.exe --python <launch.py>`.
- Exports env vars: `ADDONS_TO_LOAD`, `EDITOR_PORT`, `VSCODE_*`.
3) `pythonFiles/launch.py`
- Parses `ADDONS_TO_LOAD`, then calls `blender_vscode.startup(...)`.
4) `pythonFiles/include/blender_vscode/__init__.py`
- Installs requirements, links addon/extension path, starts communication/debug server, registers dev operators, enables addon.

## Workflow
1) Confirm Blender Development extension version/path in the user profile.
2) Confirm workspace addon path and module name.
3) Choose one terminal replication mode:
- `direct` (recommended): load/register addon directly for interactive work.
- `blender-development` (parity mode): run the extension `launch.py` with the same env contract.
4) Execute `tools/blender_dev_start.py` with Blender 5.0 path.
5) Verify addon loaded in console/logs.

## Commands
Direct mode (recommended, no VS Code server dependency):
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" tools\blender_dev_start.py --mode direct --blender-exe "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
```

Parity mode (matches Blender Development startup contract):
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" tools\blender_dev_start.py --mode blender-development --editor-port 17342 --blender-exe "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
```

## Validation
- Startup log includes: `[Lime Pipeline] Loading addon from: ...`
- `addon_utils.check("lime_pipeline")` returns loaded `True`.
- No path corruption in `%APPDATA%\Blender Foundation\Blender\5.0\scripts\addons\lime_pipeline`.

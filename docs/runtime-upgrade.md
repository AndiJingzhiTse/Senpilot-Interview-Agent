# Windows runtime migration

On October 28, 2026, the active SenpilotAgent task was migrated from Python 3.10.11 to **Python 3.12.16**.
The new environment was built beside the old one. The original `.venv` and task XML backup remain available for rollback.

## Preparation

The migration used uv 0.13.6 installed inside ignored `artifacts/tooling/uv`, and uv's managed CPython distribution.
The commands below reproduce the local layout from the repository root using the original environment as bootstrap:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-deps --target artifacts/tooling/uv uv==0.13.6
& .\artifacts\tooling\uv\bin\uv.exe python install 3.12.16 --install-dir artifacts/runtime/python --no-bin --no-registry --cache-dir artifacts/tooling/cache --no-config
& .\artifacts\tooling\uv\bin\uv.exe venv --python artifacts/runtime/python/cpython-3.12.16-windows-x86_64-none/python.exe --seed artifacts/runtime/venv --cache-dir artifacts/tooling/cache --no-config
& .\artifacts\tooling\uv\bin\uv.exe pip install --python artifacts/runtime/venv/Scripts/python.exe -r requirements-dev.txt --cache-dir artifacts/tooling/cache --no-config
```

These are initial preparation commands for a fresh target directory; do not recreate an environment while its task is running.
No default Python, PATH entry, or Windows Python registry registration was changed. See uv's [managed Python guide](https://docs.astral.sh/uv/guides/install-python/).
Python's [version status](https://devguide.python.org/versions/) identifies 3.12 as maintained at the review date.

## Verification and handover

The new environment passed the regression suite, dependency checks, Chrome checks, Gmail profile access, and a real DeepSeek extraction request.
The live queue was idle before handover. Its existing five sends and their attempt counts and Gmail message IDs were preserved.

The task definition was exported to ignored `artifacts/deployment/task-before-python312.xml`. The old task was stopped and its action updated:

```powershell
.\deploy\windows\Register-AgentTask.ps1 -Config deploy/agent.json -PythonPath artifacts/runtime/venv/Scripts/python.exe -Update -Start
```

The update action verifies that the existing task belongs to this project and configuration. It changes the executable action while preserving the trigger and other task settings.
Preflight refuses a live worker lock. Runtime updates wait briefly and retry only a busy lock result; configuration failures do not trigger that retry.
The first stop returned before the old process had released its locks. Preflight correctly refused overlap; the update succeeded after the process finished.

The active heartbeat now records Python 3.12.16 and the new `pythonw.exe` path. The new startup polled Gmail successfully without the earlier unsupported Python warning.
Detailed checks remain in ignored `artifacts/deployment/python312-provider-check.json`, `python312-before.json`, and `python312-activation.json`.

## Current operation and rollback

```powershell
$senpilotPython = '.\artifacts\runtime\venv\Scripts\python.exe'
& $senpilotPython -m senpilot.service --config deploy/agent.json --health
```

If a rollback is needed, first stop the task and wait for its worker to exit. Update the task action to the retained original interpreter:

```powershell
.\deploy\windows\Register-AgentTask.ps1 -Config deploy/agent.json -PythonPath .venv/Scripts/python.exe -Update -Start
```

The queue, OAuth token, key file, and downloaded artifacts are shared with the existing configuration. They are not replaced during a runtime change.
The old interpreter is an operational rollback option, not the recommended runtime for a new installation.

# Deployment validation

Checks were performed on October 28, 2026, America/Toronto. The existing terminal worker was not stopped, replaced, or used to send additional requests during this work.

## Live evidence audit

The existing live queue contained these confirmed Gmail send records:

| Request | Documents | ZIP bytes | Encoded message bytes |
| --- | ---: | ---: | ---: |
| M12205 Other Documents | 10 | 10371745 | 14194463 |
| M12383 Other Documents | 10 | 7111283 | 9732756 |
| Request requiring clarification | 0 | No ZIP | 587 |

For both document replies, the saved MIME message matched its journal size and SHA256, addressed andi.xie24@gmail.com from andi.xie241@gmail.com, and contained exactly one ZIP attachment.
The decoded ZIP matched its package hash. All ten archived document hashes and sizes matched the saved source files, and the archive contained eleven entries including its manifest.
The clarification reply had no attachment. All three journal rows contained a Gmail sent message ID.
Andi reported that live handling and receipt worked. Recipient inbox contents were not independently fetched in this audit. The earlier journal did not record the extraction mode; new jobs now retain that setting.
The detailed audit remains in the ignored `artifacts/deployment/live-audit.json` file.

## Local checks

The full suite ran 78 tests: 77 passed and one existing filesystem symlink test was skipped because this Windows session does not permit creating symbolic links.

- A real Python process acquired the OS worker lock, was forcibly terminated, and a new process could acquire that lock without deleting its file.
- A competing process was refused while the owner remained alive.
- The old lock format was refused without changing or deleting the legacy file.
- Interrupted processing was requeued within its attempt limit; exhausted work failed explicitly; prepared and confirmed sends remained intact; interrupted sends became uncertain.
- The supervisor restarted a simulated failed worker, enforced its restart budget, and preserved pauses without making additional provider calls.
- The configured key was removed from captured log output, log rotation stayed bounded, and the previous process environment was restored after supervision.
- Local health distinguished running, paused, failed, stopped, and stale states.
- Real preflight commands launched only blank Chrome through both the normal Python executable and `pythonw.exe`. Synthetic credentials were used, with no Gmail, DeepSeek, or source website calls.
- The Windows task script passed PowerShell parsing and a real `-WhatIf` invocation. No task was registered.
- Compose passed validation using the official Compose schema. The schema snapshot hash was `d549057ebc2925f39f62799eab0db7b9e2c18b35b6c00595199116da3ed10e64`.

Run local checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/check_deployment.py
```

The schema checker fetches the public specification and caches it under `artifacts/deployment/`.
For offline repetition, pass `--schema artifacts/deployment/compose-schema.json`.

## Limits and pending checks

The local environment is Windows with Python 3.10.11 and installed Chrome. The new image targets Linux amd64 and Python 3.12.
Docker is absent here, so the image has not been built or executed. The POSIX lock branch, Linux dependency installation, and mounted file permissions still need validation on that target.
The scheduled task has not been registered, so actual logon startup and Task Scheduler restart behavior remain pending.
Application recovery tests do not establish availability during host failure, expired provider grants, disk exhaustion, or an operator's intentional shutdown.
No host has been purchased or provisioned, and no deployment has replaced the user's current worker.

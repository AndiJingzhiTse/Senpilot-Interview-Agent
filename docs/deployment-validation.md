# Deployment validation

Checks were performed on October 28, 2026, America/Toronto. Packaging checks left the original terminal worker untouched. During the subsequent authorized Windows activation, Andi stopped that worker and saved the key locally.

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
The scheduled task has since been registered and started. Background startup, a controlled task restart, and a fresh request through to a confirmed Gmail send passed. An actual logoff or reboot and a forced crash of the installed task were not performed.
Application recovery tests do not establish availability during host failure, expired provider grants, disk exhaustion, or an operator's intentional shutdown.
No remote host has been purchased or provisioned. The local task now replaces the former terminal worker.

## Windows activation

Task **SenpilotAgent** runs through the project's `pythonw.exe` under the current Windows user. Its enabled trigger is user logon.
Settings were read back from Task Scheduler: five failure restarts with a one minute interval, no execution time limit, and IgnoreNew for additional instances.

The actual local preflight passed with Chrome 155.0.8059.85. Service health reported running, and the first poll preserved all three existing sent records.
A controlled Stop-ScheduledTask operation stopped both Python processes. The next local preflight could acquire the state locks, and Start-ScheduledTask started a new healthy process.
All three original Gmail message IDs and processing attempt counts remained unchanged. Details are saved in ignored `artifacts/deployment/windows-activation.json`.

The background Google client emitted a Python 3.10.11 support warning. It did not prevent startup or polling, but native runtime migration remains a followup.

## Fresh background request

Andi sent a new request for M12205 Other Documents to the agent inbox. The Windows task processed it without a terminal worker, using the recorded `deepseek` extractor and `deepseek-flash` model.
The job completed on its first processing attempt with ten documents and zero download failures, and Gmail returned a sent message ID.

The attached ZIP contained 6686350 bytes; the encoded email contained 9151294 bytes. Its From and To addresses matched the configured agent and requester.
The saved MIME message and decoded attachment matched their recorded hashes. The archive contained ten documents plus its manifest, and every archived document matched the size and SHA256 of its saved source file.
The source now listed 44 Other Documents rather than the earlier 43, and the catalog included a new document in the selected ten. The new run used these actual source counts.
The service remained healthy after the send. Detailed evidence is in ignored `artifacts/deployment/background-email-test.json`.

This verifies processing and Gmail acceptance under the background task. Receipt and opening of this particular reply have not been independently confirmed in the recipient inbox.

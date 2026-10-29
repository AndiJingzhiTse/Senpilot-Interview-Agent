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

Initial packaging checks used Windows with Python 3.10.11 and installed Chrome. The active native environment has since been migrated to Python 3.12.16. The image targets Linux amd64 and Python 3.12.
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

The original background environment emitted a Python 3.10.11 support warning. The subsequent migration to Python 3.12.16 removed that warning from the new startup.

## Fresh background request

Andi sent a new request for M12205 Other Documents to the agent inbox. The Windows task processed it without a terminal worker, using the recorded `deepseek` extractor and `deepseek-flash` model.
The job completed on its first processing attempt with ten documents and zero download failures, and Gmail returned a sent message ID.

The attached ZIP contained 6686350 bytes; the encoded email contained 9151294 bytes. Its From and To addresses matched the configured agent and requester.
The saved MIME message and decoded attachment matched their recorded hashes. The archive contained ten documents plus its manifest, and every archived document matched the size and SHA256 of its saved source file.
The source now listed 44 Other Documents rather than the earlier 43, and the catalog included a new document in the selected ten. The new run used these actual source counts.
The service remained healthy after the send. Detailed evidence is in ignored `artifacts/deployment/background-email-test.json`.

Andi subsequently confirmed that this reply arrived and that the ZIP opened successfully. This completes the reported recipient check for the background request; the inbox was not independently fetched by the agent.

## Runtime migration and final review

Python 3.12.16 was installed beside the existing environment, with the same pinned application dependencies.
The latest suite ran 79 tests: 78 passed and the existing Windows symlink test was skipped. Dependency and Compose schema checks passed.
Live Gmail profile access and a real DeepSeek request extraction were verified under the new interpreter before handover. No synthetic email request was sent for that provider check.

The task action was changed only after the queue was idle. All five existing sends retained their Gmail IDs and processing attempt counts.
The new heartbeat records Python 3.12.16 and `artifacts/runtime/venv/Scripts/pythonw.exe`, and Gmail polling resumed successfully.
The original task XML and Python 3.10 environment remain available for rollback. See [runtime migration](runtime-upgrade.md).

Andi chose to keep the current oversized ZIP notice and explicitly disclose the resulting attachment limitation. The [requirements review](requirements-review.md) and [demo guide](demo.md) form the handoff record.

## Requests from any sender

On October 28, 2026, Andi requested intake from any email address. The service now uses `accept_any_sender: true` and an empty `allowed_senders` list.
The CLI requires an explicit sender policy. Inbox polling, processing, and reply sending all use that policy; an empty restricted list never enables unrestricted intake.
Replies still target the original From address, and automatic messages, bulk mail, malformed senders, and self messages retain their existing exclusions.

The full suite ran 85 tests: 84 passed and the existing Windows symlink test was skipped.
New tests cover a new customer address through mocked Gmail intake, retrieval, ZIP preparation, and a single confirmed send, including restart deduplication and a Reply-To redirection attempt.
Other checks cover the unrestricted Gmail query, empty restricted lists, explicit CLI and JSON configuration, and message exclusions in unrestricted mode.

The idle Windows task was stopped, its configuration updated, local preflight passed, and the task restarted.
Its fresh heartbeat confirmed `sender_policy: any`, Python 3.12.16, and healthy running status. Previously excluded unread messages entered the queue.
Activation snapshots are saved in ignored `artifacts/deployment/any-sender-before.json` and `artifacts/deployment/any-sender-activation.json`.
Recipient receipt from a new address has not yet been confirmed for this change.

## Intake repair and missing requests

The first unrestricted implementation had an intake defect: it scanned all unread historical Inbox mail. It sent 426 clarification replies to unrelated historical messages beyond the five original test sends.
The worker was stopped after investigation. The queue was backed up, all sent records retained, and 19 unsent historical or unrelated jobs marked ignored with repair reasons. No emails were deleted, relabelled, or recalled.

The repaired worker persists the first intake timestamp in SQLite. An explicit `received_after` setting supports controlled catchup; the active deployment uses October 28, 2026, at midnight in Toronto.
Gmail queries and metadata receipt timestamps both enforce the boundary. Subscription mail, obvious automated sender addresses, and messages without document request cues are ignored before extraction.
The watcher processes one queued job at a time, sends its reply immediately, and polls on its regular cadence rather than draining a historical batch first.

The suite ran 91 tests: 90 passed and the existing Windows symlink test was skipped. New checks cover persistent receipt boundaries, old metadata exclusion, unrelated mail, partial request clarification, automated sender exclusions, and sending a reply before the next retrieval.
Local preflight passed and the restarted Windows task reported healthy status with unrestricted sender intake. The initial repaired queue contained 114 ignored records and 431 confirmed sends, with no pending or prepared historical jobs.
Repair evidence and a private queue backup are under ignored `artifacts/deployment/intake-repair*` paths.

The two missing requests from andi.xie242@gmail.com were found in Spam, outside the worker's Inbox query. Both request M12205 Other Documents and pass local request parsing.
The agent's read and send scopes cannot move them. Andi was asked to select Not spam in the agent mailbox and leave them unread in the Inbox; recipient receipt remains unconfirmed until that step and processing complete.

# Deployment

The service wrapper runs the existing Gmail worker with a persistent queue, rotating logs, recovery after crashes, and a local health heartbeat.
It can run as a Windows task or inside the supplied Linux container. Only one installation should actively process the agent mailbox.

The package is prepared. No background task has been registered and no container has been launched by this milestone.
The existing terminal worker remains under Andi Tse's control.

## Local configuration and key storage

An ignored `deploy/agent.json` was prepared here from `deploy/agent.example.json`. On another checkout, copy the example first.
Paths in this JSON are resolved relative to the configuration file. The example reuses the current live queue and OAuth token:

- Agent mailbox: andi.xie241@gmail.com.
- Allowed requester: andi.xie24@gmail.com.
- Queue and documents: `artifacts/email/live/`.
- Gmail token: `artifacts/oauth/token.json`.
- DeepSeek key file: `artifacts/deploy/deepseek.key`.

Before activation, stop the existing terminal worker with Ctrl+C and wait for it to exit.
In a terminal where `DEEPSEEK_API_KEY` is already set, save that key without displaying it:

```powershell
.\.venv\Scripts\python.exe -m senpilot.service --config deploy/agent.json --store-key
```

If the environment variable is absent, the command prompts privately for the key. It refuses to overwrite an existing key file.
The key stays outside Git and is never passed as a command argument. A background task can read this file without inheriting a terminal's environment.

Run the local preflight:

```powershell
.\.venv\Scripts\python.exe -m senpilot.service --config deploy/agent.json --check
```

It checks the key source, token structure and scopes, exclusive state locks, and a blank Chrome launch.
It does not validate the key against DeepSeek, refresh Gmail access, retrieve documents, or send mail.
An old running worker's legacy lock is rejected. Stop that worker normally; do not delete its lock while it runs.

## Windows background task

The supplied task uses the existing virtual environment and installed Chrome. It starts at the current Windows user's logon and can restart after a process failure.
It runs through `pythonw.exe`, so an open terminal is unnecessary. The computer must remain awake and connected, and this setup does not start before user logon.

First inspect the registration without changing Task Scheduler:

```powershell
.\deploy\windows\Register-AgentTask.ps1 -Config .\deploy\agent.json -WhatIf
```

To register it and start it immediately:

```powershell
.\deploy\windows\Register-AgentTask.ps1 -Config .\deploy\agent.json -Start
```

Registration runs the preflight first and refuses to replace an existing task with the same name.
If Windows denies registration, use an account or shell permitted to create that user's scheduled tasks.

```powershell
Get-ScheduledTaskInfo -TaskName SenpilotAgent
Stop-ScheduledTask -TaskName SenpilotAgent
Start-ScheduledTask -TaskName SenpilotAgent
```

To remove the registration after stopping it:

```powershell
Unregister-ScheduledTask -TaskName SenpilotAgent -Confirm:$false
```

These commands do not remove queue history or downloaded files. Microsoft documents the task's [restart and execution settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).
The existing Windows environment is Python 3.10.11; it was used for local compatibility tests. The new server image targets Python 3.12, which is still maintained according to Python's [version status](https://devguide.python.org/versions/).

## Linux container

The container targets Linux amd64, installs Python 3.12, the pinned email dependencies, Google Chrome, and browser system dependencies.
It runs as UID 1000 without root privileges. The build copies source and dependency manifests only; credentials, key files, downloads, and queue data are not copied into the image.
Chrome installation follows Playwright's [browser installation](https://playwright.dev/python/docs/browsers) guidance.

The Compose definition mounts:

| Host path, relative to the repository | Container path | Purpose |
| --- | --- | --- |
| artifacts/email/live | /data | Persistent queue, replies, archives, logs, and heartbeat |
| artifacts/oauth | /oauth | Gmail token and atomic token refresh writes |
| artifacts/deploy/deepseek.key | /run/secrets/deepseek_api_key | Read only secret file |

Stop the existing worker before copying these directories to another host. Preserve the entire queue directory, including the database and job files, to retain duplicate detection.
Use a local persistent filesystem on one host. Locks do not coordinate independent copies of the queue, and two active hosts can process the same mailbox twice.
On Linux, the mounted data and OAuth directories must be writable by UID 1000, and the key must be readable by that user inside the container.
The OAuth directory is writable because token refresh saves a temporary file and atomically replaces the token.

From the repository root on a machine with Docker:

```text
docker compose -f deploy/compose.yaml build
docker compose -f deploy/compose.yaml run --rm agent --check
docker compose -f deploy/compose.yaml up -d
docker compose -f deploy/compose.yaml logs -f --tail 50
docker compose -f deploy/compose.yaml ps
```

The entrypoint already supplies the service command and configuration. The `--check` argument adds the local preflight action.
The service uses Docker init, a 60 second stop grace period, shared memory allocation for Chrome, bounded container logs, and `unless-stopped` restart behavior. See the [Compose service reference](https://docs.docker.com/reference/compose-file/services/).

Stop it with:

```text
docker compose -f deploy/compose.yaml stop
```

The bind mounted state remains intact. Starting it again reuses the same queue.
The Docker daemon must itself start on host boot for container restart policies to apply.

Docker is not installed in the current workspace environment. Compose passed validation against the official schema, but image construction and Linux execution remain pending on the chosen host.
After building there, run the suite inside the image before enabling live processing:

```text
docker compose -f deploy/compose.yaml run --rm --entrypoint python -v "$PWD/tests:/tests:ro" agent -m unittest discover -s /tests -v
```

Host selection should provide an ongoing background process, Chrome support, persistent writable storage, and outbound HTTPS access.
Recordings need substantial disk capacity: ten files comparable to the observed 472 MB sample would use about 4.7 GB before ZIP packaging. Existing artifacts are not automatically deleted.

## Health and logs

```powershell
.\.venv\Scripts\python.exe -m senpilot.service --config deploy/agent.json --health
Get-Content artifacts/email/live/service/worker.log -Tail 30
```

`service/heartbeat.json` updates about every five seconds. The health command succeeds only for a running service with a heartbeat no older than 30 seconds.
Logs use JSON lines with UTC timestamps and rotate at 5 MB, retaining three backups. The configured DeepSeek key is redacted from captured worker output.
Queue summaries contain counts rather than incoming email bodies. New job records retain the extraction mode and configured model for troubleshooting.
Health measures local service liveness and recorded queue problems; it does not prove that Gmail, DeepSeek, the website, or recipient delivery is currently available.
Docker health checks report unhealthy status but do not independently restart a running unhealthy container.

## Recovery behavior

- OS locks are released when the Python process exits, including a hard crash. The lock files remain on disk; their existence does not mean a worker is active. Do not delete them to bypass a running worker.
- On service startup, interrupted `processing` jobs can be requeued up to three processing attempts. Retries use fresh attempt directories.
- `prepared` replies stay available, and confirmed `sent` jobs are never requeued.
- An interrupted `sending` state becomes `send_uncertain`. The service waits for operator reconciliation and never automatically resends it.
- A recognized site block preserves the queue pause and prevents additional provider processing until the operator resolves it.
- Unexpected worker exits use increasing restart delays, with five retries by default. A worker that ran for at least five minutes resets that retry budget.
- A missing key, invalid token, or exhausted retry budget leaves the service in attention status without continually retrying provider calls. Restart after resolving the cause. A missing or malformed service JSON exits with a configuration error instead.

For queue retry and site pause commands, see the [email setup guide](email-setup.md).
OAuth grants can expire or be revoked; reauthorize locally when needed, then replace the server token while its worker is stopped.
The existing oversized archive policy still applies. Deployment does not add hosted file delivery or increase email attachment limits.

## Remaining host acceptance

Choose Windows activation or a Linux host. Then verify an actual background startup, a new email request, its received attachment, and recovery after a controlled restart on that target.
The [validation record](deployment-validation.md) distinguishes the local checks from target checks still pending.

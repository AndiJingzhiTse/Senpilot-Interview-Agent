# Demo and evaluator handoff

Maintainer: Andi Tse. The [requirements review](requirements-review.md) records coverage and the known attachment limitation.

## Existing live demonstration

The configured agent mailbox is **andi.xie241@gmail.com**. It accepts requests from any sender; **andi.xie24@gmail.com** is the original test requester.
It runs as Windows task **SenpilotAgent**, starting at user logon. The computer must remain awake, online, and signed in.

Evaluators can email the agent directly without registering their addresses. The active sender configuration is:

```json
"accept_any_sender": true,
"allowed_senders": []
```

Replies go to the original From address. No recipient address is selected by the AI model.
The evaluator does not need Gmail OAuth authorization to email the existing agent. OAuth belongs to the agent mailbox.

## Demonstration sequence

1. Show that the task is running and its heartbeat is current.
2. From any address, send a new email to the agent with: “Can you give me Other Documents files from M12205?”
3. Leave the request unread in the agent inbox until the worker polls it. If Gmail placed it in Spam, select **Not spam** in the agent mailbox first. The default polling interval is 60 seconds; processing time depends on the website and files.
4. Show the resulting reply with matter metadata, all five category counts, downloaded and skipped counts, and the ZIP attachment.
5. Open the ZIP and its manifest. There are at most ten retrieved documents plus the manifest. Original names and file hashes are listed there.

The validated snapshot had 44 Other Documents, and ten were downloaded. Treat that as observed evidence rather than a fixed expected count: the website can change.

Useful operator commands in the current configured checkout:

```powershell
$senpilotPython = '.\artifacts\runtime\venv\Scripts\python.exe'
Get-ScheduledTask -TaskName SenpilotAgent
& $senpilotPython -m senpilot.service --config deploy/agent.json --health
Get-Content artifacts/email/live/service/heartbeat.json
Get-Content artifacts/email/live/service/worker.log -Tail 20
```

Use the heartbeat to view active queue counts. The separate email CLI's `--status` action needs the worker lock, so use it after stopping the worker.
Keep credential files and key values out of the demonstration. The service log captures progress rather than incoming email bodies.

## Boundary demonstrations

| Case | Input | Expected behavior |
| --- | --- | --- |
| Missing document type | Please send documents for M12205 | Clarification reply; no browser retrieval |
| Empty category | Please send Transcripts for M12205 | Current source counts and an empty result when the category remains empty; no ZIP |
| Missing matter | Please send Other Documents for M99999 | Clear not found result if that matter still does not exist |
| ZIP over the configured size limit | Use the saved Recording preview below | Explicit notice without a ZIP attachment |

These are test cases for a demonstration, not messages the setup script sends automatically.
For the oversized case in this existing checkout, reuse the saved Recording result:

```powershell
& $senpilotPython -m senpilot.email --eml examples/recordings-request.eml --agent andi.xie241@gmail.com --allow-sender andi.xie24@gmail.com --extractor exact --saved-report artifacts/retrieval/recording-with-timeout/report.json --state artifacts/email/recording-demo
```

This writes a local reply preview, does not send it, and avoids another large audio download.
It requires the ignored saved artifacts from this workspace. They are not included in a fresh Git checkout.
Explain that the notice is a disclosed limitation: an oversized request does not deliver the archive, whereas the assignment asks for a ZIP attachment.

## Design explanation

| Choice | Reason and tradeoff |
| --- | --- |
| DeepSeek extraction with local validation | Accepts conversational requests while keeping the matter, category, recipient, and paths constrained. |
| Deterministic Playwright workflow | Handles FileMaker's stateful UI, virtual rows, and export dialogs without asking the model to choose browser actions. |
| Browser file transfer | Keeps export preparation and downloads in the same session. The optional direct HTTP comparison remains diagnostic only. |
| Full selected category catalog | Supports rows beyond the first viewport and a consistent newest document selection. |
| Manifest and byte verification | Preserves source name mappings and establishes that the archived bytes match the accepted downloads. |
| Durable queue and OS locks | Limits duplicate handling and supports recovery after interrupted processing. An uncertain send requires operator reconciliation rather than an automatic resend. |
| Windows background task | Demonstrates operation without a terminal. Availability still depends on this computer and user session. |

## Reproduce on another machine

Use the [README setup](../README.md), [Gmail and DeepSeek configuration](email-setup.md), and [deployment guide](deployment.md).
Install the pinned dependencies, configure a separate agent mailbox, authorize that mailbox, set a DeepSeek key locally, and choose whether to accept any sender or a specific sender list.
Incoming mail, OAuth tokens, API keys, downloaded documents, and queue state are excluded from Git.
The running agent uses Python 3.12.16; the original Python 3.10 environment is retained locally only for rollback.

The remaining operational checks are an actual logoff or reboot and, if selected later, Linux container execution. They are not required to reproduce the demonstrated Windows request flow.

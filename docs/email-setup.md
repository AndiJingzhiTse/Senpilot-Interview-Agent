# Gmail and DeepSeek setup

Andi Tse selected these roles:

| Address | Role |
| --- | --- |
| andi.xie241@gmail.com | Agent mailbox: receives requests and sends replies |
| andi.xie24@gmail.com | Original test requester and ZIP recipient |

The Windows background task is active and accepts requests from any sender. Live Gmail authorization, DeepSeek extraction, and ZIP delivery have been verified; see [deployment validation](deployment-validation.md).

## Install

From the repository root in PowerShell:

```powershell
$senpilotPython = if (Test-Path 'artifacts/runtime/venv/Scripts/python.exe') { '.\artifacts\runtime\venv\Scripts\python.exe' } else { '.\.venv\Scripts\python.exe' }
& $senpilotPython -m pip install -r requirements-email.txt
```

The email dependencies are optional for browser retrieval. DeepSeek requests use Python's standard HTTP library.

## Preview using the existing downloads

This command uses the saved M12205 request, writes a local `.eml` reply, and does not connect to Gmail, DeepSeek, or the documents website:

```powershell
& $senpilotPython -m senpilot.email --eml examples/request.eml --agent andi.xie241@gmail.com --accept-any-sender --extractor exact --saved-report artifacts/retrieval/release-ten-other-documents/report.json --state artifacts/email/pdf-preview
```

The prepared reply is under that state directory's `jobs/` folder. Repeating the command reuses the queued result rather than downloading or preparing it again.
The sample's ZIP attachment has already been checked against the original archive hash and contains ten documents plus its manifest.
The saved retrieval is a local artifact, not part of Git. On another machine, retrieve M12205 Other Documents first and substitute its report path.

`exact` is a deterministic testing mode that requires an explicit matter number and supported category. It does not call an AI model.

## Authorize the agent mailbox

Follow Google's [Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) for a local test application:

1. Create a Google Cloud project and enable the Gmail API.
2. Configure the OAuth consent screen. If the application is in external testing mode, add **andi.xie241@gmail.com** as a test user.
3. Create an OAuth client with application type **Desktop app**. Save its downloaded JSON as `artifacts/oauth/credentials.json`.
4. Run the command below and choose **andi.xie241@gmail.com** in the consent browser.

```powershell
& $senpilotPython -m senpilot.gmail --agent andi.xie241@gmail.com
```

The authorization requests Gmail read and send scopes. It does not request mailbox modification or Drive access.
The helper verifies the selected Gmail account before saving `artifacts/oauth/token.json`.
Credentials, refresh tokens, email state, and generated messages remain outside tracked source. Reauthorize if the test grant expires or its scopes change.

## Configure DeepSeek

Create an API key using DeepSeek's [API setup guide](https://api-docs.deepseek.com/). Enter it locally in the same PowerShell window that will start the worker:

```powershell
$senpilotApiSecret = Read-Host 'DeepSeek API key' -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $senpilotApiSecret).Password
Remove-Variable senpilotApiSecret
```

Do not paste the key into chat or commit it. The application reads environment variables; it does not automatically load a `.env` file.
The default model is `deepseek-flash`, with thinking disabled for this small extraction task. `DEEPSEEK_MODEL` can override the model name.
These settings follow the current [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) and [model list](https://api-docs.deepseek.com/quick_start/pricing/).

The client uses DeepSeek's [JSON mode](https://api-docs.deepseek.com/guides/json_mode/), then checks the object locally.
JSON mode does not replace application validation: only one explicit matter and one supported category are accepted, and they must match the email text.
Unclear requests get a clarification reply. Empty, truncated, malformed, or failed API responses do not start retrieval, and there is no silent fallback to testing mode.
Only the request subject and text body are passed to extraction. Addresses, attachment contents, output paths, and website selection remain outside model control.

## First live request

From any email address, send a request to **andi.xie241@gmail.com** such as:

> Can you give me Other Documents files from M12205?

Leave it unread in the agent inbox until the worker polls it. Run one poll to prepare a local reply:

```powershell
& $senpilotPython -m senpilot.email --gmail --agent andi.xie241@gmail.com --accept-any-sender --state artifacts/email/live
```

This performs real request extraction and browser retrieval, but saves the reply locally. After inspecting it, add `--send` to send prepared replies through Gmail:

```powershell
& $senpilotPython -m senpilot.email --gmail --agent andi.xie241@gmail.com --accept-any-sender --state artifacts/email/live --send
```

For automatic ongoing handling, add `--watch`. It polls every 60 seconds by default and stops with Ctrl+C:

```powershell
& $senpilotPython -m senpilot.email --gmail --agent andi.xie241@gmail.com --accept-any-sender --state artifacts/email/live --send --watch
```

Gmail sends use MIME messages and base64url encoding as documented in Google's [sending guide](https://developers.google.com/workspace/gmail/api/guides/sending).
With `--accept-any-sender`, polling accepts unread Inbox messages from any sender. It does not mark them read, delete them, or change their labels. Gmail message IDs prevent repeated handling within the same state directory. Automatic replies, bulk mail, delivery reports, and messages from the agent itself are ignored.

For restricted intake, replace `--accept-any-sender` with one or more `--allow-sender ADDRESS` arguments. Choose exactly one policy. The background service uses `accept_any_sender: true` with an empty `allowed_senders` list in its JSON configuration; restart the task after changing it. Requesters do not need OAuth authorization or Google test user registration.

## Attachment policy

The default application limit is **20000000 bytes for the encoded MIME message**, including its body and attachment encoding.
This is a conservative application policy. It is not a claim that every recipient accepts that size. Personal Gmail's published attachment limit is 25 MB; Workspace limits depend on account settings. [Gmail attachment guidance](https://support.google.com/mail/answer/6584?hl=en)

The ZIP's recorded hash is checked again before attachment. The application measures the final MIME message size before allowing a send.
An oversized ZIP stays local; the reply explicitly says no ZIP is attached and asks the requester to arrange another delivery method with the operator.
It does not upload files, invent a download link, or rely on Gmail's website to convert a file to Drive.
The observed 392 MB Recording ZIP takes this exception path, so automatic ZIP delivery for that request remains outside the current attachment policy.

## Queue and recovery

Use one state directory for the agent mailbox so workers share duplicate detection, locking, and website pauses.
Each accepted request receives its own job directory. Replies target the original From address; a body instruction or Reply-To header cannot redirect delivery. An optional sender list restricts intake when configured; it does not authenticate sender identity.

```powershell
& $senpilotPython -m senpilot.email --status --state artifacts/email/live
```

| State | Meaning |
| --- | --- |
| pending | Queued for processing |
| processing | Claimed by a worker; may need explicit recovery after an interrupted process |
| prepared | Reply is saved locally; no send confirmation exists |
| sent | Gmail returned a sent message ID |
| ignored | Sender or message type was excluded |
| failed | Processing failed before delivery |
| sending or send_uncertain | Sending began but confirmation is missing; it is never automatically repeated |

An interrupted or failed processing job can be explicitly retried with `--retry-job FULL_JOB_ID --agent andi.xie241@gmail.com --accept-any-sender --state artifacts/email/live`.
For an uncertain send, inspect the agent's Sent mail using the reply's Message-ID before any manual reconciliation. Neither `--retry-job` nor a restart repeats these sends.
The current worker uses an OS lock that releases when the process exits. Its lock file remains on disk and must not be deleted to bypass another worker.
When upgrading from the original lock format, stop the old worker normally first. The new worker deliberately refuses to adopt that legacy file.
The [deployment wrapper](deployment.md) also offers bounded recovery of interrupted processing jobs, without repeating uncertain sends.

Recognized site challenges and HTTP 403 or 429 responses stop retrieval and persist a pause for remaining queued requests, including after restarting the worker.
Inspect and resolve the block before using `--resume-site` with a processing command. The worker makes no attempt to bypass it.
Requests run sequentially, with at least five seconds between jobs; this is an application setting, not a published allowance from the website operator.

One shot commands return 0 for successfully prepared or sent ordinary results, and 2 for processing errors, site pauses, oversized deliveries, or incomplete retrieval results.
Clarification preparation is an ordinary result, not fulfillment of the original document request. Ctrl+C stops a watching worker with code 130 and preserves its journal.

# Email workflow validation

## Current evidence

Email handling was tested with local `.eml` requests, saved retrievals, mocked Gmail and DeepSeek calls, and Chrome fixtures for access blocks.
No live Gmail authorization, real DeepSeek inference, or actual email delivery has been performed. The configured addresses come from Andi Tse's instructions.

| Saved request | Prepared result | MIME message bytes |
| --- | --- | ---: |
| M12205 Other Documents | Ten document ZIP attached, from andi.xie241@gmail.com to andi.xie24@gmail.com | 14194428 |
| M10431 Recordings | Explicit oversized reply with no attachment; original ZIP remains local | 1286 |

The PDF attachment was decoded from the saved reply and matched the package's SHA256.
Its ZIP had eleven entries: ten documents and `manifest.json`. The reply preserved the actual date labels, all five counts, skipped and failed counts, and the distinction between category entries and unique files.
Both previews remained under the 20 MB encoded message policy and were saved without sending.

## Automated coverage

The full suite includes checks for:

- One matter and one supported category, with ambiguous requests rejected.
- JSON output field validation, values grounded in the email text, and rejection of invented recipient fields.
- DeepSeek request parameters, empty content, incomplete output, content filtering, missing credentials, and HTTP 429 using mocked transport.
- Text and HTML email bodies, quoted replies, ignored attachments, unsupported encodings, automatic replies, mailing lists, and self messages.
- Original sender routing, thread references, exact attached ZIP bytes, final MIME size, changed archives, oversized archives, empty results, and partial results.
- Durable duplicate detection, worker locking, explicit retry, sender restrictions, confirmed sends, and uncertain sends that are never repeated automatically.
- A real local CLI restarted twice against the same request without duplicate processing.
- Continuous polling through retrieval, packaging, reply preparation, sending, and shutdown with mocked remote services.
- Google scope checks and refusal to save a token for a different Gmail account.
- HTTP 403 and 429 responses and challenge pages in Chrome, plus a persistent queue pause after a block.

Run with the email dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The full suite ran 64 tests: 63 passed and one filesystem symlink test was skipped because this Windows session does not permit creating symbolic links.

## Remaining live acceptance

1. Configure Gmail OAuth for andi.xie241@gmail.com and a DeepSeek API key locally using the [setup guide](email-setup.md).
2. Send the assignment's sample request from andi.xie24@gmail.com to the agent inbox.
3. Confirm the extracted fields, retrieval report, attachment size, and local reply.
4. Exercise Gmail delivery and verify that the recipient can open the ZIP and its manifest.

The Recording exception currently sends a truthful size notice rather than fulfilling the assignment's ZIP attachment requirement for an oversized result.
Hosting or another delivery policy would be a separate decision. Provider quotas, live account restrictions, and deployment supervision remain unverified.

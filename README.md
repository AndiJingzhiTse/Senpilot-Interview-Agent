# Senpilot regulatory document retrieval

The local command collects matter metadata and downloads up to ten files from the Nova Scotia public documents website using browser automation.
It produces a JSON report, downloaded files, and a verified ZIP with a manifest.
The email worker supports a dedicated Gmail inbox and validated DeepSeek request extraction. Live activation requires local OAuth and API configuration.
The [deployment package](docs/deployment.md) adds supervision, logs, health checks, and persistent state for Windows or a Linux container.

## Setup

Tested on Windows with Python 3.10.11 and an installed Google Chrome browser.
Run these commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Retrieve files

```powershell
.\.venv\Scripts\python.exe -m senpilot M12205 'Other Documents'
.\.venv\Scripts\python.exe -m senpilot M12205 'Key Documents' --limit 3
.\.venv\Scripts\python.exe -m senpilot M10431 Transcripts --limit 1
.\.venv\Scripts\python.exe -m senpilot M10431 Recordings --limit 1
```

The category must be Exhibits, Key Documents, Other Documents, Transcripts, or Recordings.
Matter numbers are normalized to uppercase and validated before opening a browser.
`--limit` accepts 0 to 10 and defaults to 10 successful files. Use 0 to collect metadata and the category catalog without downloading files.
`--output` selects a new directory; existing directories are rejected to prevent overwrites.

Default output is `artifacts/retrieval/<request>/`:

- `report.json` contains matter metadata, source date labels, all five category counts, the selected category's catalog, downloaded file details, skipped entries, failures, and format warnings.
- `files/` contains completed downloads, with safe names and an identity prefix to prevent collisions. Original names are preserved in the report.
- `incomplete/` holds temporary browser and validation files and is excluded from the completed file list.
- `package/documents.zip` contains the completed files and `manifest.json`, when at least one file is available.
- `package/package.json` records the packaging status, ZIP size and SHA256, and the manifest. Empty results have this summary without an empty ZIP.

The report is saved after each attempted file so a later error retains the successful results.
Exit code 0 means complete, empty, or metadata only; code 2 means partial, unavailable, nonexistent matter, or another reported retrieval error.
Packaging failures also return code 2, preserving the retrieval report and source files.
Unexpected programming errors still raise a traceback and leave an error report.

## Package a saved retrieval

Packaging runs automatically after the retrieval command. To package an older saved report without opening a browser or downloading again:

```powershell
.\.venv\Scripts\python.exe -m senpilot.package artifacts/retrieval/release-ten-other-documents/report.json
```

The default destination is a new `package/` directory beside that report.
Existing destinations are refused. Use `--output artifacts/packages/review` to choose another fresh directory.

Only the report's completed file list is included, with a maximum of ten documents. Unlisted files and incomplete transfers are excluded.
The manifest preserves matter metadata, category counts, original filenames, source identities, format warnings, skipped entries, and failures.
Archive paths retain the unique local filenames, so repeated original names do not overwrite each other.

Packaging checks each source file against its recorded size and SHA256 while streaming it into the ZIP.
It then reads every archive entry back to verify the file count, manifest, sizes, hashes, and ZIP CRC checks before publishing the final archive.
Missing or changed files fail packaging, remove the temporary ZIP, and leave an error summary. The original retrieval is never rewritten.
Files must remain within the retrieval's `files/` directory, and unsafe or duplicate archive paths are rejected.

The package status is `ready` for a complete retrieval with files, `partial` for a partial, failed, or interrupted retrieval that retained files, and `no_files` when there are no completed files.
The original retrieval status remains explicit in the manifest and package summary, including empty, unavailable, and nonexistent matter results.
The standalone packaging command preserves the retrieval exit convention: code 0 for complete, empty, or metadata only results; code 2 otherwise or when packaging fails.

Compression and verification stream file data with bounded memory and support ZIP64.
The reported ZIP size is its actual size in bytes; it does not include email encoding overhead or imply that the archive fits a provider's attachment limit.

## Selection and identity

The command verifies the returned matter number, reads the full selected category through its virtual scrollbar, then chooses the newest dated eligible entries.
Ties use the source identifier or title in lexical order, followed by the occurrence number and document key. Dates without values come last.
The ten file limit counts successes, so an individually failed candidate can be followed by another eligible entry.

Entries explicitly labelled Public are eligible. Confidential and other security labels are reported as skipped.
The observed Recording layout has blank security labels; those published rows are attempted through the normal guest browser interface, and their original blank labels remain in the report.
No credentials or permissions are changed.

Document numbers, Exhibit numbers, dates, and titles differ between layouts.
Keys combine visible metadata with an occurrence number within the captured list; two identical Recording titles are retained as separate entries.
Before each export, the command returns to the captured list position and checks its metadata fingerprint. These keys are not global record IDs.
Category totals may overlap and are labelled as category entries rather than unique files.

## Transfers and validation

Files are downloaded sequentially with Playwright download events and `save_as`, keeping the export dialog open until saving and validation finish.
The Export Field to File dialog's filename is normalized to avoid the observed Chrome header error with commas.
Chrome's download progress events enforce a 30 second inactivity limit and a 15 minute maximum per transfer. A failed file is retried once using a fresh export.
The transfer remains inside the browser; the HTTP comparison client is not used by this command.
Observed HTTP 403 or 429 responses from the source host and recognized challenge pages stop retrieval without a file retry.
The report records `access_blocked` and retains existing successful results. A stalled transfer alone is not classified as an access block.

Empty downloads, HTML error pages, invalid PDFs, and unreadable supported formats are reported as failures.
PDF structures, MP3 headers, WAV headers, and ZIP containers are inspected; other formats receive a nonempty file check. Every completed file gets a size and SHA256 hash.
PDF text that lacks the matter number is recorded without rejecting an otherwise readable file, since scanned pages and ordinary correspondence may not include that text.
WAV source header inconsistencies are reported as warnings after the browser confirms transfer completion; file bytes are preserved and an unreliable duration is omitted.
Audio is not fully decoded or played during validation.

The tested Recording samples were 411 MB and 472 MB WAV files. The latter produced a 392 MB ZIP, so email handling still needs a delivery size policy.

## Checks and diagnostics

For email processing, OAuth setup, local previews, and the chosen mailbox addresses, see the [email setup guide](docs/email-setup.md) and [email validation](docs/email-validation.md).
Install `requirements-email.txt` to run the email worker and its complete test suite.
Install `requirements-dev.txt` for the optional Compose schema checker. See the [deployment validation](docs/deployment-validation.md) for current evidence and remaining target checks.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/probe_download_transport.py
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --compare-http
```

Tests include real Chrome downloads from a local test server, including a connection that stalls after 32 KB.
The optional [transport probe](docs/transport-probe.md) shares browser helpers with the retrieval command and retains HTTP comparison for diagnostics.
See the [packaging checks](docs/packaging-validation.md), [live retrieval checks](docs/retrieval-validation.md), [website inspection](docs/site-inspection.md), and [working plan](WORKFLOW.md).

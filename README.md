# Senpilot regulatory document retrieval

The local command collects matter metadata and downloads up to ten files from the Nova Scotia public documents website using browser automation.
It produces a JSON report and the downloaded files; ZIP packaging and email are the next stages.

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

The report is saved after each attempted file so a later error retains the successful results.
Exit code 0 means complete, empty, or metadata only; code 2 means partial, unavailable, nonexistent matter, or another reported retrieval error.
Unexpected programming errors still raise a traceback and leave an error report.

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

Empty downloads, HTML error pages, invalid PDFs, and unreadable supported formats are reported as failures.
PDF structures, MP3 headers, WAV headers, and ZIP containers are inspected; other formats receive a nonempty file check. Every completed file gets a size and SHA256 hash.
PDF text that lacks the matter number is recorded without rejecting an otherwise readable file, since scanned pages and ordinary correspondence may not include that text.
WAV source header inconsistencies are reported as warnings after the browser confirms transfer completion; file bytes are preserved and an unreliable duration is omitted.
Audio is not fully decoded or played during validation.

The tested Recording samples were 411 MB and 472 MB WAV files. ZIP and email handling will need to account for these actual sizes.

## Checks and diagnostics

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/probe_download_transport.py
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --compare-http
```

Tests include real Chrome downloads from a local test server, including a connection that stalls after 32 KB.
The optional [transport probe](docs/transport-probe.md) shares browser helpers with the retrieval command and retains HTTP comparison for diagnostics.
See the [live retrieval checks](docs/retrieval-validation.md), [website inspection](docs/site-inspection.md), and [working plan](WORKFLOW.md).

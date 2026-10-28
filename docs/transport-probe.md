# Download transport probe

On October 27, 2026, browser preparation followed by HTTP retrieval succeeded for three public PDFs across two matters and two category layouts.
This is a reproducible investigation of one file at a time, not the complete assignment agent.

## Verified behavior

| Case | Bytes | PDF pages | Same session HTTP | Without browser cookies | After closing export |
| --- | ---: | ---: | --- | --- | --- |
| M12205 Other Documents 102674 | 170571 | 2 | 200, identical bytes | 403 | 404 |
| M12205 Other Documents 102454 | 166431 | 1 | 200, identical bytes | 403 | 404 |
| M10431 September 13, 2022 Transcript | 1019620 | 327 | 200, identical bytes | 403 | 404 |

Each case also passed a separate fresh export where the browser's file request was intercepted and aborted before network transfer, then HTTP retrieved the bytes instead.
The HTTP bytes matched the browser baseline exactly. A successful HTTP status alone was not accepted as proof of a valid file.
The browser baseline was parsed as a PDF and checked for the requested matter number on its first page.

The HTTP responses used `application/octet-stream;charset=UTF-8`, including for valid PDFs.
File signatures and actual PDF contents are therefore more useful than requiring an application/pdf response header.
Export URLs must be obtained dynamically and used with the matching browser session while the export dialog remains open.

The earlier standard Data API endpoint checks returned 502. No authenticated Data API access has been established.
This successful HTTP transport still depends on browser automation to search, select rows, and prepare exports.

## Transcript filename finding

The original suggested Transcript filename contained spaces and a comma.
Chrome rejected that response with `net::ERR_RESPONSE_HEADERS_MULTIPLE_CONTENT_DISPOSITION`.
The observed header was `attachment; filename*=UTF-8''NSUARB-M10431-September%2013,%202022.pdf`.
The same session HTTP client nevertheless retrieved and parsed the 327 page PDF successfully.

The probe now normalizes the filename in the normal Export Field to File dialog before submitting it, preserving letters, digits, periods, underscores, and hyphens.
This also made Chrome's browser download work for the Transcript.
Both original and normalized names are recorded when this dialog is present; the PDF bytes were unchanged.

## Timing limits

The JSON reports include transfer timings, but these are ordered samples rather than a controlled performance benchmark.
They exclude matter lookup and export preparation; HTTP requests run after the browser baseline and may benefit from warmed connections or caches.
Fresh HTTP replacement transfers were faster than browser click and save for the two small PDFs in the initial runs, but slower for the Transcript.
There is no demonstrated overall speed advantage yet, and no claim that direct HTTP increases the server's transfer bandwidth.

## Run the probe

Tested with Python 3.10.11 and an installed Google Chrome browser.
The probe launches Chrome using its own temporary Playwright context.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-probe.txt
.\.venv\Scripts\python.exe scripts/probe_download_transport.py
```

To reproduce the other cases:

```powershell
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --row-text 102454
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --matter M10431 --category Transcripts --row-text 'September 13, 2022'
```

Each run creates a new directory under `artifacts/transport/` containing `browser.pdf`, `http.pdf` when successful, and `report.json`.
An optional `--output` argument selects a directory that must not already exist.
Reports record category counts, the selected row, PDF validation, hashes, statuses, and timings. They do not save cookies or temporary export URLs.

## Decision and remaining work

Use browser automation for discovery and export preparation, with HTTP retrieval through the same browser context as the preferred transport to evaluate in the actual downloader.
Keep the export dialog open until the transfer completes and the file is validated.
If HTTP fails, prepare a fresh export and use a normal browser download; the first export's button may already be disabled.
The comparison probe retains its successful browser baseline and reports browser_download as the usable transport if the HTTP replacement fails.

The next implementation stage needs reusable retrieval functions, deterministic selection and list traversal, handling for unavailable entries, and retries with explicit failure reporting.
Audio bytes, large attachments, all ten files in one request, ZIP creation, and email have not been tested by this PDF probe.

References: [Playwright request contexts](https://playwright.dev/python/docs/api/class-apirequestcontext), [download events](https://playwright.dev/python/docs/downloads), and the [earlier site inspection](site-inspection.md).

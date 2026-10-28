# Download transport probe

On October 27, 2026, browser preparation followed by HTTP retrieval succeeded for three public PDFs across two matters and two category layouts.
The selected default is now full browser automation. HTTP comparison remains available through an explicit diagnostic flag.
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

The default command downloads and validates one PDF through Playwright, without intercepting requests or invoking the HTTP comparison client.
To run the same browser flow on the other cases:

```powershell
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --row-text 102454
.\.venv\Scripts\python.exe scripts/probe_download_transport.py --matter M10431 --category Transcripts --row-text 'September 13, 2022'
```

Each default run creates a new directory under `artifacts/browser/` containing `browser.pdf` and `report.json`.
To reproduce the earlier HTTP experiments, add `--compare-http` to any command. Diagnostic runs use `artifacts/transport/` and additionally save `http.pdf` when successful.
An optional `--output` argument selects a directory that must not already exist.
Reports record category counts, the selected row, PDF validation, hashes, statuses, and timings. They do not save cookies or temporary export URLs.

## Decision and remaining work

Use browser automation for discovery, export preparation, and the actual download. Playwright waits for its download event and saves the completed file.
Keep the export dialog open until the transfer completes and the file is validated.
The HTTP experiment demonstrated compatibility but retained the per file UI work and did not show an overall speed advantage that justified its additional interception and session handling.
The optional comparison mode retains its successful browser baseline and reports browser_download as the usable transport if the HTTP replacement fails.

After changing the default, browser mode was verified on M12205 document 102674 and the M10431 September 13 Transcript.
Both produced valid PDFs with the same hashes as the previous experiments, including the normalized Transcript filename.

The next implementation stage needs reusable retrieval functions, deterministic selection and list traversal, handling for unavailable entries, and retries with explicit failure reporting.
Audio bytes, large attachments, all ten files in one request, ZIP creation, and email have not been tested by this PDF probe.
The separate [retrieval command](../README.md) now has live checks for ten PDFs and WAV Recordings; see the [retrieval validation](retrieval-validation.md) for those results and audio format warnings.

References: [Playwright request contexts](https://playwright.dev/python/docs/api/class-apirequestcontext), [download events](https://playwright.dev/python/docs/downloads), and the [earlier site inspection](site-inspection.md).

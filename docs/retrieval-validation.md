# Local retrieval validation

The local retrieval milestone was exercised against the live public website on October 27, 2026, America/Toronto.
The command uses browser automation for discovery, export preparation, and file transfer.
Generated files and detailed reports remain under the ignored `artifacts/retrieval/` directory.

## Live checks

| Request | Observed result |
| --- | --- |
| M12205 Other Documents, limit 10 | Enumerated 43 entries and downloaded 10 files with no failures |
| M12205 Key Documents, limit 10 | Downloaded all 6 entries with no failures |
| M12205 Exhibits, limit 1 | Enumerated 13 entries, skipped 6 Confidential entries, downloaded a Public Exhibit beyond the initial viewport |
| M10431 Transcripts, limit 1 | Enumerated 10 entries and downloaded the newest Transcript through the filename normalization flow |
| M10431 Recordings, limit 1 | Enumerated 23 entries and completed a 471539706 byte WAV download through the browser |
| M12205 Transcripts | Reported an empty category without attempting a file export |
| M00001 Key Documents | Reported an empty category and preserved the missing Decision Date as null |
| M99999 Other Documents | Reported not_found with no files or invented matter metadata |

The catalog traversal checks also returned to the oldest M12205 Other Documents entry after visiting later viewports and verified its visible metadata before selecting it.
Tests do not hardcode current counts into the retrieval implementation.

## Recording findings

The M10431 list contains two entries with exactly the same title and date.
Both remain in the catalog, distinguished by occurrence within the captured list. These identifiers are scoped to that list rather than claimed as global record IDs.

The tested Recording exports were WAV files. An additional selected sample, September 21 final track, completed at 411181050 bytes.
Both completed WAV files had headers declaring more bytes than the saved files contained:

| File | Browser completed bytes | RIFF declared bytes | SHA256 |
| --- | ---: | ---: | --- |
| thurday 1.wav | 471539706 | 1196383948 | `5b0a9e6167971d12a844d565431a6817dd6446ffaac448d6ab59296e98a5ab56` |
| september 21.wav | 411181050 | 1051611852 | `fa255ffc14efae46773ce46f4855facdb7b12b15e176d58af98f5357ea7ee16f` |

The reports record this inconsistency as a format warning and omit an unreliable duration.
The files were preserved without rewriting their headers, and audio was not played or fully decoded.
Browser transfer completion establishes that the browser received a file; it does not prove that the published audio is complete or free of source defects.
The completed audio files were inspected again with the final WAV validation code, with a revalidation timestamp retained in their reports.

An earlier Recording attempt stopped progressing after 32 KB and was interrupted during development.
The command now observes Chrome download progress and cancels a transfer after 30 seconds without increasing byte counts or 15 minutes overall.
One failed file is retried once with a fresh export before its failure is recorded and the next eligible source entry is attempted.

## Automated checks

The test suite covers:

- Deterministic ordering and missing dates.
- Row identity across recycled viewport positions and repeated Recording labels.
- Delayed row contents after a position update, including when animation frame callbacks are unavailable.
- Public labels independent of words such as Confidential in a document title.
- The ten successful file cap, replacement candidates after failures, and metadata only mode.
- Distinct empty and unavailable category results.
- Filename containment and normalization collisions without overwriting an existing file.
- Empty or HTML responses disguised as PDFs.
- Readable PDFs that do not contain extractable matter text.
- WAV detection independent of the filename extension, with source header warnings retained.
- Completed and stalled downloads using a real Chrome browser and a local HTTP test server.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Scope

The command supports all five category layouts and caps successful downloads at ten.
It saves metadata, file hashes, skipped entries, failures, and format inspection results to a report after each attempted file.
Unknown website states stop the request with its existing successful results preserved.

The live file samples were PDFs and WAV audio. MP3 parsing and ZIP container checks are implemented, while other formats receive a nonempty transfer check; every possible format has not been exercised live.
Ten Recording downloads have not been tested. The observed audio sizes are material to the next ZIP and email stages.
Category totals overlap, so the report labels their sum as category entries rather than unique files.

## Explicit access blocks

Local Chrome fixtures verified HTTP 403, HTTP 429 with Retry-After, a recognized challenge title, and an ordinary page that must remain accessible.
The retrieval now reports `access_blocked` for these recognized signals and stops without retrying the blocked file.
Existing successful files can still be packaged as partial results. These fixtures do not establish which protection system, if any, the live website uses.
Challenge detection is limited to the implemented signals; an unfamiliar blocking page can still appear as a general retrieval failure.

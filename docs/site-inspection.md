# Website inspection

Inspection date: October 27, 2026, America/Toronto.

Source: [Public Documents Database](https://uarb.novascotia.ca/fmi/webd/UARB15).
Scope: step 1 of the [working plan](../WORKFLOW.md).
Status: initial inspection complete. Remaining implementation checks are listed explicitly below.
Observations are a dated snapshot, not permanent expected values.

## Assignment requirements

The [assignment](../Co-op%20Technical%20Assignment%20-%20Winter%202027.docx) requires an email containing a matter number and one of five document categories: Exhibits, Key Documents, Other Documents, Transcripts, or Recordings.
The agent must retrieve up to 10 files from that category, ZIP them, and reply with the attachment, matter metadata, and a count of all files in the matter.
The example reply also breaks the counts down by all five categories.

## Live observations

### Search and identity

- The site is a FileMaker WebDirect application. The URL remains `/fmi/webd/UARB15` while navigating within the application.
- The landing form has several Search buttons. The one beside Go Directly to Matter is the relevant action.
- The displayed matter format is M followed by five digits.
- An empty matter search opened M00001 in this session instead of rejecting the input. This is a single observed case, not a promise about every session.
- The native browser tool exposed the text input as generic groups rather than a normal editable control. Andi assisted with entering M12205 after initial focus and window geometry problems. Native text entry and search were then verified for M12383 after taking a fresh screenshot and confirming input focus.
- Page changes can arrive after an initial accessibility snapshot. A successful click is not proof that the destination has loaded.
- A later native automation attempt entered M10431 but returned the previous M12383 matter. The cause is unverified; field commit timing and tool interaction are possibilities, not established website behavior.

Implementation consequence: validate the input before search, then require the displayed matter number to equal the requested matter before extracting or downloading anything.

Searching M99999 produced a No Records Found dialog saying no records matched the request and offering OK to return to Search.
This differs from the No Matching Records dialog used for an empty document category.
M00001's overview exposed a blank Decision Date, so metadata fields must allow missing values.

### M12205 metadata

| Field | Observed value |
| --- | --- |
| Matter number | M12205 |
| Status | Closed |
| Title | Halifax Regional Water Commission, Windsor Street Exchange Redevelopment Project, $69,275,000 |
| Type | Water |
| Category | Capital Expenditure Approvals |
| Date Received | 04/07/2025 |
| Date Final Submissions on document list | 10/23/2025 |
| Outcome | Directions given |

The title's punctuation is normalized in this table; preserve the source text in extracted data.
The category is visibly shortened to Capital Expenditure in the field, while accessibility exposes Capital Expenditure Approvals.
The matter overview labels the second date Decision Date; the document list labels the same displayed value Date Final Submissions.
Keep the layout and original field label as provenance rather than silently treating these as equivalent concepts.
The search form uses MM/DD/YYYY placeholders, and document dates such as 06/22/2026 confirm month/day/year formatting in the list.

### Counts

| Matter | Exhibits | Key Documents | Other Documents | Transcripts | Recordings | Sum of five categories |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| M12205 | 13 | 6 | 43 | 0 | 0 | 62 |
| M00001 | 2 | 0 | 2 | 0 | 0 | 4 |
| M12383 | 6 | 4 | 18 | 0 | 0 | 28 |
| M10431 | 304 | 10 | 187 | 10 | 23 | 534 |

These are category counts, not a count of unique files. Document 102674 was observed in both Key Documents and Other Documents, confirming category overlap.
M12205 differs from the assignment example, which gives 5 Key Documents, 21 Other Documents, and a project amount of $69,270,000.
Retrieve current data rather than using the example as a fixed test fixture.

M12383 is Municipal Boundary, Town of Amherst, 2025 Application for Mutual Boundary Change.
It was Closed, with Date Received 07/10/2025, Decision Date 11/28/2025, and outcome Allowed/Approved.

M10431 was subsequently opened successfully after retrying the lookup with an explicit Tab after entry.
This does not isolate the cause of the preceding mismatch or prove that Tab is required.
It is P-899, Nova Scotia Power Inc., 2022 General Rate Application (GRA), with Type Electricity and Category Electricity Rates.
It was Closed, with Date Received 01/27/2022, Decision Date 02/02/2023, and outcome Directions given.
It provides populated Transcripts and Recordings categories for further checks.

### Other Documents list

- The M12205 tab shows Other Documents 43 and Found Count 43 with All Types visible as a filter option.
- Each row exposes a document number, title, date, security label, extension, Preview, and GO GET IT.
- The top visible document is 102674, Board Order, dated 07/08/2026, Public, `.pdf`.
- The following visible document numbers are 102454, 102417, 102329, 102330, 102293, 102295, and 102266.
- Visible dates appear newest first; documents on the same date are not strictly ordered by document number. No explicit default sort contract has been established.
- The list has its own vertical scrollbar and only a subset of the 43 rows appears in the accessibility snapshot.
- PDF Only, Excel/Word/Other, All Types, document number sorting, security sorting, date sorting, and Save List controls are present.

Implementation consequence: scope GO GET IT to its document row, enumerate beyond the initial viewport, and read counts before applying filters.

### Key Documents list

All six rows were exposed in one accessibility snapshot:

| Document number | Title | Date |
| --- | --- | --- |
| 97289 | Notice of Paper Hearing | 04/11/2025 |
| 97291 | Hearing Order | 04/11/2025 |
| 97354 | Notice of Intervention, HRM | 04/16/2025 |
| 98406 | Amended Hearing Order | 07/04/2025 |
| 99761 | Board Decision | 10/23/2025 |
| 102674 | Board Order | 07/08/2026 |

All six showed Public and `.pdf` with Preview and GO GET IT controls.
The observed ordering was oldest first, unlike Other Documents. The row field order also differed.
Document 102674 appears in both categories, so unique matter counts require deduplication by document number after complete enumeration.

### Exhibits list

The M12205 list reports Found Count 13. Its visible identifier is Exhibit No rather than the numeric Doc No shown by Other Documents.
Initial rows include H-1 Application, H-2 HRWC (CA) RIR-1, H-3 HRWC (BCC) RIR-1 to RIR-6, and H-4 with a REDACTED title.
The list also contains rows explicitly labelled Confidential, such as H-4(C), alongside Public rows.
The initial accessibility snapshot contains only eight rows. Scrolling inside the list exposed the remaining rows, including H-5, H-5(C)-i, H-5(c)-ii, H-5-iii, and H-6.
Across the 13 listed exhibits, seven were labelled Public and six Confidential.
The scrolled snapshot reused the same accessibility row indexes for different exhibits, confirming that indexes and initial viewport contents are not persistent row identities.

Implementation consequence: distinguish available public files from listed confidential entries, and preserve the security label in the retrieval result.
Do not silently treat every listed entry as an available attachment. No confidential file was requested during this inspection.
Exhibit labels are not a verified global file identifier; a unique file total needs more evidence than just concatenating the visible row labels.

### Recordings list

M10431 Recordings lists 23 entries. Initial rows expose a date and title, with Preview and GO GET IT, but no visible document number, security label, or file extension in the accessibility row text.
The first entry is dated 09/12/2022 and titled M10431, NS Power 2022 GRA, Monday; another entry on that date is the Monday Evening Session.
Multiple entries can share a date, and some titles describe parts of a recording.
Do not identify recordings by date alone or assume that numeric document numbers are available in every category.

GO GET IT for the first recording opened Export Field to File, with a Save As field containing an MP3 filename based on the matter and recording title.
This differs from the PDF flow, which went directly to Download Files.
Accepting the export filename opened Download Files with a second button bearing the MP3 filename. The prepared download was closed without downloading the audio bytes during this inspection.
The Recordings layout also showed an Other Documents tab label without its numeric count, despite the overview showing 187. Capture all category counts from the matter overview before entering category specific layouts.

### Transcripts list

M10431 Transcripts reports Found Count 10. Initial rows expose a date, title, format label such as Pdf or PDF, security label Public, Preview, and GO GET IT.
The first entries are September 12, 2022 and September 12, 2022 Evening Session.
Multiple transcripts can share a date. Normalize format labels without losing the original text, and do not use the date alone as an identifier.
GO GET IT for the first transcript opened Export Field to File with a suggested PDF filename containing the matter and hearing date. The export was cancelled after inspecting the filename.
Cancelling the export opened Continue or Cancel Script, stating that Export Field Contents had been cancelled and asking whether to continue. Cancel was used to end the unused export script.
Cancellation therefore needs explicit modal cleanup before the next retrieval action.

## Open checks

- Confirm transport response headers and whether other file types use the same download flow.
- Verify downloaded transcript and recording bytes, filenames, and size limits during the retrieval implementation.
- Automate traversal beyond the initial viewport and identify an explicit reproducible selection order.
- Turn the observed invalid matter, blank metadata, empty category, and mismatched matter cases into automated acceptance checks.
- Define the reply's total count precisely: report category entries or enumerate and deduplicate all categories for a unique document count.
- Verify automated text entry with the proposed browser library before committing to it.

## Empty category behavior

Opening M12205 Transcripts and Recordings, each with a count of zero, returned to the matter overview and opened a No Matching Records dialog.
The dialog said Click Ok to return to Matter and exposed an OK button.
A zero count is therefore a normal empty result that can involve navigation and a modal, rather than a populated list with no rows.

## Verified sample download

For M12205 Other Documents, clicking GO GET IT for document 102674 opened an in page Download Files dialog.
The dialog said the files were ready and exposed a second button named `102674.pdf`.
Clicking that button produced a completed Chrome download without opening a new PDF tab in this observed flow.
The button became disabled after the download, and Escape dismissed the download UI.

The suggested filename was `102674.pdf`; Chrome saved `102674 (1).pdf` because a file with the original name already existed in the user's Downloads directory.
The newly downloaded file was inspected locally:

| Check | Result |
| --- | --- |
| Size | 170571 bytes |
| File signature | `%PDF-1.6` |
| PDF structure | Parsed successfully, 2 pages |
| Matter marker in first page text | ORDER M12205 |
| SHA256 | `6a3b3b90596df09605d7a978caf32d7bdbefb4f0b68648388733c2376d45757f` |

This verifies an actual PDF rather than an HTML error response saved with a PDF extension.
It does not verify HTTP Content Type headers or every download category.
The sample remains outside the repository.

Implementation consequence: handle the second download button, save to a request specific directory, and keep the source document number separate from the local filename.

## Proposed defaults pending implementation

- Report each of the five category counts; label their sum as a sum rather than claiming unique files.
- Preserve exact website date labels and omit missing values instead of inventing them.
- Retrieve the first 10 available rows in a documented explicit sort order, subject to a verified traversal mechanism.
- Use deterministic extraction and download logic; reserve AI for interpreting email requests and composing language grounded in extracted values.

## Next implementation checkpoint

Build a small browser probe that opens M12205, verifies the displayed matter number, and extracts the overview metadata and five category counts.
Evaluate Python with Playwright against the actual DOM and field commit behavior before expanding to downloads.
Success means a structured result grounded in the live page, no hardcoded example counts, and a clear failure for a mismatched or nonexistent matter.
Only then add the two observed export flows, row traversal, and security handling in separate reviewable changes.

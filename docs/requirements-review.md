# Assignment requirements review

Prepared for Andi Tse on October 28, 2026, against the supplied [technical assignment](../Co-op%20Technical%20Assignment%20-%20Winter%202027.docx), current source, saved reports, and live test evidence.

## Verdict

The ordinary document workflow is verified from an incoming email through recipient receipt and opening of its ZIP, including operation under the Windows background task.
Coverage is **partial for the attachment requirement**: an oversized ZIP receives a truthful size notice and its files are not delivered. Andi explicitly chose to retain this behavior and disclose the limitation.
The submission should retain that distinction rather than claim that every supported request produces an attached ZIP.

## Required behavior

| Assignment requirement | Status | Implementation and evidence |
| --- | --- | --- |
| Accept a matter number and document type by email | Verified | Gmail receives requests; DeepSeek extracts the two fields and local validation checks them against the input. The fresh M12205 background job recorded the DeepSeek mode and model. |
| Support Exhibits, Key Documents, Other Documents, Transcripts, and Recordings | Implemented and retrieval tested | All five layouts were exercised against the website. Full email delivery was exercised for Other Documents; every category has not been tested through live email. See [retrieval validation](retrieval-validation.md). |
| Open the supplied website, search for the matter, and use the requested tab | Verified | Playwright uses the guest UI and confirms the returned matter number before collecting metadata. See [browser implementation](../senpilot/browser.py). |
| Download up to ten documents with Go Get It | Verified | The successful download count is capped at ten, after unavailable entries are skipped. Ten, fewer than ten, empty, and missing matter cases were exercised. The fresh request downloaded ten of 44 Other Documents. |
| Compress the retrieved documents into a ZIP | Verified | The archive includes only completed files and a manifest. Source and archived file sizes and hashes are checked. See [ZIP validation](packaging-validation.md). |
| Include the ZIP as an email attachment | Partial | Normal sized results are attached, sent, and confirmed by the recipient. Oversized archives produce a notice without an attachment. The observed Recording ZIP was 392292513 bytes. |
| Provide a total count of files in the matter | Implemented with stated interpretation | The reply reports all five source category counts and their sum as category entries. Categories overlap, so the sum is explicitly not described as a unique physical file count. This follows the assignment example's category count presentation. |
| Summarize key matter metadata | Verified | Replies include title, type, category, status, outcome, and the source's date labels. The latest saved reply was checked against its report. |

The manifest is additional metadata, so an archive containing ten source documents has eleven entries. It does not count as an eleventh retrieved document.
Source dates are preserved as labelled by the website, including Decision Date; a final filing date is not inferred from that field.

## Decisions and assumptions

- Choose the newest dated eligible documents, with deterministic ties. The assignment does not prescribe a selection order.
- Skip entries labelled Confidential or another unavailable security level. Published Recording rows with blank security labels are attempted through the normal guest interface.
- Preserve identical visible Recording entries as separate occurrences within the captured list; their keys are not claimed to be global record IDs.
- An empty category produces an explanatory reply without an empty ZIP. A missing or ambiguous request produces clarification.
- Use a 20 MB encoded MIME message policy. Any category can produce an oversized archive; this policy is not limited to Recordings.
- Preserve source bytes and record format warnings rather than silently rewriting published audio.
- Accept requests from any sender and reply to the original From address. A specific sender list remains available as an optional configuration. The model cannot select a recipient, filesystem path, or alternative website.

## Oversized archive decision

Andi selected the current notice on October 28, 2026. The behavior remains:

1. Retrieve and package the selected files.
2. Measure the encoded reply size before sending.
3. If it exceeds the application limit, retain the archive locally and send a notice stating that no ZIP is attached.

There is no private download link, automatic upload, or split archive delivery.
This is a disclosed functional limitation against the literal attachment requirement. An evaluator's acceptance of that limitation has not been established.

The tested files were audio, not video. The Board describes the category as recordings of proceedings in its [database guide](https://www.nserbt.ca/nseb/matters-evidence/how-use-database).
M10431 had 23 Recording entries; M12205 and M12383 had none in the inspected snapshots.
The two downloaded WAV samples were approximately 411 MB and 472 MB. This small sample does not establish the frequency of oversized archives across the website.

## Evidence boundaries

- The background M12205 request produced ten documents in a 6686350 byte ZIP. Gmail accepted the reply, its saved attachment hashes were verified, and Andi confirmed that it arrived and opened. See [deployment validation](deployment-validation.md).
- A separate M12383 live request returned ten documents. A live clarification reply was also observed.
- Empty categories, unavailable entries, nonexistent matters, delayed virtual rows, transfer stalls, bad file responses, and access blocks have local or retrieval evidence; they have not all been exercised through real Gmail delivery.
- WAV source headers were inconsistent in the completed samples. Their warnings remain in the reports. The audio was not fully decoded or played.
- Windows startup and a controlled task restart passed. A full logoff or host reboot and a forced crash of the installed task were not performed.
- The Linux container definition passed schema validation, but Docker is unavailable here and the image has not been built or run.

## Submission readiness

The active Windows task has been migrated to Python 3.12.16 after regression checks and live Gmail profile and DeepSeek extraction checks. The old environment remains available for rollback. See [runtime migration](runtime-upgrade.md).
The [demo and handoff guide](demo.md) covers the normal request, an empty category, clarification, and the size notice without downloading large audio again.
Evaluators can email the existing agent without registering their sender addresses. An evaluator reproducing the project independently supplies their own agent mailbox, OAuth configuration, and DeepSeek key.

The known attachment limitation should appear in the submission and demo. The assignment itself does not specify a hosted deployment, a demonstration video, or a new user interface; the background task and demo notes are supporting deliverables.

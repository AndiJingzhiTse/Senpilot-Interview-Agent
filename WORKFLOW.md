# Working together

Andi Tse and Codex are completing the Senpilot technical assignment in small, reviewable stages.
The course slides are guidance, adapted to this assignment rather than a mandatory process.

## Cooperation

1. Start each stage with its purpose, inputs, expected outputs, and acceptance checks.
2. Explain meaningful alternatives and tradeoffs before choices that affect scope, cost, or architecture. Andi owns those choices.
3. Keep implementation changes small enough to understand and review. Prefer one behavior per change; use the slides' 10 to 50 lines as a guide rather than a rigid limit.
4. Separate assignment requirements, live observations, proposed defaults, and unresolved questions.
5. Run meaningful checks and report their actual results. Treat generated tests and critiques as hypotheses that require review.
6. Use local Git commits for coherent milestones. Keep credentials, downloaded documents, and temporary browser data outside tracked source.
7. Explain the mechanism and limitations so Andi can discuss the implementation in an interview.

Routine reversible work can continue within the current stage. Raise questions when the answer materially changes the result rather than asking for approval after every action.

## Stages

The selected download approach is browser automation with Playwright download events and save_as. HTTP comparison remains an optional diagnostic tool.

1. Inspect the public website and record evidence and open questions.
2. Implement matter lookup, metadata extraction, category counts, and document retrieval.
3. Validate downloaded files and create the ZIP.
4. Connect email and validated AI request extraction.
5. Test the complete workflow and failure cases.
6. Prepare setup instructions and a reproducible demonstration.

## Completed local retrieval milestone

Build a local retrieval command that accepts a matter number and one of the five document categories, collects the matter overview metadata and category counts, and downloads up to ten available files using the browser.

Acceptance checks:

- Confirm the displayed matter number before collecting results.
- Preserve source labels for dates and distinguish missing metadata from empty strings or invented values.
- Traverse rows beyond the first viewport using a documented selection order and stable file identities.
- Retain original names and source metadata while preventing local filename collisions.
- Report empty categories, unavailable entries, failed downloads, and actual successful counts explicitly.
- Complete each browser download before closing its export dialog, retaining the Transcript filename normalization.

Validate the command on a category with more than ten entries, a category with fewer than ten, an empty category, and a nonexistent matter. Include a Recording sample before declaring all five categories supported.
These cases have been exercised; see the [live checks](docs/retrieval-validation.md) and [run instructions](README.md).

## Completed ZIP milestone

ZIP packaging now uses only the report's completed file list and preserves original filenames and source metadata in a manifest.
It verifies archive entry counts, source and archive file hashes, and archive size. Empty results produce a summary without an empty ZIP; partial results remain labelled partial.
The retrieval CLI packages automatically, and a separate command packages saved reports without contacting the website.
See the [packaging checks](docs/packaging-validation.md) for test evidence and the observed Recording archive size.

## Implemented email workflow

Andi selected andi.xie241@gmail.com as the agent inbox and sender, and andi.xie24@gmail.com as the requester and ZIP recipient.
The Gmail adapter uses OAuth, and DeepSeek performs request extraction with local validation of its JSON output.
A durable local queue, one worker per state directory, explicit handling of uncertain sends, and persistent pauses after observed site blocks are implemented.
Local previews attach the saved ten document ZIP and report the large Recording ZIP as oversized without claiming delivery.
The application checks a configurable encoded message size limit before sending. No hosted file delivery is configured.

## Next milestone

Andi reported successful live handling. The existing journal records two successful ten document replies and one clarification reply, and the saved attachments passed the deployment audit.
The portable service package now includes persistent state, OS locks, bounded processing recovery, safe handling of uncertain sends, logs, health checks, a Windows task definition, and a Linux container definition.
Andi selected Windows background activation. Task SenpilotAgent is now registered and running against the original queue and token. Local startup, Gmail polling, and a controlled restart passed without repeating any of the three prior sends.
See the [deployment guide](docs/deployment.md) and [validation record](docs/deployment-validation.md).

The background task processed a fresh M12205 request using DeepSeek, downloaded ten documents without failures, and sent a verified ZIP through Gmail. Andi confirmed receipt and successfully opened the ZIP.
The [requirements review](docs/requirements-review.md) and [demo and handoff guide](docs/demo.md) are prepared. Andi chose to retain the oversized ZIP notice and disclose that those results do not fulfill the ZIP attachment requirement. Andi subsequently chose to accept requests from any sender, so evaluators do not need their addresses added manually.
The active Windows task now uses Python 3.12.16 after regression and provider checks; the previous environment is retained for rollback. See [runtime migration](docs/runtime-upgrade.md).
An actual user logon or host reboot has not been tested.
The alternative Linux image still requires a real Docker build and runtime test on a selected host.

The unrestricted intake change exposed old unread mail and sent 426 clarification replies to unrelated historical messages. The task was stopped, the queue backed up, and 19 unsent historical or unrelated jobs excluded without deleting their audit records.
Intake now persists a receipt boundary, excludes subscription and obvious automated mail, ignores unrelated messages before extraction, and sends each watcher reply before starting the next job.
Two missing requests from andi.xie242@gmail.com were found in Gmail Spam. Both contain valid M12205 Other Documents requests. An approved Gmail filter now selects Never send it to Spam for incoming mail to the agent containing any of the five supported categories, with no sender restriction. The two existing requests were moved into the Inbox and left unread for processing.
The background task then processed both requests on their first attempts and Gmail confirmed two ZIP reply sends to andi.xie242@gmail.com. Each archive contained ten documents and passed the saved attachment checks. Customer receipt has not yet been confirmed.

## References

- [Course introduction](Slide/01_IntroCodingWithAI.pdf), especially page 12 on owning decisions.
- [Requirements guidance part 1](Slide/04_01_requirements_guidelines.pdf), especially pages 6 to 12 on questions, assumptions, and ambiguity.
- [Requirements guidance part 2](Slide/04_02_requirements_guidelines.pdf), especially pages 2 to 13 on structure, consistency, and measurable checks.
- [Code generation guidance](Slide/05_Code_Generation_guidelines.pdf), especially pages 2 to 25 on review size, alternatives, contracts, tests, and critique.

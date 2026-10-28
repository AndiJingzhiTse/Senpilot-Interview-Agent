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

1. Inspect the public website and record evidence and open questions.
2. Implement matter lookup, metadata extraction, category counts, and document retrieval.
3. Validate downloaded files and create the ZIP.
4. Connect email and validated AI request extraction.
5. Test the complete workflow and failure cases.
6. Prepare setup instructions and a reproducible demonstration.

## References

- [Course introduction](Slide/01_IntroCodingWithAI.pdf), especially page 12 on owning decisions.
- [Requirements guidance part 1](Slide/04_01_requirements_guidelines.pdf), especially pages 6 to 12 on questions, assumptions, and ambiguity.
- [Requirements guidance part 2](Slide/04_02_requirements_guidelines.pdf), especially pages 2 to 13 on structure, consistency, and measurable checks.
- [Code generation guidance](Slide/05_Code_Generation_guidelines.pdf), especially pages 2 to 25 on review size, alternatives, contracts, tests, and critique.

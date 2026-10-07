# Deep research

Normal answers read a ranked sample. Deep research walks every stored source section in your selected collection instead. It runs locally through Ollama; a large collection can take hours or days. Start with a short run to see your PC's speed.

Enter a question, select the model and collection above, then open **Deep research**. Set a run budget and click **Start research**. The default is ten minutes; zero means continue until finished. A batch limit gives another way to bound a run. The budget is checked between model calls, so the current call can finish after the time expires.

**Pause** saves the current work after its active call. **Resume** continues the same question, model and source snapshot. Saved jobs survive closing the app, but do not restart themselves. A rebuilt index or changed model requires a new job to keep the evidence consistent.

**Summarize findings so far** makes an interim report. Its coverage label tells you how much was examined; it does not mean the collection was fully read. Resume afterward to continue scanning. Once the scan finishes, the final report is built automatically.

## How the summary is built

1. Read each section in small word windows with 40 words of boundary overlap. Split each window into numbered sentence excerpts (long sentences use overlapping spans under 80 words). The model selects relevant IDs; code copies and validates their original text instead of asking the model to transcribe it. A section counts as examined only after every window is processed.
2. Summarize groups of up to eight collected excerpts. Keep the question in view, combine overlapping points, preserve different contexts and disagreements, and avoid forcing a requested ranking or item count.
3. Combine those summaries in further groups until one report remains. Each intermediate summary and its evidence links are saved, so this stage can also resume.
4. Link the final report's citation numbers to evidence groups. Open **Read underlying excerpts** to inspect their original passages and full stored sections. Group citations identify supporting evidence; they are not a quotation from a book.

This is hierarchical map-reduce summarization, informed by [GraphRAG global search](https://microsoft.github.io/graphrag/query/global_search/) and [RAPTOR's recursive summarization](https://arxiv.org/abs/2401.18059). It does not implement their knowledge graphs or semantic clustering, and there is no universal best summarizer. Small saved batches fit this local app's context limits and interruption requirements.

The model is not trained by this process. Scanning and synthesis use the installed model's existing weights. Research is question-specific, rather than a reusable summary index.

## What coverage means

Reading every window is broader than retrieving a few nearest matches. It still cannot prove that every relevant statement was identified: the model can miss a passage, and later compression can lose nuance. Exact excerpt validation checks copied text, not the truth of every interpretation. Treat an absence of collected evidence as a finding of this run, not proof that the ministry never addressed something.

Reports should say what the examined sources support, distinguish background from direct teaching, and retain qualifications. They should not turn recurring themes into an authoritative list of the ministry's most important items. Inspect the underlying excerpts when a conclusion matters.

## Private files

Jobs live in a `research` folder beside your index, each in its own SQLite file. These files contain private excerpts and summaries. Keep them local along with your books and index. The code-only package uses a fixed allowlist and excludes these files.

## Time estimates and interim reports

Estimated time remaining uses measured batch speed, remaining scan windows and the expected summary hierarchy. New jobs count scan windows from section word lengths; older jobs extrapolate from completed and partially read sections. Until enough batches finish, the page says it is still estimating. Before summary calls have been timed, their duration uses the observed batch average. Estimates include projected final-report work but can change substantially with section lengths, evidence yield, retries and PC load. Paused jobs show estimated active time after resuming.

An interim report is available once the job is fully paused and at least one relevant excerpt is saved. Pause waits for the current model call to finish and save. The page explains that waiting state beside the controls. Resume afterward to keep scanning.

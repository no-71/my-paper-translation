---
name: my-paper-translation-en
description: Faithfully translate paper PDFs into a user-specified target language, preserving structure, equations, and figure/table numbering, with automatic batching and resumable progress; use parallel subagents only when explicitly requested.
---

# Paper Translation

Translate the user's paper PDF into self-contained Markdown in the target language, automatically completing all batches by default. Determine the target language from the user's request and existing context; if neither makes it clear, ask before translating. Do not assume English or Chinese. Follow the user's instructions when they specify a translation scope, number of batches, or pause.

## Files and Source Preparation

- Save the final translation to `translation/<paper-filename-without-extension>.md` in the working directory by default; use the user's path when specified.
- Save all intermediate files under `tmp_gpt/translation/<paper-id>/` in the working directory; the paper ID must distinguish different PDFs with the same filename.
- Prefer the PDF text layer; use available OCR or page-viewing capabilities for scanned or problematic pages.
- Count pages by their actual order in the PDF, recording printed page numbers separately; check pages to establish the reading order of two-column text, paragraphs spanning pages, and floating figures and tables.
- Before translating, identify the body structure and excluded content, then create a traceable source index and batch plan following the [Progress Files and Tool Protocol](references/state-protocol.md).

## Translation Scope and Fidelity

- Translate the title, abstract, and body, including the conclusion, body footnotes, figure captions, table titles, and table notes; preserve section numbering, heading hierarchy, paragraph order, and relationships in the argument.
- Do not omit or condense content, or add explanations absent from the source, except for long-table summaries. Use fluent academic prose in the target language and consistent terminology throughout; retain necessary English terms or abbreviations at first occurrence when useful.
- Exclude references, appendices, and explicitly marked supplementary material, including their equations and code; determine scope by section membership rather than cutting off body content at a page position.
- Keep body equations faithful to the source, preserving symbols, subscripts, superscripts, structure, numbering, and references; output LaTeX using `$...$` or `$$...$$`.
- Preserve body code verbatim and translate its natural-language explanations into the target language.
- If source content cannot be read or identified, record its location, explain the limitation, and check the PDF; if it remains unresolved, mark it for verification rather than guessing missing content.

## Figures and Tables

- Do not insert images. Preserve figure numbers and references, translate captions and explanations, and place them near their original logical positions. By default, do not transcribe individual axis or legend labels inside figures; follow the user's instructions if they request otherwise.
- Preserve table numbers and translate titles and necessary notes. Use Markdown tables for ordinary tables; complex headers may use other Markdown arrangements that faithfully express the relationships. Preserve numerical values, units, comparison markers, and associations with notes.
- When a table body exceeds 300 non-whitespace characters, replace it with a clearly labeled "Table content summary" in the target language. Count the original cell contents, including text, numbers, and symbols, but exclude the title and notes. Preserve comparison subjects, metrics, main results, and key conditions in the summary without adding inferences.

## Automatic Batching

1. Treat the highest-level body divisions as "chapters" and the abstract as a separate unit; excluded content does not enter batches.
2. The inclusive interval between each batch's starting and ending PDF pages must not exceed six pages; structural boundaries may make a batch shorter.
3. Within the limit, prioritize at least one complete chapter and include more complete chapters when possible; split overly long chapters at subsection or paragraph boundaries, and allow continuation batches without a complete chapter.
4. If a single source unit exceeds six pages, first split it at verifiable boundaries such as sentences, table row groups, or equation groups; if it still cannot be split, record the reason, actual page count, and exception. Never exceed the limit silently.
5. Read context across batches when needed, but output only the current batch's scope to avoid duplicating or omitting content spanning pages.
6. Save progress when interrupted or paused; on resumption, verify the source and index according to the progress protocol and continue unfinished work.

## Execution Modes

- Unless the user explicitly requests subagents, the current model translates, checks, and saves batches sequentially according to the plan.
- When the user explicitly requests subagents, read and follow the [Parallel Interaction Protocol](references/parallel-translation.md).
- If agent capabilities are unavailable, explain the limitation and do not claim parallel execution. If the user requires agents to translate, save the preparation results and report the blocker without substituting your own translation; otherwise, proceed using available capabilities.
- Both modes follow the progress protocol for submission, acceptance, and merging; the tool validates structure and file consistency but does not replace checks against the source.

## Review and Delivery

Review is enabled by default; only when the user explicitly disables it, set `--review off` according to the progress protocol. When disabled, skip per-batch and full-text content review and terminology usage rechecks specified in this file and its referenced protocols, while retaining structural validation, subagent glossary maintenance and adjudication of new terms, and unresolved issue tracking.

When review is enabled, check each batch against the source for completeness, accuracy, equations, figures/tables and their references, paragraph boundaries, and terminology.

Merge accepted batches according to the progress protocol, keeping working records out of the final translation. Before completion, use the index to confirm that every included source unit is covered exactly once and excluded units have not entered the translation; when review is enabled, also check the actual content, transitions between batches, and terminology consistency.

When delivering, link the translation and state the completed scope, whether it was reviewed, and unresolved issues; do not claim the entire paper is fully complete while content remains unresolved.

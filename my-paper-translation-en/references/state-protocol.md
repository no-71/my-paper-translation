# Progress Files and Tool Protocol

The tool is this skill's `scripts/translation_state.py`; it requires Python 3.9 or later and has no third-party dependencies. Relative paths are based on the task's working directory; replace `<...>` in commands with actual values. Only the main model modifies progress or invokes state-changing and merge commands; subagents write only translations and reports in their exclusive directories.

## Modes and Initialization

- `sequential`: Ordinary translation, the default mode; no glossary is enabled and terminology fields are not required.
- `parallel`: Subagent translation explicitly requested by the user; use this mode even if only one subagent runs. After initialization, publish the first glossary version according to the [Terminology Protocol](glossary-protocol.md), then assign tasks.

Set review at initialization with `--review on|off`, defaulting to `on`; use `off` only when the user explicitly requests it. Progress stores `review_enabled`; legacy tasks without this field are treated as having review enabled, and switching during a task is not supported. When disabled, skip content review according to the main skill's overall rule; structural validation, terminology maintenance, and issue handling continue as usual.

Persist the mode rather than inferring it from whether glossary files exist. If old progress lacks `mode` or a task needs to switch modes, the main model verifies the actual execution method, preserves existing progress, explicitly registers the mode, and completes the corresponding reports and glossary versions. Do not reinitialize to overwrite results or switch silently.

Save the complete index and plan in `tmp_gpt/translation/<paper-id>/plan.json`. The following illustrates only one unit and one batch:

```json
{
  "units": [
    {"id": "u0001", "pages": [1, 1], "chapter": "Abstract", "kind": "paragraph", "source": "source.md#u0001", "include": true, "reason": ""}
  ],
  "batches": [
    {"id": "B001", "units": ["u0001"], "equations": [], "figures": [], "tables": [], "exception": ""}
  ]
}
```

- List `units` in reading order with unique IDs and `source` references traceable to the actual source; `pages` contains the actual starting and ending PDF pages, inclusive.
- Set `include: false` and provide a reason for excluded units. Concatenated in order, batches must cover every included unit exactly once.
- List figure captions and table notes separately or explicitly record them within their containing unit. Use source numbers in object inventories; body references to an object across batches do not count as additional objects.
- For batches exceeding six pages, record the indivisible unit and reason in `exception`, for confirmation by the main model.

```text
python3 <skill>/scripts/translation_state.py init --root tmp_gpt/translation/<paper-id> --pdf <source.pdf> --plan tmp_gpt/translation/<paper-id>/plan.json --mode sequential
```

For subagent mode, change the argument to `--mode parallel`. The tool saves PDF and plan fingerprints and refuses to overwrite existing progress; changes to the source or plan require a new task. Do not edit fingerprints manually to bypass checks.

## Publishing Glossary Versions

Use only in subagent mode. The main model prepares a draft according to the terminology protocol and publishes it:

```text
python3 <skill>/scripts/translation_state.py glossary-publish --root <task-directory> --file <task-directory>/glossary-draft.json --reason "Affected terms, source evidence, and adjudication reasons"
```

Versions increment from 1. The tool saves immutable snapshots, the current glossary, fingerprints, and history, and refuses deletion of published term IDs; do not manually edit published files. The tool does not authenticate the caller; the main model's exclusive write access is enforced through the division of responsibilities and agent instructions.

## Assignment and Submission

Subagent task package sizes follow the [Parallel Protocol](parallel-translation.md); ordinary mode may assign one batch at a time. Example:

```text
python3 <skill>/scripts/translation_state.py assign --root <task-directory> --task T001 --attempt A001 --batches B001 B002 B003 B004 B005
```

The tool creates `workers/T001/A001/`; task/attempt combinations cannot be reused. Save `B001.md` and `B001.report.json` for each batch. Shared report fields:

```json
{
  "batch": "B001",
  "task": "T001",
  "attempt": "A001",
  "units": ["u0001"],
  "equations": [],
  "figures": [],
  "tables": [],
  "issues": [],
  "translation_sha256": "SHA-256 of the translation file's byte contents"
}
```

Inventories must derive from actual checking, not mechanical copies of the plan; put problems in `issues`. In subagent mode, add the version, fingerprint, usage records, and proposal fields required by the terminology protocol; ordinary mode ignores terminology fields in old reports. Generate fingerprints with Python's `hashlib.sha256(Path(...).read_bytes()).hexdigest()`.

```text
python3 <skill>/scripts/translation_state.py submit --root <task-directory> --batch B001
```

The tool checks the task, attempt, scope, object inventories, and file fingerprints; in subagent mode, it also checks published glossary versions and usage locations. Batches with issues may be submitted for inspection but cannot be accepted.

## Acceptance and Repairs

The main model accepts ordinary batches after checking them against the source:

```text
python3 <skill>/scripts/translation_state.py accept --root <task-directory> --batch B001 --reviewed
```

For subagent batches, process terminology proposals and confirm compatibility with the current standard, additionally passing `--terms-reviewed`; when `term_proposals` is nonempty, also use `--terms-note` to record the reasons for adopting, reusing, or rejecting each proposal in the progress history:

```text
python3 <skill>/scripts/translation_state.py accept --root <task-directory> --batch B001 --reviewed --terms-reviewed --terms-note "Decisions and reasons for each item"
```

Use the review flags above only when review is enabled. When disabled, continue using `accept` but omit `--reviewed` and `--terms-reviewed` (passing them causes an error):

```text
python3 <skill>/scripts/translation_state.py accept --root <task-directory> --batch B001
```

If a subagent batch contains term proposals, `--terms-note "Decisions and reasons for each item"` is still required when review is disabled, but do not recheck terminology usage paragraph by paragraph. The tool still checks scope, object inventories, versions, fingerprints, and unresolved issues. Batches store `reviewed: false`; subagent batches also store `terms_reviewed: false`. `accepted` only means the batch has been received and can be merged; it must not be described as having passed review on that basis.

These flags declare that the main model has actually performed the checks; the tool does not judge translation semantics, equation contents, term meanings, or the completeness of usage records. Review standards follow the main skill, and terminology adjudication follows the terminology protocol.

After glossary publication, when relevant entries associated by the tool change, it marks accepted batches `terms_stale` and excludes them from the merged prefix. Process them again according to the review setting and accept them using the corresponding command (when review is disabled, only handle term proposals and refresh bindings without reviewing the translation); for known conflicts or reassignment:

```text
python3 <skill>/scripts/translation_state.py reject --root <task-directory> --batch B001 --reason "Source location and repair requirements"
```

Then assign repairs with a new task/attempt combination and new directory; even revisions by the same agent must not overwrite submitted artifacts. Retain old results for traceability but exclude them from the current merge. The tool does not stop or detect agents; before reassignment, the main model confirms actual run state according to the parallel protocol.

## Merging and Status

```text
python3 <skill>/scripts/translation_state.py merge --root <task-directory> --output translation/<paper-name>.md
python3 <skill>/scripts/translation_state.py status --root <task-directory>
```

`merge` regenerates the continuous accepted prefix starting from the first batch in source order rather than appending. It refuses empty output when there is no valid prefix, and refuses to merge modified submission artifacts. Repairs or terminology reviews may shorten the prefix; explicitly report that the work remains incomplete.

Output must not overwrite the source, intermediate files, or other tasks' contents. Use a new output name when an existing file has an unknown origin; if an existing final translation has been modified externally, preserve the user's changes before proceeding. After merging, report the scope and perform final checks and delivery according to the main skill.

States are `pending` (awaiting assignment), `assigned` (translation in progress), `submitted` (submitted), `accepted` (received), and `repair` (awaiting repair); `terms_stale` indicates that terminology needs review, and `merged` records the valid merged range. `status` returns the mode, `review_enabled`, glossary version, and batch states; the glossary version is null in ordinary mode. Progress is written atomically with an event history; the main model executes mutation commands sequentially rather than modifying progress concurrently.

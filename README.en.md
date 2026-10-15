# My Paper Translation

[简体中文](README.md) | English

Translate paper PDFs faithfully into self-contained Markdown, with automatic batching, saved progress, resumable translation, and subagent translation when explicitly requested by the user.

This project provides instructions and helper tools for AI coding agents that support skills. The model reads the PDF, translates it, and reviews the translation against the source. The Python script validates coverage, manages progress, and merges batches in order; it cannot perform translation on its own.

## Choose a Version

| Skill directory and invocation identifier | Instruction language | Translation target language |
| --- | --- | --- |
| [`my-paper-translation-cn`](my-paper-translation-cn/SKILL.md) | Chinese | Chinese by default |
| [`my-paper-translation-en`](my-paper-translation-en/SKILL.md) | English | Specified by the user |

`cn` / `en` identify the language of the skill instructions. Apart from the default target language, both versions use the same translation and progress rules.

The Chinese version translates papers into Chinese by default; the English version requires a target language to be specified. To change any translation rules, state your requirements in the prompt.

## Requirements

- Python 3.9 or later. The progress script uses only the standard library and has no third-party dependencies.
- Subagent support is optional and is used only when explicitly requested by the user. Actual concurrency depends on the environment's capacity and the number of task packets available for assignment.

## Installation

Download or clone this repository, then copy the selected **complete skill folder** into your skills directory, preserving its internal structure.

Both versions can be installed together and distinguished by their respective identifiers. Copying only `SKILL.md` is insufficient: the protocol files and script must also be copied. Copy the complete skill folder.

**When using Codex**, the skills directory is `$CODEX_HOME/skills`; `CODEX_HOME` defaults to `~/.codex/skills` (on Windows: `C:\Users\<User Name>\.codex`).

For example, install the Chinese version from the repository root in a Bash environment where `CODEX_HOME` is not set:

```bash
mkdir -p ~/.codex/skills
cp -R my-paper-translation-cn ~/.codex/skills/
```

## Usage Examples

Provide an accessible PDF to the agent and specify the skill in your request.

Translations are reviewed by default, which increases token usage. To disable review, state this in your prompt.

You can also specify changes to other translation rules in your prompt.

**Chinese version:**

```text
Use $my-paper-translation-cn to translate papers/example.pdf.
```

**English version, translating into Spanish for example:**

```text
Use $my-paper-translation-en to translate papers/example.pdf into Spanish.
```

**Parallel translation with subagents (optional, suited to long papers):**

```text
Use $my-paper-translation-cn with subagents to translate papers/example.pdf into Chinese in parallel.
```

```text
Use $my-paper-translation-en with subagents to translate papers/example.pdf into Spanish in parallel.
```

When the environment supports parallel execution and enough tasks are available, subagents can speed up the translation of long papers, but increase model usage (token consumption).

**Specify a scope or pause condition:**

```text
Use $my-paper-translation-cn to translate papers/example.pdf. Complete only the first two batches this time, then save progress and pause.
```

The user's requested translation scope, batch count, output path, and pause conditions take precedence over the defaults.

## Outputs and Workflow

Read the PDF and confirm the translation scope, then split the content into batches based on its structure, translate and review each batch, and save progress. Finally, merge accepted translations in source order and deliver the result. Interrupted work can resume from saved progress. All intermediate translation files are stored under `tmp_gpt/`, and translation results are stored under `translation/`.

## Translation Scope and Limitations

- Translate the title, abstract, and main text, including conclusions, main-text footnotes, figure captions, table titles, and table notes. Preserve section numbering, heading hierarchy, paragraph order, and the relationships between arguments.
- Exclude references, appendices, and explicitly labeled supplementary material, including their equations and code. Determine exclusions by section membership rather than cutting off the main text at a page boundary.
- Preserve the symbols, subscripts, superscripts, structure, numbering, and references of main-text equations, using LaTeX. Preserve main-text code unchanged and translate the accompanying natural-language explanations.
- Do not insert images. Preserve figure numbers and references, and translate captions. By default, do not transcribe every axis label or legend entry within figures.
- Preserve table contents when the table body contains no more than 300 non-whitespace characters. For longer tables, replace the body with a clearly labeled "Table content summary." Count cell text, numbers, and symbols, excluding the table title and notes.
- Apart from summaries of long tables, do not omit or compress content, or add explanations absent from the source. Record and check the location of illegible content; if it remains unresolved, mark it for verification rather than guessing.

## Subagent Translation

By default, the current model translates and reviews batches sequentially; subagents are used only when explicitly requested by the user. See "Usage Examples" for invocation examples.

In this mode, the main model prepares source material, assigns tasks, maintains terminology, accepts submissions, and merges results; it does not translate or rewrite the translation. Subagents translate, check their work, and revise it. Initial task packets contain five consecutive batches each; the last packet may contain fewer than five. Actual parallel execution requires both sufficient capacity and enough task packets. Do not arbitrarily split initial packets into smaller ones just to create parallelism.

Subagent mode uses a versioned glossary, with each batch fixed to one published version. After terminology changes, review affected batches based on their actual usage records. Ordinary sequential translation does not require a separate glossary, but terminology must remain consistent.

If the environment does not support subagents, explain the limitation. If the user requires translation by subagents, save the prepared material and report the blocker rather than taking over the translation. See each version's parallel translation and glossary protocols for the detailed rules.

## Resume an Interrupted Translation

Keep the original PDF, task intermediate directory, and existing translation, and provide the original task directory to the agent:

```text
Use $my-paper-translation-cn to resume translating papers/example.pdf. The existing task directory is tmp_gpt/translation/example-task/. Verify the saved progress and complete the remaining batches.
```

```text
Use $my-paper-translation-en to resume translating papers/example.pdf into Spanish. The existing task directory is tmp_gpt/translation/example-task/. Verify the saved progress and complete the remaining batches.
```

On resumption, verify the source and plan fingerprints without reinitializing and overwriting existing progress. Changes to the source or plan require a new task. Batches requiring repair use a new task/attempt combination and directory, retaining old artifacts for traceability.

## License

This project is licensed under the [MIT License](LICENSE).

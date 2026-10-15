# Terminology Management for Subagent Translation

Enable this protocol only for subagent translation. The main model has exclusive maintenance and publishing rights; subagents read the shared glossary and submit new terms and evidence-based change proposals in their own reports. Ordinary translation does not create, maintain, or require reading a glossary, and does not require terminology fields.

## Files and Initial Version

Files reside under `tmp_gpt/translation/<paper-id>/`:

- `glossary.json`: Current authoritative glossary.
- `glossary-versions/<version>.json`: Immutable version snapshots.
- `glossary-history.jsonl`: Versions, fingerprints, and publication reasons.
- `glossary-draft.json`: The complete draft of the next version prepared by the main model; agents must not read it as a published glossary.

The main model establishes the first version from the title, abstract, keywords, and source definitions without needing to read the whole paper closely beforehand. Include only core concepts, technical terms, abbreviations, and expressions likely to receive inconsistent translations; mark translations as tentative when evidence is insufficient rather than inventing a definitive rendering.

Draft format (Spanish is an example target language):

```json
{
  "version": 1,
  "terms": [
    {
      "id": "T0001",
      "source": "policy",
      "aliases": ["policies"],
      "translation": "política",
      "variants": [],
      "scope": "A mapping from states or observations to actions in reinforcement learning",
      "evidence": ["u0001"],
      "status": "confirmed"
    }
  ]
}
```

`evidence` references actual source units; replace the example IDs. `aliases` contains abbreviations and inflected source forms, `variants` contains permitted target-language variants, and `status` is `tentative`, `confirmed`, or `superseded`. Use different IDs and `scope` values for different meanings of the same word. Published IDs must not be deleted or reused; when replacing a term, retain the old entry and record its replacement ID and the reason.

See the [Progress Protocol](state-protocol.md) for publication commands and version checks. If publication is unexpectedly interrupted, check the progress registration, snapshot, and current glossary, retain the artifacts, and restore a consistent state without directly overwriting versions.

## Reading Versions

After publishing an update, the main model notifies running agents. At the start of each batch, a subagent checks the latest published version, uses that snapshot throughout the batch, and records the SHA-256 of the complete file; do not switch versions within a batch. Adopt updates from the next batch without requiring all agents to stop and wait.

On first load, read core terminology and task-relevant entries; subsequently read changes and relevant entries rather than repeatedly loading the complete history. Determine relevance using source terms, aliases, abbreviations, definitions, and scopes. Even when reading selected entries, reference the complete version number and snapshot fingerprint. After context loss or task resumption, recover necessary rules from persistent files.

## Reports and Adjudication

Add the following to each batch report:

```json
{
  "glossary_version": 1,
  "glossary_sha256": "SHA-256 of the complete version snapshot",
  "term_usage": [{"term_id": "T0001", "units": ["u0001"]}],
  "term_proposals": [
    {"source": "new concept", "translation": "Provisional rendering actually used in this batch", "scope": "Meaning in the source", "units": ["u0002"]}
  ]
}
```

Use empty lists when there is no usage or no proposal. `term_usage` records glossary terms actually used and their locations; `term_proposals` records actual renderings of new terms, their meanings, and source locations, and may include abbreviations, alternative translations, and reasons. Objections to existing entries must include the target ID and source evidence. Records must derive from actual translation and checking.

Follow the standard translations for existing terms; use provisional renderings for new terms and continue translating without waiting for adjudication. Put unresolved questions that affect accuracy in `issues`.

The main model deduplicates and adjudicates against the source: publish a new version when adopting proposals, or reuse the ID of an existing synonymous entry. After processing all proposals and conflicts for the batch, record each decision and its reason in the acceptance history according to the progress protocol; publication history records actual entry changes, and rejecting a proposal alone does not warrant an empty update. Consult existing decisions later and do not reopen disputes without new evidence. Change a confirmed translation only when supported by source definitions, applicable meaning, or a clear error; do not repeatedly switch based on stylistic preferences.

## Change Impacts and Targeted Repairs

Unrelated additions or updates that only add confirmation status or evidence do not invalidate old batches. Changes to the translation, scope, aliases, or permitted variants of a used term require checking related batches; if the translation is already compatible, accept it again, and if it conflicts, send it to an agent for targeted repair. See the progress protocol for status markers and commands.

Automatic association depends on actual usage records; omitted terms, aliases, and different meanings still require judgment against the source and translation, and reasonable grammatical variation cannot be deemed wrong solely from string differences. Finally, check items individually using usage records and search clues rather than blindly replacing terms or retranslating indiscriminately.

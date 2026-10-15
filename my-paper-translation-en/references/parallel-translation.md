# Parallel Subagent Interaction Protocol

Use this protocol only when the user explicitly requests subagent translation; use subagents of the current task rather than creating new user-facing chats.

## Responsibilities and Preparation

The main model prepares the source, creates batches, assigns tasks, maintains terminology, reviews submissions, and merges results; it does not translate or rewrite translations. Subagents translate, self-check, and revise their assigned scope; they do not create further subagents or modify the final translation, global progress, or other agents' directories.

Before launching, establish a unified index and batch plan, initialize subagent mode according to the [Progress Protocol](state-protocol.md), and publish the first glossary version according to the [Terminology Protocol](glossary-protocol.md).

Each initial translation task package contains five consecutive batches; the last package may contain fewer than five. Repair tasks include only batches requiring repair. Agents may read context outside their scope but must not include it in their translation.

## Parallel Scheduling

Parallel execution requires overlapping translation execution times across multiple agents. Let `C` be the number of subagents that can run simultaneously for this task, `R` the currently occupied slots, and `Q` the number of task packages ready for immediate dispatch. Initially launch `min(C, Q)` agents; subsequently launch `min(max(C - R, 0), Q)` additional agents. Determine capacity from the actual environment state, reserving the slots required by the main model; results awaiting review do not by themselves occupy running slots.

- **Fill capacity initially:** Register and launch the task packages that can run in the current round consecutively; do not wait for one agent to finish translating before launching the next. When both capacity and the number of task packages are at least two, multiple translation agents must run simultaneously.
- **Receive continuously:** The main model processes batch notifications from any agent without waiting for the whole group to finish; after delivering each batch, a subagent continues to the next without waiting for acceptance. Prioritize repair requests when received.
- **Refill slots first:** After completion, failure, or a capacity change, check the actual state and confirm released slots; if tasks remain, launch new agents immediately without waiting for other agents, review of current results, or merging in order. Refill slots before time-consuming review. Prioritize already identified repairs that block merging, but do not delay translation for repairs that have not yet been identified.
- **Limitations and failures:** Explain the limitation when there are fewer than two task packages or only one available slot; do not shrink initial task packages just to create parallelism. Record the reason for launch failures, resource limits, or a user pause, and avoid busy-loop retries.

## Task Dispatch

The main model registers a unique task and attempt ID according to the progress protocol before launching an agent, and provides:

- Absolute paths to the PDF, traceable source, index, plan, this skill and relevant protocols, glossary, and version directory.
- Task and attempt IDs, assigned batches, exact starting and ending units, and page numbers.
- An exclusive writable directory and the filenames for each batch's translation and report.
- The division of responsibilities in this protocol, translation scope, prohibition on rebatching, and the required formats for unresolved issues and completion notifications.

Agents read the specified files before executing; they do not depend on inheriting the complete chat history.

## File Delivery and Notifications

For each batch, write the translation and report to temporary files first, then rename them to their final filenames and notify the main model when complete. Files are the basis of delivery; messages convey only status and paths. See the progress protocol for the report format, source coverage, object inventories, and fingerprint requirements, and the terminology protocol for terminology fields.

Example notification:

> T002/A001: B006 submitted, translation and report paths …; covers u0081–u0104; the equation's lower-right subscript on page 32 needs verification; continuing with B007.

After receiving a notification, the main model registers the submission and schedules review according to the scheduling rules; merging follows the progress protocol.

## Acceptance and Repairs

The main model reviews against the source using the standards in the [Main Skill](../SKILL.md) and records acceptance results according to the progress protocol.

When problems are found, first send the source location, specific problem, repair requirements, and acceptance criteria to the original agent; if that agent has finished, launch a repair agent. Revisions and reassignment use new attempts and new directories according to the progress protocol; late results from old attempts must not overwrite the current task.

Follow the terminology protocol for glossary reading, proposal submission, adjudication, and change impacts.

## Run Records and Recovery

- The main model saves run IDs, task and attempt IDs, batch ranges, start and end times, running/completed/failed states, and the capacity, occupied slots, tasks awaiting dispatch, and refill actions at scheduling time in `scheduler.json` in the task directory; maintain these records separately from batch progress.
- Confirm execution using agent status, messages, and waiting tools, then use actual run IDs and time records to verify overlap. An observation timeout does not mean failure; do not launch duplicates merely because no message has arrived yet. After a launch failure or agent interruption, confirm that the original agent has stopped or never actually started before reassigning unfinished batches or batches needing repair; retain accepted results.
- When the user pauses, stop dispatching, coordinate stopping running agents, and save state; before resuming, verify the source according to the progress protocol and check actual run states and the pending queue.

All agents finishing does not mean translation is complete; perform final checks and delivery according to the main skill and progress protocol.

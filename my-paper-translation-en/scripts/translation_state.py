#!/usr/bin/env python3
"""Validate paper translation coverage, manage progress, and merge in order; do not assess translation semantics."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value), "Identifiers may contain only letters, digits, underscores, and hyphens")
    return value


def validate_plan(plan):
    units = plan["units"]
    batches = plan["batches"]
    require(units and batches, "The index and batches must both be nonempty")
    lookup = {}
    for unit in units:
        uid = identifier(unit["id"])
        require(uid not in lookup, "Duplicate source unit identifier")
        start, end = unit["pages"]
        require(type(start) is int and type(end) is int and 1 <= start <= end, "Invalid source page range")
        require(type(unit["include"]) is bool, "include must be a boolean")
        require(unit.get("chapter") and unit.get("kind") and unit.get("source"), "Missing chapter, kind, or source location")
        require(unit["include"] or unit.get("reason"), "Excluded units must include a reason")
        lookup[uid] = unit
    covered, seen = [], set()
    for batch in batches:
        bid = identifier(batch["id"])
        require(bid not in seen, "Duplicate batch identifier")
        seen.add(bid)
        ids = batch["units"]
        require(isinstance(ids, list) and ids and all(uid in lookup for uid in ids), "Batch contains invalid source units")
        pages = [lookup[uid]["pages"] for uid in ids]
        span = max(end for _, end in pages) - min(start for start, _ in pages) + 1
        require(span <= 6 or str(batch.get("exception", "")).strip(), "Batch exceeds six pages without an exception explanation")
        for key in ("equations", "figures", "tables"):
            values = batch[key]
            require(isinstance(values, list) and all(isinstance(v, str) for v in values), "Invalid object identifier list")
            require(len(values) == len(set(values)), "Duplicate object identifier within a batch")
        covered.extend(ids)
    require(covered == [u["id"] for u in units if u["include"]], "Batches must cover all included units exactly once in source order, without excluded content")


def load_state(root):
    state = read(root / "progress.json")
    require(digest(Path(state["pdf"])) == state["pdf_sha256"], "The PDF has changed; create a new task")
    require(digest(Path(state["plan_path"])) == state["plan_sha256"], "The plan has changed; create a new task")
    require(read(Path(state["plan_path"])) == state["plan"], "The plan in progress does not match the original plan")
    validate_plan(state["plan"])
    require(state.get("mode") in ("sequential", "parallel"), "Legacy progress lacks an execution mode; verify the task and add mode as sequential or parallel; do not reset existing progress")
    state.setdefault("review_enabled", True)
    require(type(state["review_enabled"]) is bool, "The review setting must be a boolean")
    return state


def parallel(state):
    return state["mode"] == "parallel"


def glossary(root, state, version=None):
    require(parallel(state), "Standard translation does not enable a glossary")
    versions = state.get("glossary_versions", {})
    version = version if version is not None else state.get("glossary_version")
    require(str(version) in versions, "The glossary version has not been published")
    path = root / "glossary-versions" / (str(version) + ".json")
    require(digest(path) == versions[str(version)]["sha256"], "A published glossary has been modified")
    value = read(path)
    if version == state.get("glossary_version"):
        require(digest(root / "glossary.json") == digest(path), "The current glossary does not match the published version")
    return value


def validate_glossary(value, state):
    require(type(value.get("version")) is int and value["version"] >= 1, "Invalid glossary version")
    require(isinstance(value.get("terms"), list), "The glossary is missing the terms list")
    seen = set()
    units = {u["id"] for u in state["plan"]["units"]}
    for term in value["terms"]:
        tid = identifier(term["id"])
        require(tid not in seen, "Duplicate term identifier")
        seen.add(tid)
        for key in ("source", "translation", "scope"):
            require(isinstance(term.get(key), str) and term[key].strip(), "A term is missing its source expression, translation, or applicable meaning")
        for key in ("aliases", "variants"):
            require(isinstance(term.get(key), list) and all(isinstance(v, str) for v in term[key]), "Invalid term aliases or allowed variants")
        require(term.get("status") in ("tentative", "confirmed", "superseded"), "Invalid term status")
        require(isinstance(term.get("evidence"), list) and term["evidence"] and all(u in units for u in term["evidence"]), "A term lacks valid source evidence")


def validate_terms(root, state, report, plan):
    version = report.get("glossary_version")
    require(type(version) is int and version >= 1, "Missing valid glossary version")
    snapshot = glossary(root, state, version)
    require(report.get("glossary_sha256") == state["glossary_versions"][str(version)]["sha256"], "The glossary fingerprint in the report does not match")
    terms = {t["id"] for t in snapshot["terms"]}
    usages = report.get("term_usage")
    proposals = report.get("term_proposals")
    require(isinstance(usages, list) and isinstance(proposals, list), "Missing term usage records or proposal list")
    for usage in usages:
        require(usage.get("term_id") in terms, "A usage record references a term absent from this batch's glossary")
        require(isinstance(usage.get("units"), list) and usage["units"] and all(u in plan["units"] for u in usage["units"]), "Term usage locations are empty or outside this batch")
    for proposal in proposals:
        for key in ("source", "translation", "scope"):
            require(isinstance(proposal.get(key), str) and proposal[key].strip(), "A new term proposal is missing its source expression, actual translation, or meaning")
        require(isinstance(proposal.get("units"), list) and proposal["units"] and all(u in plan["units"] for u in proposal["units"]), "Invalid source locations in a proposal")


def term_bindings(root, state, report, current=None):
    """Track only entries used by the batch and entries matching its proposals; unrelated additions are not conflicts."""
    current = glossary(root, state) if current is None else current
    used = {u["term_id"] for u in report["term_usage"]}
    proposed = {(p["source"].strip().casefold(), p["scope"]) for p in report["term_proposals"]}
    result = {}
    for term in current["terms"]:
        names = {s.strip().casefold() for s in [term["source"], *term["aliases"]]}
        if term["id"] in used or any((name, term["scope"]) in proposed for name in names):
            # Updates to confirmation status and evidence do not change translations or trigger unnecessary repairs.
            result[term["id"]] = {k: term[k] for k in ("source", "translation", "scope", "aliases", "variants")}
    require(used <= result.keys(), "A used term has been removed; preserve its identifier and record the replacement relationship")
    return result


def batch_plan(state, bid):
    require(bid in state["batches"], "Batch does not exist")
    return next(b for b in state["plan"]["batches"] if b["id"] == bid)


def artifact(root, entry, bid):
    folder = root / "workers" / identifier(entry["task"]) / identifier(entry["attempt"])
    return folder / (bid + ".md"), folder / (bid + ".report.json")


def check_delivery(root, state, bid, check_snapshot=False):
    plan = batch_plan(state, bid)
    entry = state["batches"][bid]
    text_path, report_path = artifact(root, entry, bid)
    report = read(report_path)
    require(text_path.read_text(encoding="utf-8").strip(), "Translation is empty")
    for key, expected in (("batch", bid), ("task", entry["task"]), ("attempt", entry["attempt"])):
        require(report.get(key) == expected, "Submission task or attempt identifier does not match")
    for key in ("units", "equations", "figures", "tables"):
        require(report.get(key) == plan[key], "Report coverage or object list does not match: " + key)
    require(isinstance(report.get("issues"), list), "Missing issues list")
    if parallel(state):
        validate_terms(root, state, report, plan)
    hashes = {"text_hash": digest(text_path), "report_hash": digest(report_path)}
    require(report.get("translation_sha256") == hashes["text_hash"], "The translation fingerprint does not match the report")
    if check_snapshot:
        require(all(entry.get(k) == v for k, v in hashes.items()), "Artifacts have been modified after submission; resubmit or register a revision")
    return report, hashes


def prefix(state):
    result = []
    for batch in state["plan"]["batches"]:
        bid = batch["id"]
        if state["batches"][bid]["status"] != "accepted" or state["batches"][bid].get("terms_stale"):
            break
        result.append(bid)
    return result


def run(args):
    root = Path(args.root).resolve()
    require("tmp_gpt" in root.parts, "The task intermediate directory must be under tmp_gpt/")
    state_path = root / "progress.json"
    if args.command == "init":
        require(not state_path.exists(), "Progress already exists; initialization must not overwrite it")
        pdf, plan_path = Path(args.pdf).resolve(), Path(args.plan).resolve()
        require(plan_path.is_relative_to(root), "The plan must be inside the task intermediate directory")
        plan = read(plan_path)
        validate_plan(plan)
        state = {"version": 2, "mode": args.mode, "review_enabled": args.review == "on",
                 "pdf": str(pdf), "pdf_sha256": digest(pdf),
                 "plan_path": str(plan_path), "plan_sha256": digest(plan_path), "plan": plan,
                 "batches": {b["id"]: {"status": "pending"} for b in plan["batches"]},
                 "assignments": [], "history": [], "merged": []}
    else:
        state = load_state(root)
        if args.command == "status":
            return {"mode": state["mode"], "review_enabled": state["review_enabled"],
                    "glossary_version": state.get("glossary_version"),
                    "batches": state["batches"], "merged": state["merged"], "ready_prefix": prefix(state),
                    "output_stale": state.get("output_stale", False),
                    "complete": len(state["merged"]) == len(state["batches"]) and not state.get("output_stale", False)}
        if args.command == "glossary-publish":
            require(parallel(state), "Standard translation does not create or maintain a glossary")
            candidate = Path(args.file).resolve()
            require(candidate.is_relative_to(root) and candidate != root / "glossary.json"
                    and not candidate.is_relative_to(root / "glossary-versions"), "Publish from a separate draft file inside the task directory")
            value = read(candidate)
            validate_glossary(value, state)
            require(args.reason.strip(), "Publication must explain the basis for additions or changes")
            version = state.get("glossary_version", 0) + 1
            require(value["version"] == version, "Versions must start at 1 and increase consecutively")
            previous = set()
            if state.get("glossary_version"):
                previous = {t["id"] for t in glossary(root, state)["terms"]}
            require(previous <= {t["id"] for t in value["terms"]}, "Published term identifiers must not be deleted; preserve them and record replacement relationships")
            affected = []
            for bid, entry in state["batches"].items():
                if entry["status"] == "accepted":
                    report, _ = check_delivery(root, state, bid, True)
                    if entry.get("term_bindings") != term_bindings(root, state, report, value):
                        affected.append(bid)
            archive = root / "glossary-versions" / (str(version) + ".json")
            if archive.exists():
                require(read(archive) == value, "This version file already exists with different content; overwriting is prohibited")
            else:
                write(archive, value)
            metadata = {"sha256": digest(archive), "reason": args.reason}
            state.setdefault("glossary_versions", {})[str(version)] = metadata
            state["glossary_version"] = version
            write(root / "glossary.json", value)
            history = root / "glossary-history.jsonl"
            history.write_text("".join(json.dumps({"version": int(v), **item}, ensure_ascii=False) + "\n"
                                       for v, item in state["glossary_versions"].items()), encoding="utf-8")
            for bid in affected:
                state["batches"][bid]["terms_stale"] = True
                if bid in state["merged"]:
                    state["merged"] = state["merged"][:state["merged"].index(bid)]
                    state["output_stale"] = True
        elif args.command == "assign":
            if parallel(state):
                glossary(root, state)
            identifier(args.task)
            identifier(args.attempt)
            require(1 <= len(args.batches) <= 5 and len(set(args.batches)) == len(args.batches), "Each task must contain one to five distinct batches")
            require(not any(a["task"] == args.task and a["attempt"] == args.attempt for a in state["assignments"]), "The task and attempt combination has already been used")
            order = [b["id"] for b in state["plan"]["batches"]]
            for bid in args.batches:
                batch_plan(state, bid)
                require(state["batches"][bid]["status"] in ("pending", "repair"), "The batch is already assigned or completed; register a repair first")
            positions = [order.index(bid) for bid in args.batches]
            require(positions == list(range(positions[0], positions[0] + len(positions))), "A task package must contain consecutive batches in order")
            folder = root / "workers" / args.task / args.attempt
            require(not folder.exists(), "The task artifact directory already exists; use a new attempt identifier")
            folder.mkdir(parents=True)
            state["assignments"].append({"task": args.task, "attempt": args.attempt, "batches": args.batches})
            for bid in args.batches:
                state["batches"][bid] = {"status": "assigned", "task": args.task, "attempt": args.attempt}
        elif args.command in ("submit", "accept", "reject"):
            batch_plan(state, args.batch)
            entry = state["batches"][args.batch]
            if args.command == "reject":
                require(entry["status"] in ("assigned", "submitted", "accepted"), "A repair cannot be registered in the current state")
                require(args.reason.strip(), "A repair reason is required")
                entry["status"] = "repair"
                entry["reason"] = args.reason
                if args.batch in state["merged"]:
                    state["merged"] = state["merged"][:state["merged"].index(args.batch)]
                    state["output_stale"] = True
            elif args.command == "submit":
                require(entry["status"] in ("assigned", "submitted"), "The batch cannot be submitted")
                _, hashes = check_delivery(root, state, args.batch)
                entry.update(hashes)
                entry["status"] = "submitted"
            else:
                if state["review_enabled"]:
                    require(args.reviewed, "Pass --reviewed only after actually checking against the source")
                else:
                    require(not args.reviewed and not args.terms_reviewed, "Review is disabled; omit --reviewed and --terms-reviewed to avoid incorrectly recording the batch as reviewed")
                require(entry["status"] == "submitted" or (parallel(state) and entry["status"] == "accepted"), "Only submitted batches or accepted batches requiring term review may be accepted")
                report, _ = check_delivery(root, state, args.batch, True)
                require(not report["issues"], "Unresolved issues remain; the batch cannot be accepted")
                if parallel(state):
                    if state["review_enabled"]:
                        require(args.terms_reviewed, "For subagent batches, the main model must resolve term proposals and pass --terms-reviewed")
                    require(not report["term_proposals"] or args.terms_note.strip(), "This batch contains term proposals; record decisions and reasons with --terms-note")
                    entry["term_bindings"] = term_bindings(root, state, report)
                    entry["terms_bound_version"] = state["glossary_version"]
                    entry["terms_reviewed"] = state["review_enabled"]
                    if state["review_enabled"]:
                        entry["terms_reviewed_version"] = state["glossary_version"]
                    entry["terms_stale"] = False
                entry["reviewed"] = state["review_enabled"]
                entry["status"] = "accepted"
        elif args.command == "merge":
            ids = prefix(state)
            require(ids, "There is no contiguous accepted prefix; refusing to generate an empty translation")
            output = Path(args.output).resolve()
            require(output != Path(state["pdf"]) and not output.is_relative_to(root)
                    and output != Path(__file__).resolve(), "The final file must not overwrite the source, the tool, or task intermediate files")
            require(output.suffix.lower() == ".md", "The final translation must be a Markdown file")
            if state.get("output"):
                require(str(output) == state["output"], "An output path is already registered; silently writing to other files is prohibited")
                require(output.exists() and digest(output) == state["output_sha256"], "The final file has been modified externally; preserve user changes and handle it manually first")
            else:
                require(not output.exists(), "The output file already exists; choose a new filename to avoid overwriting user content")
            chunks = []
            for bid in ids:
                report, _ = check_delivery(root, state, bid, True)
                require(not report["issues"], "The batch still has unresolved issues")
                if parallel(state):
                    require(state["batches"][bid].get("term_bindings") == term_bindings(root, state, report),
                            "Terms relevant to the batch have changed; the main model must review and reaccept it or assign a subagent repair: " + bid)
                text_path, _ = artifact(root, state["batches"][bid], bid)
                chunks.append(text_path.read_text(encoding="utf-8").strip())
            output.parent.mkdir(parents=True, exist_ok=True)
            # The staging file also stays in the task's tmp_gpt directory before being written to the final path.
            staged = root / "merged-preview.md"
            staged.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
            output.write_bytes(staged.read_bytes())
            state.update(output=str(output), output_sha256=digest(output), merged=ids, output_stale=False)
    event = {k: v for k, v in vars(args).items() if k != "root"}
    state["history"].append(event)
    write(state_path, state)
    return {"command": args.command, "mode": state["mode"], "review_enabled": state["review_enabled"],
            "glossary_version": state.get("glossary_version"),
            "merged": state["merged"], "output_stale": state.get("output_stale", False),
            "complete": len(state["merged"]) == len(state["batches"]) and not state.get("output_stale", False)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "assign", "submit", "accept", "reject", "merge", "status", "glossary-publish"):
        sub = commands.add_parser(command)
        sub.add_argument("--root", required=True, help="Task directory under tmp_gpt")
        if command == "init":
            sub.add_argument("--pdf", required=True)
            sub.add_argument("--plan", required=True)
            sub.add_argument("--mode", choices=("sequential", "parallel"), default="sequential", help="Standard sequential translation or subagent translation; defaults to sequential")
            sub.add_argument("--review", choices=("on", "off"), default="on", help="Whether to review content; defaults to on; use off only when the user explicitly disables review")
        elif command == "glossary-publish":
            sub.add_argument("--file", required=True)
            sub.add_argument("--reason", required=True)
        elif command == "assign":
            sub.add_argument("--task", required=True)
            sub.add_argument("--attempt", required=True)
            sub.add_argument("--batches", nargs="+", required=True)
        elif command in ("submit", "accept", "reject"):
            sub.add_argument("--batch", required=True)
            if command == "accept":
                sub.add_argument("--reviewed", action="store_true")
                sub.add_argument("--terms-reviewed", action="store_true")
                sub.add_argument("--terms-note", default="", help="Decisions and reasons for this batch's term proposals, recorded in progress history")
            if command == "reject":
                sub.add_argument("--reason", required=True)
        elif command == "merge":
            sub.add_argument("--output", required=True)
    try:
        print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        parser.exit(1, "Error: " + str(error) + "\n")


if __name__ == "__main__":
    main()

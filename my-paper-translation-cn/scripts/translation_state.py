#!/usr/bin/env python3
"""论文翻译的范围校验、进度管理与有序合并；不判断译文语义。"""

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
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]+", value), "编号仅允许字母、数字、下划线和连字符")
    return value


def validate_plan(plan):
    units = plan["units"]
    batches = plan["batches"]
    require(units and batches, "索引和批次均不能为空")
    lookup = {}
    for unit in units:
        uid = identifier(unit["id"])
        require(uid not in lookup, "原文单元编号重复")
        start, end = unit["pages"]
        require(type(start) is int and type(end) is int and 1 <= start <= end, "原文页码范围无效")
        require(type(unit["include"]) is bool, "include 必须为布尔值")
        require(unit.get("chapter") and unit.get("kind") and unit.get("source"), "缺少章节、类型或原文位置")
        require(unit["include"] or unit.get("reason"), "排除单元必须说明原因")
        lookup[uid] = unit
    covered, seen = [], set()
    for batch in batches:
        bid = identifier(batch["id"])
        require(bid not in seen, "批次编号重复")
        seen.add(bid)
        ids = batch["units"]
        require(isinstance(ids, list) and ids and all(uid in lookup for uid in ids), "批次包含无效原文单元")
        pages = [lookup[uid]["pages"] for uid in ids]
        span = max(end for _, end in pages) - min(start for start, _ in pages) + 1
        require(span <= 6 or str(batch.get("exception", "")).strip(), "批次超过六页且缺少例外说明")
        for key in ("equations", "figures", "tables"):
            values = batch[key]
            require(isinstance(values, list) and all(isinstance(v, str) for v in values), "对象编号清单无效")
            require(len(values) == len(set(values)), "同批对象编号重复")
        covered.extend(ids)
    require(covered == [u["id"] for u in units if u["include"]], "批次必须按原文顺序完整覆盖应翻译单元一次，且不含排除内容")


def load_state(root):
    state = read(root / "progress.json")
    require(digest(Path(state["pdf"])) == state["pdf_sha256"], "PDF 已变化，请建立新任务")
    require(digest(Path(state["plan_path"])) == state["plan_sha256"], "计划已变化，请建立新任务")
    require(read(Path(state["plan_path"])) == state["plan"], "进度中的计划与原计划不符")
    validate_plan(state["plan"])
    require(state.get("mode") in ("sequential", "parallel"), "旧进度缺少执行模式，请核对任务后补充 mode 为 sequential 或 parallel；不要重置已有进度")
    state.setdefault("review_enabled", True)
    require(type(state["review_enabled"]) is bool, "审校设置必须为布尔值")
    return state


def parallel(state):
    return state["mode"] == "parallel"


def glossary(root, state, version=None):
    require(parallel(state), "普通翻译不启用术语表")
    versions = state.get("glossary_versions", {})
    version = version if version is not None else state.get("glossary_version")
    require(str(version) in versions, "术语表版本尚未发布")
    path = root / "glossary-versions" / (str(version) + ".json")
    require(digest(path) == versions[str(version)]["sha256"], "已发布术语表被修改")
    value = read(path)
    if version == state.get("glossary_version"):
        require(digest(root / "glossary.json") == digest(path), "当前术语表与已发布版本不一致")
    return value


def validate_glossary(value, state):
    require(type(value.get("version")) is int and value["version"] >= 1, "术语表版本无效")
    require(isinstance(value.get("terms"), list), "术语表缺少 terms 列表")
    seen = set()
    units = {u["id"] for u in state["plan"]["units"]}
    for term in value["terms"]:
        tid = identifier(term["id"])
        require(tid not in seen, "术语编号重复")
        seen.add(tid)
        for key in ("source", "translation", "scope"):
            require(isinstance(term.get(key), str) and term[key].strip(), "术语缺少原词、译法或适用含义")
        for key in ("aliases", "variants"):
            require(isinstance(term.get(key), list) and all(isinstance(v, str) for v in term[key]), "术语别名或允许变体无效")
        require(term.get("status") in ("tentative", "confirmed", "superseded"), "术语状态无效")
        require(isinstance(term.get("evidence"), list) and term["evidence"] and all(u in units for u in term["evidence"]), "术语缺少有效原文依据")


def validate_terms(root, state, report, plan):
    version = report.get("glossary_version")
    require(type(version) is int and version >= 1, "缺少有效术语表版本")
    snapshot = glossary(root, state, version)
    require(report.get("glossary_sha256") == state["glossary_versions"][str(version)]["sha256"], "报告的术语表指纹不匹配")
    terms = {t["id"] for t in snapshot["terms"]}
    usages = report.get("term_usage")
    proposals = report.get("term_proposals")
    require(isinstance(usages, list) and isinstance(proposals, list), "缺少术语使用记录或建议列表")
    for usage in usages:
        require(usage.get("term_id") in terms, "使用记录引用了本批术语表中不存在的术语")
        require(isinstance(usage.get("units"), list) and usage["units"] and all(u in plan["units"] for u in usage["units"]), "术语使用位置超出本批或为空")
    for proposal in proposals:
        for key in ("source", "translation", "scope"):
            require(isinstance(proposal.get(key), str) and proposal[key].strip(), "新术语建议缺少原词、实际译法或含义")
        require(isinstance(proposal.get("units"), list) and proposal["units"] and all(u in plan["units"] for u in proposal["units"]), "建议的原文位置无效")


def term_bindings(root, state, report, current=None):
    """仅追踪批次使用的条目及建议对应条目；不把无关新增视为冲突。"""
    current = glossary(root, state) if current is None else current
    used = {u["term_id"] for u in report["term_usage"]}
    proposed = {(p["source"].strip().casefold(), p["scope"]) for p in report["term_proposals"]}
    result = {}
    for term in current["terms"]:
        names = {s.strip().casefold() for s in [term["source"], *term["aliases"]]}
        if term["id"] in used or any((name, term["scope"]) in proposed for name in names):
            # 确认状态和证据更新不改变译法，不触发无意义返修。
            result[term["id"]] = {k: term[k] for k in ("source", "translation", "scope", "aliases", "variants")}
    require(used <= result.keys(), "已使用术语被移除，请保留编号并记录替代关系")
    return result


def batch_plan(state, bid):
    require(bid in state["batches"], "批次不存在")
    return next(b for b in state["plan"]["batches"] if b["id"] == bid)


def artifact(root, entry, bid):
    folder = root / "workers" / identifier(entry["task"]) / identifier(entry["attempt"])
    return folder / (bid + ".md"), folder / (bid + ".report.json")


def check_delivery(root, state, bid, check_snapshot=False):
    plan = batch_plan(state, bid)
    entry = state["batches"][bid]
    text_path, report_path = artifact(root, entry, bid)
    report = read(report_path)
    require(text_path.read_text(encoding="utf-8").strip(), "译文为空")
    for key, expected in (("batch", bid), ("task", entry["task"]), ("attempt", entry["attempt"])):
        require(report.get(key) == expected, "提交任务或尝试编号不匹配")
    for key in ("units", "equations", "figures", "tables"):
        require(report.get(key) == plan[key], "报告覆盖或对象清单不匹配：" + key)
    require(isinstance(report.get("issues"), list), "缺少问题列表")
    if parallel(state):
        validate_terms(root, state, report, plan)
    hashes = {"text_hash": digest(text_path), "report_hash": digest(report_path)}
    require(report.get("translation_sha256") == hashes["text_hash"], "译文指纹与报告不符")
    if check_snapshot:
        require(all(entry.get(k) == v for k, v in hashes.items()), "提交后产物被修改，必须重新提交或登记修订")
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
    require("tmp_gpt" in root.parts, "任务中间目录必须位于 tmp_gpt/ 下")
    state_path = root / "progress.json"
    if args.command == "init":
        require(not state_path.exists(), "进度已存在，禁止覆盖初始化")
        pdf, plan_path = Path(args.pdf).resolve(), Path(args.plan).resolve()
        require(plan_path.is_relative_to(root), "计划必须位于任务中间目录内")
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
            require(parallel(state), "普通翻译不创建或维护术语表")
            candidate = Path(args.file).resolve()
            require(candidate.is_relative_to(root) and candidate != root / "glossary.json"
                    and not candidate.is_relative_to(root / "glossary-versions"), "请在任务目录内用独立草稿文件发布")
            value = read(candidate)
            validate_glossary(value, state)
            require(args.reason.strip(), "发布必须说明新增或修改依据")
            version = state.get("glossary_version", 0) + 1
            require(value["version"] == version, "版本必须从 1 开始逐次递增")
            previous = set()
            if state.get("glossary_version"):
                previous = {t["id"] for t in glossary(root, state)["terms"]}
            require(previous <= {t["id"] for t in value["terms"]}, "不得删除已发布术语编号，请保留并记录替代关系")
            affected = []
            for bid, entry in state["batches"].items():
                if entry["status"] == "accepted":
                    report, _ = check_delivery(root, state, bid, True)
                    if entry.get("term_bindings") != term_bindings(root, state, report, value):
                        affected.append(bid)
            archive = root / "glossary-versions" / (str(version) + ".json")
            if archive.exists():
                require(read(archive) == value, "该版本文件已存在且内容不同，禁止覆盖")
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
            require(1 <= len(args.batches) <= 5 and len(set(args.batches)) == len(args.batches), "每任务应包含一至五个不同批次")
            require(not any(a["task"] == args.task and a["attempt"] == args.attempt for a in state["assignments"]), "任务与尝试组合已使用")
            order = [b["id"] for b in state["plan"]["batches"]]
            for bid in args.batches:
                batch_plan(state, bid)
                require(state["batches"][bid]["status"] in ("pending", "repair"), "批次已分配或已完成，需先登记修复")
            positions = [order.index(bid) for bid in args.batches]
            require(positions == list(range(positions[0], positions[0] + len(positions))), "任务包必须按序连续")
            folder = root / "workers" / args.task / args.attempt
            require(not folder.exists(), "任务产物目录已存在，使用新的尝试编号")
            folder.mkdir(parents=True)
            state["assignments"].append({"task": args.task, "attempt": args.attempt, "batches": args.batches})
            for bid in args.batches:
                state["batches"][bid] = {"status": "assigned", "task": args.task, "attempt": args.attempt}
        elif args.command in ("submit", "accept", "reject"):
            batch_plan(state, args.batch)
            entry = state["batches"][args.batch]
            if args.command == "reject":
                require(entry["status"] in ("assigned", "submitted", "accepted"), "当前状态不可登记修复")
                require(args.reason.strip(), "必须填写修复原因")
                entry["status"] = "repair"
                entry["reason"] = args.reason
                if args.batch in state["merged"]:
                    state["merged"] = state["merged"][:state["merged"].index(args.batch)]
                    state["output_stale"] = True
            elif args.command == "submit":
                require(entry["status"] in ("assigned", "submitted"), "批次不可提交")
                _, hashes = check_delivery(root, state, args.batch)
                entry.update(hashes)
                entry["status"] = "submitted"
            else:
                if state["review_enabled"]:
                    require(args.reviewed, "必须实际核对原文后传入 --reviewed")
                else:
                    require(not args.reviewed and not args.terms_reviewed, "已关闭审校，请省略 --reviewed 和 --terms-reviewed，避免误记为已审校")
                require(entry["status"] == "submitted" or (parallel(state) and entry["status"] == "accepted"), "仅已提交批次或需重新核对术语的已验收批次可验收")
                report, _ = check_delivery(root, state, args.batch, True)
                require(not report["issues"], "仍有未解决问题，不可验收")
                if parallel(state):
                    if state["review_enabled"]:
                        require(args.terms_reviewed, "子代理批次需主模型处理术语建议并传入 --terms-reviewed")
                    require(not report["term_proposals"] or args.terms_note.strip(), "本批含术语建议，请用 --terms-note 记录裁决及理由")
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
            require(ids, "没有连续已验收批次，拒绝生成空译文")
            output = Path(args.output).resolve()
            require(output != Path(state["pdf"]) and not output.is_relative_to(root)
                    and output != Path(__file__).resolve(), "最终文件不能覆盖原文、工具或任务中间文件")
            require(output.suffix.lower() == ".md", "最终译文必须为 Markdown 文件")
            if state.get("output"):
                require(str(output) == state["output"], "已有输出路径，禁止静默改写其他文件")
                require(output.exists() and digest(output) == state["output_sha256"], "最终文件被外部修改，请先保留用户改动并人工处理")
            else:
                require(not output.exists(), "输出文件已存在，选择新文件名以免覆盖用户内容")
            chunks = []
            for bid in ids:
                report, _ = check_delivery(root, state, bid, True)
                require(not report["issues"], "批次仍有未决问题")
                if parallel(state):
                    require(state["batches"][bid].get("term_bindings") == term_bindings(root, state, report),
                            "批次相关术语发生变化，请主模型核对并重新验收或交代理修复：" + bid)
                text_path, _ = artifact(root, state["batches"][bid], bid)
                chunks.append(text_path.read_text(encoding="utf-8").strip())
            output.parent.mkdir(parents=True, exist_ok=True)
            # 临时生成文件也位于任务的 tmp_gpt 目录，再写入最终路径。
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
        sub.add_argument("--root", required=True, help="tmp_gpt 下的任务目录")
        if command == "init":
            sub.add_argument("--pdf", required=True)
            sub.add_argument("--plan", required=True)
            sub.add_argument("--mode", choices=("sequential", "parallel"), default="sequential", help="普通顺序翻译或子代理翻译；默认 sequential")
            sub.add_argument("--review", choices=("on", "off"), default="on", help="是否内容审校，默认 on；仅用户明确关闭时用 off")
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
                sub.add_argument("--terms-note", default="", help="本批术语建议的裁决及理由，写入进度历史")
            if command == "reject":
                sub.add_argument("--reason", required=True)
        elif command == "merge":
            sub.add_argument("--output", required=True)
    try:
        print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as error:
        parser.exit(1, "错误：" + str(error) + "\n")


if __name__ == "__main__":
    main()

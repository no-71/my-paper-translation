# 进度文件与工具协议

工具为本 skill 的 `scripts/translation_state.py`，需 Python 3.9 或更高版本，无第三方依赖。相对路径基于任务工作目录，命令中的 `<...>` 替换为实际值。仅主模型修改进度、调用状态变更和合并命令；子代理只写专属目录中的译文及报告。

## 模式与初始化

- `sequential`：普通翻译，默认模式；不启用术语表，不要求术语字段。
- `parallel`：用户明确要求的子代理翻译，即使仅运行一个子代理也使用此模式；初始化后按 [术语协议](glossary-protocol.md) 发布第一版术语表，再分配任务。

模式持久化，不依据术语文件是否存在推断。旧进度缺少 `mode` 或任务需切换模式时，主模型核对实际执行方式、保留现有进度后明确登记模式，并补齐对应报告及术语版本；禁止重新初始化覆盖结果或静默切换。

在 `tmp_gpt/translation/<论文标识>/plan.json` 保存完整索引与计划。以下仅示范一个单元和批次：

```json
{
  "units": [
    {"id": "u0001", "pages": [1, 1], "chapter": "摘要", "kind": "paragraph", "source": "source.md#u0001", "include": true, "reason": ""}
  ],
  "batches": [
    {"id": "B001", "units": ["u0001"], "equations": [], "figures": [], "tables": [], "exception": ""}
  ]
}
```

- `units` 按阅读顺序排列，编号唯一，`source` 可回查真实原文；`pages` 为实际 PDF 起止页，含端点。
- 排除单元设 `include: false` 并填写原因。批次依序连接须恰好覆盖全部应翻译单元一次。
- 图注、表注单独列出或在所属单元内明确记录。对象清单使用原文编号，跨批正文引用不重复计作对象。
- 超过六页的批次在 `exception` 记录不可再拆分的单元及原因，由主模型确认。

```text
python3 <skill>/scripts/translation_state.py init --root tmp_gpt/translation/<论文标识> --pdf <原文.pdf> --plan tmp_gpt/translation/<论文标识>/plan.json --mode sequential
```

子代理模式将参数改为 `--mode parallel`。工具保存 PDF 和计划指纹，拒绝覆盖已有进度；原文或计划变化须建立新任务，不手改指纹绕过检查。

## 术语版本发布

仅子代理模式使用。主模型按术语协议准备草稿并发布：

```text
python3 <skill>/scripts/translation_state.py glossary-publish --root <任务目录> --file <任务目录>/glossary-draft.json --reason "涉及术语、原文依据及裁决理由"
```

版本从 1 逐次递增。工具保存不可变快照、当前表、指纹和历史，拒绝删除已发布术语编号；禁止手改已发布文件。工具不认证调用者身份，主模型独占写入由分工与代理指令约束。

## 分配与提交

子代理任务包大小按 [并行协议](parallel-translation.md)；普通模式可逐批分配。示例：

```text
python3 <skill>/scripts/translation_state.py assign --root <任务目录> --task T001 --attempt A001 --batches B001 B002 B003 B004 B005
```

工具创建 `workers/T001/A001/`，任务与尝试组合不可复用。每批保存 `B001.md` 和 `B001.report.json`。共同报告字段：

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
  "translation_sha256": "译文文件字节内容的 SHA-256"
}
```

清单须来自实际核对，不机械复制计划；问题写入 `issues`。子代理模式另加术语协议规定的版本、指纹、使用记录和建议字段；普通模式忽略旧报告中的术语字段。指纹可用 Python `hashlib.sha256(Path(...).read_bytes()).hexdigest()` 生成。

```text
python3 <skill>/scripts/translation_state.py submit --root <任务目录> --batch B001
```

工具核对任务、尝试、范围、对象清单及文件指纹；子代理模式还检查已发布术语版本及使用位置。存在问题可提交供检查，但不能验收通过。

## 验收与修复

主模型对照原文核对后验收普通批次：

```text
python3 <skill>/scripts/translation_state.py accept --root <任务目录> --batch B001 --reviewed
```

子代理批次须处理术语建议并确认兼容当前标准，额外传入 `--terms-reviewed`；含非空 `term_proposals` 时还必须以 `--terms-note` 记录逐项采纳、复用或拒绝的理由，写入进度历史：

```text
python3 <skill>/scripts/translation_state.py accept --root <任务目录> --batch B001 --reviewed --terms-reviewed --terms-note "逐项裁决及理由"
```

标志声明主模型已实际核对，工具不判断翻译语义、公式内容、术语含义或使用记录是否完整。核对标准遵循主 skill，术语裁决遵循术语协议。

术语发布后，工具绑定的相关条目发生变化时，将已验收批次标记 `terms_stale` 并排除出合并前缀。译文兼容则重新核对并用上述命令验收；确有冲突或需重派时：

```text
python3 <skill>/scripts/translation_state.py reject --root <任务目录> --batch B001 --reason "原文位置与修复要求"
```

随后使用新任务/尝试组合及新目录分配修复；同一代理修订也不得覆盖已提交产物。旧结果保留供追溯，不参与当前合并。工具不停止或检测代理，重派前由主模型按并行协议确认真实运行状态。

## 合并与状态

```text
python3 <skill>/scripts/translation_state.py merge --root <任务目录> --output translation/<论文名>.md
python3 <skill>/scripts/translation_state.py status --root <任务目录>
```

`merge` 按原文顺序重新生成从首批开始的连续已验收前缀，不追加。无有效前缀时拒绝空输出；提交产物被修改时拒绝合并。修复或术语复核可缩短前缀，须明确报告尚未完成。

输出不得覆盖原文、中间文件或其他任务的内容；已有不明来源文件时改用新输出名，已有最终译文被外部修改时先保留用户改动再处理。合并后报告范围，并按主 skill 做最终核对与交付。

状态为 `pending`（待分配）、`assigned`（翻译中）、`submitted`（已提交）、`accepted`（已验收）、`repair`（待修复）；`terms_stale` 表示术语需复核，`merged` 记录有效合并范围。`status` 返回模式、术语版本及批次状态，普通模式术语版本为 null。进度原子写入并保留事件历史；主模型顺序执行修改命令，不并发改写进度。

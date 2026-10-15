# My Paper Translation

简体中文 | [English](README.en.md)

论文翻译 skill。将论文 PDF 忠实翻译为可独立阅读的 Markdown，自动分批、保存进度，并支持中断续译和用户明确要求的子代理翻译。

这是供支持 skill 的 AI 编码代理使用的指令与辅助工具。模型负责读取 PDF、翻译和对照原文审阅；Python 脚本负责范围校验、进度管理和有序合并，不能单独完成翻译。

## 选择版本

| Skill 目录与调用标识 | 指令语言 | 译文目标语言 |
| --- | --- | --- |
| [`my-paper-translation-cn`](my-paper-translation-cn/SKILL.md) | 中文 | 默认中文 |
| [`my-paper-translation-en`](my-paper-translation-en/SKILL.md) | 英文 | 由用户指定 |

`cn` / `en` 表示 skill 指令的语言。除默认目标语言外，两版采用相同的翻译与进度规则。

中文版默认将论文翻译为中文，英文版需指定翻译目标语言。如需要修改部分翻译规则，请在提示词中说明。

## 运行条件

- Python 3.9 或更高版本；进度脚本仅使用标准库，无第三方依赖。
- 子代理能力为可选项，仅在用户明确要求时使用。实际并发数量取决于环境容量及待分配任务包数量。

## 安装

下载或克隆本仓库，将所选的**完整 skill 文件夹**复制到技能目录，保留其内部结构。

两个版本可以同时安装，通过各自的标识不同。仅复制 `SKILL.md` 不足以使用此 skill，协议文件和脚本也必须同步复制，请复制完整skill文件夹。

**使用 Codex 时**，技能目录为 `$CODEX_HOME/skills`；`CODEX_HOME` 默认为 `~/.codex/skills`(Windows下: `C:\Users\<User Name>\.codex`)。

例如，在未设置 `CODEX_HOME` 的 Bash 环境中，从仓库根目录安装中文版：

```bash
mkdir -p ~/.codex/skills
cp -R my-paper-translation-cn ~/.codex/skills/
```

## 使用示例

向代理提供可访问的 PDF，并在请求中指定 skill。

默认对译文进行审校，会增大Token开销，如需关闭审校，请在提示词中说明。

如需要修改其他翻译规则，也可在提示词中说明。

**中文版：**

```text
使用 $my-paper-translation-cn 翻译 papers/example.pdf。
```

**英文版，例如翻译成西班牙语：**

```text
Use $my-paper-translation-en to translate papers/example.pdf into Spanish.
```

**子代理并行翻译（可选，适合长论文）：**

```text
使用 $my-paper-translation-cn，通过子代理并行将 papers/example.pdf 翻译成中文。
```

```text
Use $my-paper-translation-en with subagents to translate papers/example.pdf into Spanish in parallel.
```

在环境支持且有足够任务可并行时，子代理翻译可加快长论文的翻译速度，但会增加模型用量（token 消耗）。

**指定范围或暂停条件：**

```text
使用 $my-paper-translation-cn 翻译 papers/example.pdf，本次只完成前两个批次，然后保存进度并暂停。
```

用户指定的翻译范围、批次数量、输出路径和暂停要求优先于默认行为。

## 输出与处理流程

先读取 PDF 并确认翻译范围，再按正文结构分批翻译、逐批核对并保存进度，最后按原文顺序合并已验收译文并交付。中断后可从已保存进度继续。翻译产生的中间文件均放置于`tmp_gpt/`文件夹下，翻译结果放置于`translation/`文件夹下

## 翻译范围与限制

- 翻译标题、摘要和正文，包括结论、正文脚注、图注、表题与表注；保留章节编号、标题层级、段落顺序和论述关系。
- 排除参考文献、附录及明确标记的补充材料，包括其中的公式和代码；按章节归属判断，不按页面位置截断正文。
- 正文公式保留符号、上下标、结构、编号及引用，以 LaTeX 输出；正文代码原样保留，相关自然语言说明翻译。
- 不插入图片；保留图号及引用并翻译图注。默认不逐项转录图内坐标轴和图例文字。
- 表体不超过 300 个非空白字符时保留表格内容；超过时改为明确标记的“表格内容概括”。计数包含单元格文字、数字和符号，不包含表题与表注。
- 除长表概括外，不删减、压缩或添加原文没有的解释。无法辨认的内容须记录位置并核对，仍无法解决时标记待核对，不猜测补全。

## 子代理翻译

默认由当前模型顺序翻译和核对，只有用户明确要求时才使用子代理。调用方式见“使用示例”。

此模式下，主模型负责原文准备、任务分配、术语维护、验收和合并，不翻译或改写译文；子代理负责翻译、自检和修订。初次任务包包含连续五批，最后一个可不足五批。只有容量和任务包数量均足够时才能实际并行，不能为凑并行随意拆小初次任务包。

子代理模式启用版本化术语表，每批固定使用一个已发布版本；术语变更后按实际使用记录复核相关批次。普通顺序翻译不要求独立术语表，但仍须保持术语一致。

环境不支持子代理时须说明限制；若用户要求必须由子代理翻译，则保存准备结果并报告阻碍，不自行替代。具体规则见各版本的并行与术语协议。

## 中断续译

保留原 PDF、任务中间目录和已有译文，并向代理提供原任务目录：

```text
使用 $my-paper-translation-cn 继续翻译 papers/example.pdf。原任务目录为 tmp_gpt/translation/example-task/，请核对已有进度后完成剩余批次。
```

```text
Use $my-paper-translation-en to resume translating papers/example.pdf into Spanish. The existing task directory is tmp_gpt/translation/example-task/. Verify the saved progress and complete the remaining batches.
```

恢复时核对原文和计划指纹，不重新初始化覆盖已有进度。原文或计划变化须建立新任务。待修复批次使用新的任务/尝试组合和目录，保留旧产物供追溯。

## 许可证

本项目采用 [MIT License](LICENSE)。

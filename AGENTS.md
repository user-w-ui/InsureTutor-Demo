# AGENTS.md

InsureTutor：基于双语保险宣传册的RAG问答机器人 demo。

## 项目资料

- [任务要求](docs/task-spec.md)
- [技术架构](docs/architecture.zh-CN.md)：模块边界、检索流程、引用与安全规则。
- [实现备忘](docs/implementation-notes.zh-CN.md)：数据契约、原文冲突与验证记录。
- [README](README.md)：安装、运行命令与当前进度。
- [原始数据说明](raw%20data/mineru-official/MANIFEST.md)：解析产物及来源。

## 工作约定

- 以简单、稳定、快速跑通为目标；关键设计变更与用户对齐，其余沿用已定架构择优实现。
- `raw data/` 是冻结输入；生成产物通过现有构建命令更新，不手工改写。
- 架构写入架构文档，实现细节写入备忘，使用方法写入 README；其他文件引用链接，避免重复。
- 中文显示异常先核对 UTF-8／字符码点，勿据终端乱码修改原文。
- 本机使用 PowerShell；多行 Git 提交说明写入临时文件，用 `git commit -F` 提交。

# AGENTS.md

InsureTutor：基于双语保险宣传册的RAG问答机器人 demo。

## 项目资料

- [任务要求](docs/task-spec.md)
- [技术架构](docs/architecture.zh-CN.md)：模块边界、检索流程、引用与安全规则。
- [实现备忘](docs/implementation-notes.zh-CN.md)：数据契约、原文冲突与验证记录。
- [README](README.md)：评委入口、项目概览与快速启动。
- [开发指南](docs/development.md)：本地安装、CLI、产物重建与评测命令。
- [原始数据说明](raw%20data/mineru-official/MANIFEST.md)：解析产物及来源。

## 工作约定

- 使用现有 `.venv`（Python 3.12）运行代码和测试：`.\.venv\Scripts\python.exe ...` 或 `uv run --locked --extra agent --extra dev ...`，无需激活。依赖报错时先核对解释器，勿依据系统 Python 误判依赖未安装。
- 以简单、稳定、快速跑通为目标；关键设计变更与用户对齐，其余沿用已定架构择优实现。
- 校验仅检查格式与本轮已提交引用；不增加数字、措辞、漏答或漏引的正文检查。
- 网页启动见 README，依赖安装与评测见开发指南；正式网页在 `src/insuretutor/web/`。
- `raw data/` 是冻结输入；生成产物通过现有构建命令更新，不手工改写。
- 架构写入架构文档，实现细节写入备忘，评委启动写入 README，开发命令写入开发指南；其他文件引用链接，避免重复。
- 中文显示异常先核对 UTF-8／字符码点，勿据终端乱码修改原文。
- 本机使用 PowerShell；多行 Git 提交说明写入临时文件，用 `git commit -F` 提交。

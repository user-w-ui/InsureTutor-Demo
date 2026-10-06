# InsureTutor 实现备忘

本文件保存当前数据契约、来源差异、实现细节和验证限制。
模块边界与流程见[技术架构](architecture.zh-CN.md)，启动见[README](../README.md)，开发与评测命令见[开发指南](development.md)，
术语见[CONTEXT](../CONTEXT.md)。语料、检索、Tutor、CLI、FastAPI、网页及 Docker 均已实现。

## 数据产物与冻结输入

`raw data/` 保持冻结。离线 cleaner 读取 MinerU 解析与
`data/cleaning-rules.json`，生成 `data/cleaned/`；corpus builder 再生成
`data/corpus.json`，这是后续 RAG 的运行时输入。

- [清洗产物](../data/cleaned/README.md)、[九表／十注释映射](data-cleaning-map.md)：格式、来源与已核对关系。
- [清洗调研](data-cleaning-plan.md)、[数据溯源](data-provenance.md)：阶段性依据，保留原记录。
- `cleaning-rules.json` 集中保存脚注、必需关系、质量标记、来源冲突、有限文本更正、
  语言边界及表头／上下文关联；不要按页面邻近重新猜测脚注归属。
- `corpus-rules.json` 只保存语料格式版本和两条独立免责声明的对应关系。
- 原文更正记录来源 block、物理页和理由；不修改 MinerU 原始文件，不认证全文语义一致。

### Corpus 契约

`corpus.py` 集中定义 Pydantic 数据模型和两个入口：
`build_corpus(...) → Corpus`、`assemble_evidence(corpus, unit_ids) → EvidenceBundle`。

| 产物 | 当前数量／用途 |
| --- | --- |
| 逻辑单元 | 137 个，保留原 ID、kind、requires、脚注与冲突关系 |
| 语言记录 | 274 条，每单元有独立 `zh-Hant/en` 正文，无混排父块 |
| 来源片段 | 660 个，保存原文、语言、物理页与来源范围 |
| 检索子块 | 275 条：中文 137、英文 138；英文排除条款拆为两块 |

格式版本为 2。语言记录包含
`id/pair_id/parallel_id/language/title/text/source_span_ids/context_span_ids`。
`pair_id` 等于逻辑单元 ID，`parallel_id` 互指，正文与上下文来源属于各自语言。
每对表示同一条款／逻辑行，不证明中英文语义一致；`evidence_group` 不用于合并不同事实。

清洗规则包含 155 条已核对语言边界。英文无中文字符，中文可保留网址、币种和产品代码；
不输出 `mixed/und/shared` 语言文本。非相邻的同语言片段之间只补空白，数字按相应表头
进入两份语言记录。两条独立免责声明通过 `parallel_units` 关联。

引用取来源片段的 `evidence_text`，保留 `text_origin`。
`origin_span_id/origin_ranges/origin_evidence_sha256` 追溯拆分前的解析或 PDF 校对文本；
字符范围为 Unicode 索引，左闭右开。按拆分后的来源 ID 去重，不能因为共同 origin ID
而把两种语言合并。配对状态沿用 `same_topic_not_equivalence` 或 `reviewed_source_conflict`。

Tokenizer 固定为 E5 revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，
本地 `tokenizers==0.21.4` 测长。检索块连同标题、表头、`passage: ` 和特殊 token
目标 256、上限 512；按句子／短语切块，无固定重叠，不静默截断。
OpenCC 只规范化检索文字；引用原文不变。构建测试核对配对、范围、关系完整性及字节一致性。
构建源码的哈希也进入 provenance；修改这些源码后需显式重建语料与索引，即使正文未变。

### 已确认原文冲突

物理 PDF 第 17 页，`table-354-row-5` 的最低增加／减少保障额：

| 原文语言 | 美元 | 港元 | 澳门元 |
| --- | ---: | ---: | ---: |
| 中文 | 5,000 | 40,000 | 400,000 |
| 英文 | 5,000 | 400,000 | 40,000 |

双方已对照 PDF 确认。数据不选任一版本为权威；已引用该单元时，服务端保留双方原文并
附冲突说明。仅召回而未用于回答的冲突不改变整题状态。

### PDF 页码与定位

`pdf_page = page_idx + 1`，封面计入；不使用印刷标签或偏移推断引用页。
物理第 6 页的章节号 `1` 曾被 MinerU 当成页码，实际印刷页为 `5`。
原始标签与已核对标签分别保存；未经核对的标签不猜测。

原始 bbox 在 0–1000 范围，不能当作 PDF 点值。网页按当前页面尺寸比例映射，缩放后
仍对齐；文本来源高亮原始块，`whole_table` 高亮整表，不声称逐句、逐行或逐格精度。
无有效 bbox 时只跳到物理页。字符范围用于溯源，不等于 PDF 字符级几何坐标。

## 本地模型、索引与检索

`embedding.py` 管理固定 FP32 ONNX 资产、本地编码和 SHA-256；`index.py` 管理向量
及 manifest；`lexical.py` 管理规范化与标题别名；`hybrid.py` 实现唯一 Retriever 边界。

- 固定 FastEmbed 0.8.1、ONNX Runtime 1.24.2、NumPy 2.3.5、rank-bm25 0.2.2。
  自定义 E5 注册指定 attention-mask 均值池化和 L2 归一化，384 维，默认 2 个 CPU 线程。
- 查询与文档共用 NFKC、空白合并、OpenCC t2s；应用只加一次 `query: / passage: `。
  编码前按真实 tokenizer 测长，超过 512 明确报错。运行时禁止下载。
- `models/` 被 Git 忽略；主权重 470,268,510 字节，总资产约 487 MB。
  固定版本及文件哈希见 [模型／向量说明](../data/retrieval/README.md)和[tokenizer](../data/tokenizer/README.md)。
- 提交的向量为 275 × 384 float32（422,528 字节）。manifest 固定语料哈希、视图行序和
  编码／模型／tokenizer 哈希；初始化检查校验和、维度、dtype、有限值及单位范数。
  错配或损坏明确报错，不自动重建。
- BM25 使用中文二元组、英文小写词、数字／百分比／货币；排除英文常见虚词，保留否定。
  14 对双语标题逐项校验原文，只作词法别名，不进入向量文本或引用。
- 中英子块先按逻辑单元归并；多个查询按排名投票归并，两路各取 12 个单元，
  等权 RRF 常数 60。最多 8 个直接命中，完整来源预算 12,000 字符。
- 脚注可独立排名；正文命中沿 `requires` 强制补全，自动补入不占 top-k。
  表头、上下文和冲突双方整组加入，超预算跳过整组，不截断条件。

首轮工具入口传入完整原问，并设置 `expand_sentences=True`；检索器最多按标点展开
4 句，每句至少 6 字。Agent 补查关闭展开，应用不对多次工具结果融合排名。
可选 `rewritten_query` 由 Retriever 支持，但 Tutor 首轮不调用模型改写。
CPU 编码由串行工作线程执行；取消异步调用也不会提前释放仍在编码的线程锁。

### 已提交的 E5 评测

[评测报告](../data/retrieval/evaluation.json)含 7 个非拒答案例 × 英文／简中／繁中／原题，
共 28 个查询案例。混合路启用首轮多句展开；BM25／向量基线不展开，因此差异不只来自 RRF。

| 方法 | Recall@5 | 完整 bundle 的核心单元覆盖 | requires 补全覆盖 |
| --- | ---: | ---: | ---: |
| BM25 | 61.90% | 74.64% | 100% |
| 向量 | 55.65% | 72.32% | 100% |
| 混合（多句展开） | 61.01% | 80.18% | 100% |

Recall@5 按主单元 ID 宏平均；核心覆盖按明确 ID 计，其他表格行的等价证据可能被低估。
requires 覆盖只证明已选正文的条件完整，不证明所有子问题已召回，也不是答案正确率。
报告环境为 Windows 11、Python 3.12.13、2 个 CPU 推理线程；报告的循环计时同时包含
未展开与展开两次排名，不能直接当作生产单问延迟。断网初始化／推理、重复查询一致、
tokenizer 一致和三行向量重编码误差为 0 的检查均记录在报告中。

## 对话与证据注入

Tutor 每轮新建 `EvidenceSearchSession`，先检索一次，再给 Agent 原问、有限历史、
初始证据与剩余额度。唯一工具为 `search_evidence(query)`；它不能选择索引、文件、URL、
top-k 或预算。首次、无效、空结果、超预算及缓存命中的尝试均计入 6 次检索限额。
缓存按规范化查询与展开模式区分；新结果超出本轮来源预算时整组拒绝。

`session.agent_json(result)` 是正式注入入口，使用 `SearchResult.to_agent_json()` 序列化。
完整中英父块、底层原文、表头、必需关系、物理页及冲突标记进入模型；每轮定义仅发送一次，
重复结果引用已提供 ID。来源使用本轮短编号 `s1/s2/...`，最终草稿只能引用逻辑单元 ID。
真实 ID、bbox、origin 范围及完整 bundle 保存在服务端；不把证据放进系统指令。

系统策略为 `generation.py` 的 `POLICY`，schema 与模型自检清单同属固定指令。
要求自然、连贯的短段落，保持原文条件与非保证含义；模型自检不属于服务端正文校验。
普通 Chat Completions JSON 输出，不依赖 API JSON mode 或 SDK `output_type`。
关闭 SDK tracing 和模型自动重试；`medium`、32,768 token、60 秒总超时。
主循环最多 7 个 SDK 回合，另留 1 次无工具格式／引用修复，修复共享总超时。

SessionStore 保留 128 个会话、空闲 TTL 30 分钟、最近 6 轮已接受问答及 6,000 字符历史，
同会话串行。历史只理解指代，每轮重新检索／登记引用，不保存 SDK 工具轨迹。
过期或未知 ID 创建新会话并提示重置；刷新网页或新对话清空浏览器内存。

### 答案契约与校验

完整契约见 [chat_models.py](../src/insuretutor/chat_models.py)。模型输出
`status + claims[{text,evidence_ids}] + clarification_question`；模型状态为
`answered/clarification/refused/insufficient`，服务端另持有 `source_conflict/excerpts`。

- Pydantic 校验 JSON、字段类型、状态及字段组合；不解析措辞、数字、语言比例、漏答或漏引。
- 已提交的证据／公式 ID 必须属于本轮提供的 bundle；未召回、旧轮或虚构 ID 不可引用。
- 必需单元、来源片段、表头和上下文必须可完整解析；原文、页码、bbox 与链接由服务端生成。
- 未附引用的段落正常展示。引用有效不证明来源支持主张、回答完整、安全或算术正确。
- `boundary` 使用固定代码并替换为服务端文案，同一代码只保留首条，避免逐话题重复同一句；`user_condition` 展示标签及模型提交的用户文本；
  `application` 保留模型正文并添加条件标签。后两者不进行用户输入语义核验。
- 算例提示词只允许本册身故保障三项公式；服务端检查公式引用，不核对输入、不复算结果。
- 格式与无效引用共用最多一次无工具修复，不填补漏答、漏引或润色内容。仍失败则整份摘录；
  不保留基于数字检查的部分降级。未配置模型、API／工具失败、超时或回合耗尽也使用摘录模式。
  检索失败或最终无证据则明确说明不足。

质量与安全措辞由模型指令和评测负责；权限限制、引用白名单和文本节点渲染由程序保证。
不会增加正文正则、安全审查模型或语义修复调用。

## HTTP、网页与 Docker

FastAPI lifespan 创建共享检索器、Generator、Tutor 与会话存储，关闭时释放模型客户端。
启动核对语料、向量、权重和原始 PDF 哈希；PDF 只作校验与原件展示，运行时不解析 PDF。
HTTP 接口、错误码和布局见架构；`reference_groups` 只从本轮引用及 corpus 必需关系恢复，
不重复检索或调用模型。语言切换展示两份原文；旧轮引用在当前页面内仍可点击。

正式网页为 `src/insuretutor/web/`，PDF.js 5.4.149、worker 及许可证本地提供。
网页使用 `/api/chat/stream`（`fetch` + `ReadableStream` 解析 SSE，`EventSource` 不支持 POST），
等待上限 75 秒；完整响应仍在通过格式／引用校验后一次显示，网络失败或流中断保留问题。
日志只记录请求 ID、耗时、状态及原因码，不记录问题、答案、完整提示、证据正文或密钥。

### 流式过程事件

Tutor 的 `answer(turn, progress=None)` 接收只读回调；`/api/chat` 与 CLI 不传回调，行为不变。
事件模型在 `chat_models.py`（`StageProgress`、`SearchProgress`），字段白名单、`extra=forbid`；
HTTP 层为每个事件附加自请求开始的 `elapsed_ms`。回调异常被吞掉，不影响检索或作答。

| 事件 | 来源与内容 |
| --- | --- |
| `stage` | `retrieving`（Tutor 首轮前）、`thinking`（`RunHooks.on_llm_start`，附第 n 次模型调用）、`searching`（`on_tool_start`）、`validating`（每次本地校验前）、`repairing`（无工具修复前）、`fallback`（附服务端原因码） |
| `search` | `EvidenceSearchSession` 每次检索后产生：`kind`、补查查询（截断 200 字，首轮不回显原问）、状态、最多 8 个直接命中、自动补入的必需单元数、剩余检索次数 |
| `final` | `{response, elapsed_ms}`，`response` 与 `/api/chat` 响应体相同；降级同样以 `final` 结束 |
| `error` | `sessions_busy` 或 `internal_error` 及请求 ID，不含异常文本 |

命中标签与引用链接共用 `references.display_title`：有标题用标题，`note-N` 显示附注编号，
否则取首个来源片段首行（最多 80 字）；英文回答用英文记录，其余用繁中原文。事件不含完整来源正文、
系统提示、模型 token、推理文本或密钥。同一模型回合可连续请求多次补查，会先出现多个 `searching`。
请求体校验失败仍在流开始前返回 422 JSON。本轮作为独立任务运行，任务引用保存在 `app.state`；
客户端断开只停止推送，任务继续完成、写入历史并记录一行日志（与 `/api/chat` 断开时行为一致，
已用 ASGI 断开实验确认）。流式请求的日志在任务完成时写出，附 `stream=1`。

`reasoning_content` 调研（未实现）：openai-agents 0.22.3 的 Chat Completions 非流式路径会把消息上的
`reasoning_content`（DeepSeek 等）、`reasoning` 或 `thinking_blocks` 转为 `ResponseReasoningItem`，
保持 `Runner.run` 时可在 `on_llm_end(response)` 按每次模型调用整段取得；token 级推理需要改用
`Runner.run_streamed`。OpenAI 官方 Chat Completions 不返回推理文本。推理可能复述证据、系统提示或注入指令，
展示前需要单独的脱敏／摘要设计。

Docker 为 Python 3.12 slim、uv 0.11.15、锁定运行依赖与 agent extra、非 root、单 worker。
构建阶段缓存固定 E5 模型层；运行无宿主源码／模型挂载，Compose 只在运行时注入 LLM 配置。
默认发布 `127.0.0.1:8000`；`.env` 的 `PORT` 可改变宿主端口，容器内部保持 8000。
`.dockerignore` 允许列表排除密钥、tests、清洗中间产物与本机环境。
`scripts/start-demo.ps1` 构建后等待容器健康，再按实际发布端口打开浏览器。

## 验证记录与已知限制

- 2026-10-06 流式过程展示：全量离线测试 175 项、305 个子检查通过（含边界去重回归；新增 8 项流式测试：事件顺序、
  与 `/api/chat` 结果一致、未配置模型／格式修复降级、超时、错误脱敏、断开后完成、回调失败隔离）；
  改动模块 Ruff 通过。Docker 真实模型下 q3（额外回报率与保证利率）三次流式运行：

  | 运行 | 首轮检索 | 模型调用（秒） | 补查 | 总耗时 | 结果 |
  | --- | ---: | --- | ---: | ---: | --- |
  | 1 | 0.06 s | 5.8／13.8 | 2 次，各约 0.02 s | 19.8 s | answered，3 检索／2 调用 |
  | 2 | 0.06 s | 10.3／2.6／27.0 | 4 次，各约 0.02 s | 40.2 s | answered，5 检索／3 调用 |
  | 3 | 0.07 s | 6.1／12.3 | 2 次，约 0.11／0.02 s | 18.6 s | answered，3 检索／2 调用 |

  耗时主要在模型调用；校验约 0.02 s。客户端到达时间与服务端 `elapsed_ms` 同步，固定偏移约 0.12 s，
  无缓冲。浏览器确认进度列表、补查占位替换与答案上方的折叠记录；真实容器中断开连接后本轮仍完成并记录日志。
- 本次交付整理：166 项离线测试、305 个子检查通过；包含冻结输入与语料重建字节一致性。
  修改的运行时模块 Ruff 通过；未为风格告警改写哈希固定的离线构建源码。
  一键脚本实际构建、等待健康并打开网页；容器资源与工作区文件哈希一致，PDF Range、
  非 root、镜像排除、断网检索及无模型摘录验证通过。浏览器可加载正式页面与 PDF。
- 离线测试使用替身编码器与真实 SDK Runner 的脚本模型，覆盖格式、引用、工具循环／限额、
  超时／修复、会话、语言、冲突、来源完整性及 API 错误／PDF Range。不需要模型 API 或权重。
- 格式／引用边界收窄后的定向测试 86 项通过；此前容器内 q3 连续三次 `answered`，
  耗时 26.07／18.48／29.45 秒，均为 3 次检索、2 次模型调用，无修复或摘录降级。
  随后的 POLICY 文案核对通过 48 项对话测试；这些记录不构成全量语义质量认证。
- 已验证容器健康、静态资源、PDF `206/416`、断网本地检索与无模型摘录。
  代表性真实模型请求验证过补查、追问、冲突和提示注入／购买／收益边界；单次成功不证明
  抵御所有注入，也不代表当前提示词版本的所有题目已通过。
- q7 的精确版本号位于 corpus 元信息，未出现在可引用来源中；不能绕过本轮来源白名单引用。
  多子问题、模糊购买意图及算例仍需人工核对语义；当前校验不会检测模型漏答、漏引或算术错误。
- 10 道题及补充三语／多轮场景只在 `tests/eval/`；评测答案和评分标准不进入模型上下文或索引。
  全量真实模型评测命令见开发指南；本次文档与清理工作不替代该评测。
- 旧内容校验和部分降级的设计记录保留在 Git 历史；临时诊断草稿、提示快照和截图不随仓库交付。

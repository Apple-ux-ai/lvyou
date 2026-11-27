# TravelMate 项目与 RAG 优化实施计划

> 日期：2026-08-15
>
> 目标：在保持本地单用户运行方式和现有 SSE/API 契约基本稳定的前提下，提升知识召回质量、索引可靠性、对话连续性和运行可观测性。

## 实施状态

本计划已转为滚动执行记录。当前已完成代码实现并验证的重点是：知识解析与增量索引、embedding provider 抽象、JSON fallback 缓存、BM25+dense 混合检索、会话与 SSE 链路、意图识别和健康检查。Windows 本地运行配置已切换到 `sentence-transformers` 和 `BAAI/bge-small-zh-v1.5`，使用独立版本化索引；Hash provider 仅保留为显式离线开发和自动化测试路径，默认配置继续关闭无提示 fallback。

最近一次完整回归：后端 `111 passed`，Vitest `10 files / 38 tests`，Playwright `9 passed`。BGE 独立质量门禁为 Recall@1 `0.95`、Recall@3 `1.00`、Recall@5 `1.00`、MRR `0.975`，平均检索延迟 `18.457 ms`；`/api/health` 返回 `status=ok`，模型、512 维向量、manifest、10 个来源和 28 个 chunk 均兼容。交付时仍需处理的外部或人工任务是轮换本地 API key，以及完成一次用户确认的真实备份恢复演练。计划中的 `[ ]` 表示仍需实施或补测，`[x]` 表示已有实现和本轮证据支持。

`build_bge_index.ps1` 已固化为“独立版本构建 → 指向新版本评测 → 通过门禁后激活”的顺序；质量门禁失败时不会切换 active pointer。BGE 激活后还必须在 `backend/.env` 配置 `TRAVELMATE_INDEX_ROOT=index_versions` 和 `sentence_transformers` provider，运行时才会读取版本化索引。

## 1. 实施前基线

当前项目是 Windows 本地运行的 FastAPI + SQLite + Chroma/JSON fallback + DeepSeek 适配器，知识文件位于 `backend/data/knowledge/`。

已确认的基线问题：

- 当前 `HashEmbedding` 是 512 维字符 n-gram 哈希，并非真正的语义 embedding。
- 当前索引有 225 个 chunk，平均 chunk 长度约 17.9 个字符，切分粒度过细。
- 现有 `golden_qa.json` 按预期 source 计算，生产阈值 `min_score=0.3` 下 Top-3 命中为 3/20。
- 知识目录有 10 个文件，当前 `knowledge.json` 只有 8 个 source，Bangkok 两份知识没有进入当前索引。
- Windows 默认使用 JSON fallback；查询会重复读取全量 JSON，且没有稳定的索引 manifest。
- 当前上游 LLM 使用 `stream=False`，前端每次请求没有传递 `session_id` 和 `history`。

## 2. 目标与非目标

### 目标

- 召回质量：`Recall@3 >= 0.80`，`Recall@5 >= 0.90`，以黄金问答集为第一版验收基线。
- 索引一致性：知识文件、chunk、embedding 模型版本和索引内容可校验、可重建、可回滚。
- 运行性能：查询不再每次从磁盘解析整个 JSON；记录 embedding、检索、LLM 各阶段耗时。
- 对话正确性：多轮历史可用，行程意图与普通问答不再依赖脆弱的关键词组合。
- 兼容性：保持 `/api/chat`、`/api/trips` 和前端 SSE 事件名称不变，分阶段替换内部实现。

### 非目标

- 本阶段不迁移 PostgreSQL、Qdrant 或 Docker。
- 本阶段不重做 14 个前端页面的视觉设计。
- 本阶段不引入 LangChain/LlamaIndex；先把现有链路做成可测量、可替换的模块。

## 3. 实施顺序

依赖关系如下：

```text
安全与评测基线
        ↓
知识解析 / chunk / manifest
        ↓
Embedding provider + 全量重建索引
        ↓
混合检索与阈值校准
        ↓
对话、流式、会话和前端契约
        ↓
运行监控、备份、CI 和清理
```

不要在没有完成评测基线和索引版本化之前直接替换 embedding 模型。

## 4. Phase 0：安全与可测量基线

### 任务

- [ ] 立即撤销并重新生成 `backend/.env` 中的 API key；确认 key 没有进入日志、备份或共享目录。
- [x] 扩展 `backend/.env.example`，补充向量后端、embedding 模型、设备、batch size 和检索阈值配置。
- [x] 新增 `backend/scripts/evaluate_retrieval.py`：读取 `backend/tests/golden_qa.json`，输出 `Recall@1/3/5`、MRR、每题 top source、分数分布和平均检索耗时。
- [x] 新增当前 fallback 评测报告 `docs/retrieval-evaluation-2026-08-15.json`；该报告明确记录 provider 和模型版本，不能替代 BGE 评测。
- [x] 修复本地测试运行条件；Python、Vitest、SSE 契约测试已通过，Playwright E2E 在本轮继续执行。

### 涉及文件

- `backend/.env.example`
- `backend/app/core/config.py`
- `backend/scripts/evaluate_retrieval.py`
- `backend/tests/golden_qa.json`
- `backend/tests/unit/test_config.py`

### 验收标准

- 无明文 key 被提交或输出。
- 一条命令可以生成检索基线报告。
- 测试命令能在正常可写环境中完成收集和执行。

## 5. Phase 1：知识解析、切块与索引生命周期

### 5.1 统一知识解析

- [x] 新增 `backend/app/rag/chunking.py`，统一处理 Markdown 和真正的 JSON。
- [x] Markdown 按标题、段落和列表语义切分，不再按每一行直接生成 chunk。
- [x] 每个 chunk 采用目标长度、overlap 和长段落边界策略；短章节可以合并，标题上下文不会被丢弃。
- [x] 对每个 chunk 加上标题和 section 上下文，让短内容具备可检索语义。
- [x] `kansai-7d.json` 已修复为合法 JSON，并通过 JSON parser 处理。
- [x] `source_id` 保持 stem 兼容，并在同名文件时中止入库。

### 5.2 建立索引 manifest

- [x] 为每个源文件保存 `source_id`、相对路径、`sha256`、chunk 数和解析器版本等 manifest 信息。
- [x] 内容 hash、chunking 版本和 embedding 版本未变化时跳过 embedding。
- [x] 内容变化时只替换该 source 的新版本 chunk。
- [x] 当前知识目录已经不存在的 source 会从索引和 manifest 中删除。
- [x] JSON 索引和 manifest 使用临时文件原子替换；版本不匹配时先清理并重建。
- [x] `--reset` 使用公开的 `delete_source()`/`reset()` 操作。

### 涉及文件

- 新增 `backend/app/rag/chunking.py`
- 新增 `backend/app/rag/index_manifest.py`
- 修改 `backend/scripts/ingest.py`
- 修改 `backend/app/rag/chroma_store.py`
- 新增或修改 `backend/tests/unit/test_chunking.py`
- 新增或修改 `backend/tests/integration/test_ingest_sync.py`

### 验收标准

- 10 个知识文件全部出现在 manifest 和索引中。
- 重复执行入库不会重新计算未变化文件的 embedding。
- 修改、删除、恢复知识文件后，索引与知识目录最终一致。
- 任意 chunk 都能追溯到源文件和标题路径。

## 6. Phase 2：Embedding provider 与版本化重建

### 6.1 Provider 抽象

- [x] 新增 `backend/app/rag/embeddings.py`，统一提供批量文档编码和单 query 编码接口。
- [x] embedding provider 工厂统一由 `embeddings.py` 管理，索引器和查询器共享同一 provider 结构。
- [x] 默认语义模型配置为 `BAAI/bge-small-zh-v1.5`；多语模型暂不作为默认路径。
- [x] `sentence-transformers` 批量编码显式开启归一化，Hash fallback 也保持归一化输出。
- [x] provider、模型、维度、归一化和版本写入 manifest/health；版本或维度不匹配会触发重建或拒绝混用。
- [x] 默认关闭无提示 fallback；本地 `backend/.env` 显式使用 `hash` 离线 provider，生产环境需显式配置 `sentence_transformers` 并安装、验证语义模型。

### 6.2 缓存与重建

- [x] 以 `content_hash + embedding_model_version` 持久化 SQLite embedding cache；cache 还包含 chunk、模型 id 和维度，避免不同向量契约复用。
- [x] 对文档 embedding 批量处理，对 query 每次只编码一次。
- [x] 重建前自动备份当前索引；`IndexVersionManager` 支持独立版本目录和备份，旧索引仍可恢复。
- [x] 新旧索引可并存并通过 `TRAVELMATE_INDEX_ROOT`、active pointer 和 `TRAVELMATE_INDEX_VERSION` 切换。

### 涉及文件

- 新增 `backend/app/rag/embeddings.py`
- 修改 `backend/app/rag/chroma_store.py`
- 修改 `backend/app/core/config.py`
- 修改 `backend/.env.example`
- 新增 `backend/tests/unit/test_embeddings.py`
- 新增 `backend/tests/integration/test_embedding_compatibility.py`

### 验收标准

- 索引和查询使用同一模型版本、维度和归一化策略。
- 旧模型向量不会和新模型向量混入同一 collection。
- 全量重建可重复执行，结果稳定，且能通过 manifest 校验。
- [x] hash fallback 评测达到 `Recall@3=1.00`、`Recall@5=1.00`，并通过当前质量门禁。
- [x] BGE 语义模型已在独立版本 `bge-small-zh-v1.5` 完成评测并激活，Recall@3 `1.00`、Recall@5 `1.00`，通过质量门禁。

## 7. Phase 3：混合检索与 Windows 存储优化

### 任务

- [x] 增加中文 unigram/bigram/trigram BM25 检索层，覆盖地名、数字和专有名词。
- [x] dense 和 lexical 各取候选，再按可解释的配置权重合并。
- [x] 对同一 source 的多个 chunk 去重，并保证结果覆盖不同 source。
- [x] 统一正式检索链路的阈值、top-k 和低置信度过滤；引用只来自实际存在且达到阈值的 source。
- [x] 低置信度时不把任意低分文档放入 prompt。
- [x] Windows JSON fallback 将记录和 embedding 矩阵路径缓存到内存，避免每次查询重新解析磁盘 JSON；Chroma 显式 backend 仍保留集成测试入口。
- [x] `/api/health` 报告 backend、source/chunk 数、embedding 版本/维度和兼容性。

### 涉及文件

- 新增 `backend/app/rag/lexical_retriever.py`
- 修改 `backend/app/rag/chroma_store.py`
- 修改 `backend/app/services/rag_chat.py`
- 修改 `backend/app/rag/pipeline.py`
- 修改 `backend/app/main.py`
- 新增 `backend/tests/integration/test_hybrid_retrieval.py`
- 新增 `backend/tests/unit/test_retrieval_evaluation.py`

### 验收标准

- [x] 当前 hash fallback 黄金问答达到 `Recall@3=1.00`、`Recall@5=1.00`；BGE 结果待补测。
- [x] citation 去重，source 与实际索引存在性一致。
- [x] 已记录当前评测 P50/P95 检索耗时，并增加 1,000 chunk fallback 内存复用回归测试。
- [x] 低相关结果按阈值过滤，不进入 prompt。

## 8. Phase 4：对话链路正确性

### 任务

- [x] `DeepSeekLLMAdapter` 已支持真实上游 SSE delta，并转换为现有 SSE `message` 事件。
- [x] 保持 `itinerary`/`done` 兼容，并覆盖上游中途断开、超时和取消请求测试。
- [x] 前端持久化 `session_id` 和最近三轮 history；后端执行角色、长度和 session 数量校验。
- [x] `is_plan_intent()` 已分离目的地识别与签证/天气等普通问答。
- [x] 已取消“日本一律映射为京都”的规则，使用目的地识别结果。
- [x] `days` 已限制在 1-30 天范围内。
- [x] prompt 要求只使用检索证据，并在证据不足时避免伪造引用。
- [x] 对外返回通用错误码，详细异常写本地日志，CORS 使用配置化 allowlist。

### 涉及文件

- 修改 `backend/app/services/rag_chat.py`
- 修改 `backend/app/rag/pipeline.py`
- 修改 `backend/app/main.py`
- 修改 `backend/app/models/schemas.py`
- 修改 `shared/api.js`
- 修改 `pages/assistant.html`
- 新增或修改 `backend/tests/contract/test_sse_contract.py`
- 新增或修改 `backend/tests/integration/test_chat_api.py`
- 新增或修改 `frontend/tests/api-client.test.js`

### 验收标准

- 首个 SSE message 在上游开始返回后即可到达前端，而不是等待完整答案。
- 同一个 session 的第二个问题能使用上一轮上下文。
- 普通问答不会意外产生 itinerary 事件。
- 上游错误、断线和无证据场景都有稳定的 SSE 终止行为。

## 9. Phase 5：测试、运维与低优先级清理

### 测试矩阵

- [x] 单元测试：chunk 边界、Markdown/JSON 解析、embedding 维度、归一化、source 去重。
- [x] 集成测试：覆盖入库同步、新旧 embedding 版本隔离和 1,000 chunk Windows fallback 内存复用。
- [x] 质量测试：已输出全部 `golden_qa.json` 的 Recall、MRR、citation precision 和耗时报告；当前 fallback 质量门禁通过，BGE 质量结果待补测。
- [x] 契约测试：SSE message/itinerary/done/error 事件、前端解析以及 `session_id/history` 请求体。
- [x] E2E：从首页提问、生成行程、保存、编辑、刷新后读取；Playwright `9 passed`。
- [x] 增加 `backend/scripts/verify_retrieval.ps1` 和评测脚本阈值参数，每次知识库或 embedding 变更可在 CI/发布阶段强制检查 Recall。
- [x] 增加 `backend/scripts/build_bge_index.ps1` 和 `backend/scripts/activate_index.py`，固化 BGE 依赖探测、独立版本重建、先评测后激活的质量门禁流程；已完成真实构建，修复 Windows PowerShell 5.1 的相对路径兼容问题，并让本地启动器从已验证缓存离线加载模型，避免 Hugging Face 网络检查阻塞启动。

### 运维

- [x] 增加完整运行指标：request id、embedding ms、retrieval ms、LLM ms、top score、source ids、模型版本；指标写入 SSE `done.metrics` 和服务日志。
- [x] 启动时检测 manifest，不匹配时记录“需要重新入库”警告；`/api/health` 返回 `degraded` 和详细 mismatch 原因。
- [x] 增加 `backend/requirements.lock`，固定 Python 依赖版本；当前环境已验证 `sentence-transformers 3.4.1`、`torch 2.5.1+cpu`、`transformers 4.46.3` 和 `tokenizers 0.20.3`，`pip check` 无冲突。
- [x] 备份中复制 legacy 索引 manifest；启用版本化索引时同时复制 `index_versions/active.json`、各版本目录和 active manifest 摘要，并在 `manifest.json` 记录 embedding、chunking 版本和 source 数。
- [x] 增加只读 `backend/scripts/verify_backup.py`，恢复前校验备份 manifest、SQLite integrity、legacy index manifest 和 versioned index active pointer。
- [x] `scripts/local/Restore-TravelMate.ps1` 在用户确认前强制执行备份只读校验，损坏备份不会进入停止服务和替换数据流程。
- [x] 清理 `home.html` 静态 mock 对话，将预览改为真实的 `assistant.html` 启动入口，并增加契约测试。
- [x] 将 13 个页面完全重复的 `.topbar-left`/`.topbar-right` shell 对齐规则收敛到 `shared/theme.css`，并增加防重复契约检查。
- [x] 将完全一致的 `.icon-btn`、`.icon-btn:hover` 和 `.avatar` 基础规则收敛到 `shared/theme.css`；保留 community 页面有意不同的 icon button 基础覆盖。
- [x] 将 13 个页面完全一致的 `.brand` 容器规则收敛到 `shared/theme.css`，保留页面级 brand text/icon 差异。
- [ ] 继续收敛前端 14 个静态页面的其余定制样式和历史 design soft warnings；该项不阻塞 RAG 发布。

## 10. 推荐交付批次

### 批次 A：先恢复可信检索

- [ ] Phase 0（代码基线已完成，API key 轮换仍需用户在服务商控制台完成）
- [x] Phase 1 核心实现
- [ ] Phase 2（cache、版本化、回滚和 fallback 策略已完成，BGE 依赖安装与评测待完成）
- [x] 已重新生成全部索引并输出 fallback golden 评测报告

### 批次 B：提升召回和稳定性

- [x] Phase 3 核心实现
- [x] Windows fallback 缓存和 Chroma 显式 backend 验证入口
- [x] 完整 health/index manifest/分阶段日志闭环

### 批次 C：补齐产品链路

- [x] Phase 4 核心实现
- [x] 前端 E2E 回归和后端 SSE 断线/超时测试

### 批次 D：工程收尾

- [ ] Phase 5 测试与运维收尾（自动化回归已完成，备份恢复演练和视觉 warning 收敛待完成）
- [ ] 备份恢复演练、14 个静态页面的重复代码治理和视觉 warning 收敛

## 11. 回滚策略

- 每次更换 embedding 或 chunk 规则都生成新的索引版本，不覆盖旧索引。
- 通过环境变量切换当前 active index；新版本评测不达标时切回旧版本。
- 旧索引至少保留到新版本运行并完成一次备份恢复演练之后。
- 不直接删除现有 `chroma_data`、备份目录或失败目录；清理工作单独确认空间和恢复需求后执行。

## 12. 后续执行清单

### P0：凭证与发布前安全

- 由用户在 DeepSeek 控制台撤销旧 key 并生成新 key，只写入本机 `backend/.env`；检查 Git 跟踪文件、日志和备份中没有 key 内容。
- 不把 `backend/.env`、真实备份和本地索引提交到仓库或共享目录。

### P1：真实 BGE 评测

- [x] 在 Python 3.11 环境安装并验证 `sentence_transformers`、`torch`、`transformers`、`tokenizers`，依赖检查无冲突。
- [x] 执行 `backend/scripts/build_bge_index.ps1`，独立 BGE 版本达到 Recall@3 `1.00`、Recall@5 `1.00`。
- [x] 将 `.env` 切换到 `sentence_transformers` 和 `TRAVELMATE_INDEX_ROOT=index_versions`；`/api/health` 已确认模型、版本、维度和 manifest 均为 BGE。
- [x] 构建与激活流程保留旧 active pointer 和 legacy `backend/chroma_data`，不会用失败版本覆盖现有索引。

### P1：备份恢复演练

- 自动化恢复逻辑已覆盖 SQLite、legacy `chroma_data`、版本化 `index_versions` 和恢复前 safety snapshot；当前工作区已创建并校验 `backups/20260815-optimization-verification-v2`。
- 仍需在停止服务后进行一次人工恢复演练，在确认备份目录和当前项目路径后再执行恢复。
- 验证恢复前 safety snapshot、SQLite 行程数据、索引 manifest、source/chunk 数和 active index pointer 均可恢复。
- 演练完成后记录恢复耗时和人工步骤；恢复脚本与自动化测试均通过后，才允许清理旧索引版本。

### P2：前端低风险收尾

- 仅在 RAG 发布稳定后，按页面组逐步收敛 topbar、表单和状态样式；每组改动后运行 Vitest 和 Playwright。
- 不再继续大范围改动页面业务 JSX；该项只减少重复代码和 design soft warnings，不作为 RAG 发布阻塞项。

### 发布门禁

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..
npm test
npx playwright test
git diff --check
```

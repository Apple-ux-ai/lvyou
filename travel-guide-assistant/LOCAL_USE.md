# TravelMate 个人本地版使用说明

## 启动与停止

双击根目录的 `start-travelmate.cmd`。脚本会启动：

- 前端：`http://127.0.0.1:5501/pages/home.html`
- 后端 API：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`

健康检查通过后会自动打开首页。重复运行会复用已启动的服务。双击 `stop-travelmate.cmd` 可停止由该启动器创建的前后端进程。

从本机地址打开前端时，API 默认使用 `127.0.0.1:8000`，不会改走旧的托管演示 API。

启动日志位于 `.local/logs/`。启动失败时先查看 `backend.err.log` 或 `frontend.err.log`。

## DeepSeek 配置

真实密钥只保存在被 Git 忽略的 `backend/.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-flash
```

模型名以 [DeepSeek 官方模型列表](https://api-docs.deepseek.com/quick_start/pricing/) 为准。如果旧的 `backend/.env` 仍配置了 `deepseek-chat`，请改成 `deepseek-flash` 后重启后端。

不要提交或分享 `backend/.env`。没有 DeepSeek 密钥，或生成行程时 DeepSeek 请求失败，都可能得到本地模板结果。看到行程不代表已连通 DeepSeek；可查看 `.local/logs/backend.err.log` 排查。检索用的 embedding provider 仍单独配置。

当前离线开发环境应显式配置 Hash provider，避免把降级路径误当成语义模型：

```dotenv
TRAVELMATE_EMBEDDING_PROVIDER=hash
TRAVELMATE_EMBEDDING_ALLOW_FALLBACK=false
```

部署语义检索时改为 `sentence_transformers`，安装并验证 `BAAI/bge-small-zh-v1.5` 后运行：

```powershell
.\backend\scripts\build_bge_index.ps1
```

该脚本会在独立版本目录重建，先用新版本执行 Recall 门禁，只有通过后才激活 `active.json`，不会覆盖当前 Hash 版本。启用 BGE 后，将以下配置写入 `backend/.env`，并重启后端：

```dotenv
TRAVELMATE_EMBEDDING_PROVIDER=sentence_transformers
TRAVELMATE_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
TRAVELMATE_EMBEDDING_VERSION=bge-small-zh-v1.5
TRAVELMATE_EMBEDDING_DIMENSION=512
TRAVELMATE_EMBEDDING_ALLOW_FALLBACK=false
TRAVELMATE_INDEX_ROOT=index_versions
TRAVELMATE_INDEX_VERSION=
```

`TRAVELMATE_INDEX_VERSION` 留空时使用 `index_versions/active.json` 指向的版本；如果保留 Hash provider 或不配置 `TRAVELMATE_INDEX_ROOT`，后端仍会继续使用当前离线索引。

## 备份与恢复

双击 `backup-travelmate.cmd` 创建备份，默认位置为 `backups/<时间戳>/`。备份包含：

- `trips.db`：已保存的行程
- `chroma_data/`：本地 RAG 向量库
- `index_versions/`：启用版本化 embedding 时的 active pointer 和索引版本
- `manifest.json`：备份格式和内容说明

双击 `restore-latest-travelmate.cmd` 恢复最新有效备份。恢复脚本会先执行只读完整性校验，输入 `RESTORE` 确认后才停止 TravelMate，并将恢复前的数据保存到 `.local/pre-restore/`，然后替换当前数据。恢复完成后重新运行启动器。

人工恢复前可先执行只读校验，确认 SQLite、索引 manifest 和 active pointer 完整：

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\verify_backup.py --backup-path backups\<时间戳>
```

浏览器中的昵称、头像和界面偏好保存在浏览器 localStorage，不包含在文件备份中。清理浏览器站点数据前需注意这一点。

## 行程核验、编辑和打印

1. 打开行程规划器。可从助手的「编辑行程」进入，也可以先试用规划器内标有「示例」的关西路线。
2. 在「出发前检查」填出发日期、成人数和全团门票预算（日元）。逐天填写各站的当地到达时间，然后点击「检查行程」。
3. 当前只核验大阪城天守阁和金阁寺。可点官方链接核对休馆、入场时间及成人票；没匹配到的活动标成「待核实」，不当成免费。官方票价和其它行程估算分开计算，检查结果不代表实时营业或余票。
4. 可以只改当天的安排，改完重新检查。保存后，从个人中心打开，日期、时间、排序和交通备注仍在。「打印全部行程 / 存 PDF」可生成一份包含所有天的行程单，不会上传个人行程。

### 复核知识数据

结构化规则维护在 `backend/data/verified-places.json`，每条应保留官方来源及核验日期。规则快照超过 180 天未复核时，不用它来判断开放或计算门票，仍提供官网供用户确认。它不依赖模型或检索索引。攻略文字也同步纠正了旧票价和停用票种；已有本地索引需用原来的配置从 `backend/` 运行 `python scripts/ingest.py` 同步，版本化 BGE 仍按上文流程构建及激活。

### 开发检查

```text
npm ci
npm test
npx playwright install chromium
npm run test:e2e
# 后端：cd backend 后运行 python -m pytest -q
```

Playwright 使用本地模型和测试库；可设 `TRAVELMATE_TEST_BROWSER` 指定测试 Chromium、`TRAVELMATE_TEST_PYTHON` 指定 Python。浏览器测试使用锁定的本地前端依赖，常规页面运行仍会加载 CDN 脚本。

## 当前运行方式

本项目按单人本地使用维护：SQLite、Chroma 和 DeepSeek API 均在当前电脑上配合运行。正式账号、PostgreSQL、Qdrant、Docker 和服务器部署暂缓。

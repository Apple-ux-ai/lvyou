# TravelMate 个人本地版使用说明

## 启动与停止

双击根目录的 `start-travelmate.cmd`。脚本会启动：

- 前端：`http://127.0.0.1:5501/pages/home.html`
- 后端 API：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`

健康检查通过后会自动打开首页。重复运行会复用已启动的服务。双击 `stop-travelmate.cmd` 可停止由该启动器创建的前后端进程。

启动日志位于 `.local/logs/`。启动失败时先查看 `backend.err.log` 或 `frontend.err.log`。

## DeepSeek 配置

真实密钥只保存在被 Git 忽略的 `backend/.env`：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

不要提交或分享 `backend/.env`。没有 DeepSeek 密钥时，对话会使用本地 LLM fallback；embedding provider 仍按下方配置单独决定。

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

## 当前运行方式

本项目按单人本地使用维护：SQLite、Chroma 和 DeepSeek API 均在当前电脑上配合运行。正式账号、PostgreSQL、Qdrant、Docker 和服务器部署暂缓。

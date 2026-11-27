# TravelMate 旅游攻略助手

TravelMate 是一个面向个人使用、可在本机运行的智能旅行规划应用。它把旅行知识检索、AI 行程生成、行程编辑和本地保存连成完整流程，也提供目的地攻略、预算、签证、汇率、目的地比较和旅行社区等工具页面。

## 主要功能

- 基于旅行攻略与景点知识库检索内容，为回答提供来源依据。
- 使用 AI 生成结构化行程，支持逐天编辑、保存、重新打开和打印全部行程。
- 用带日期的官方资料检查部分关西景点的开放时段和成人门票预算；没有证据的项目标为待核实。
- 管理行程数据，并在本机保存 RAG 索引和应用数据。
- 浏览目的地与攻略，查询预算、签证和汇率等旅行信息。
- 提供本地一键启动、停止以及数据备份和恢复脚本。

## 技术栈

- 前端：React、JavaScript 和多页面 HTML
- 后端：Python、FastAPI 和 SSE
- 检索与存储：Chroma、SQLite，以及本地索引与降级方案
- 模型：可配置 DeepSeek 等兼容服务；本机环境也支持本地 fallback

## 项目位置与使用

应用源码位于 `travel-guide-assistant/`。本地启动、模型配置、索引切换和备份恢复说明见 [`LOCAL_USE.md`](travel-guide-assistant/LOCAL_USE.md)；可双击 [`start-travelmate.cmd`](travel-guide-assistant/start-travelmate.cmd) 启动。

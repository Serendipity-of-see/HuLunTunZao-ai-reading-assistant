# 囫囵吞枣

AI 辅助阅读器。导入 TXT 小说 → 用 DeepSeek 大模型自动生成三层情节档案（气泡流）→ 在阅读器中边读边查看章节结构。

![](https://img.shields.io/badge/version-0.2-orange)
![](https://img.shields.io/badge/license-MIT-green)

## 技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Tauri 2.x |
| 前端 | React 18 / TypeScript / Tailwind CSS 4 / Vite 6 |
| 后端 | Python 3.11+ / FastAPI / LangChain / SQLite |
| 大模型 | DeepSeek V4 Flash (情节分析) + DeepSeek V4 Pro (跨章整合) |

## 前置条件

- **Python 3.11+**（含 `pip`）
- **Node.js 18+**
- **Rust 1.77+**（仅桌面端打包需要）
- **DeepSeek API Key**：在 [DeepSeek Platform](https://platform.deepseek.com/) 申请

## 快速开始

```bash
# 1. 安装 Python 依赖
cd backend
pip install -r requirements.txt

# 2. 安装前端依赖
cd ../frontend
npm install

# 3. 启动开发模式（后端 + 前端）
npm run tauri-dev

# 4. 浏览器打开 http://localhost:5173
#    在底部「设置」页面填入 DeepSeek API Key
```

## 打包桌面应用

```bash
cd frontend
npx tauri build
# 安装包在 frontend/src-tauri/target/release/bundle/nsis/
```

## 项目结构

```
backend/            FastAPI 后端 (localhost:8765)
├── agents/         Parse Agent (分句) + Plot Agent (L4→L3→L2) + Merge Agent (L2→L1)
├── api/            REST 路由 (books, bubbles, reading, settings)
├── services/       业务逻辑 + 处理管线 (断点续处理)
├── db/             SQLite schema + 连接管理
└── models/         Pydantic 请求/响应模型

frontend/           React 前端
├── src/
│   ├── views/      书架 / 阅读器 / 档案 / 设置
│   ├── components/ BubbleCard, BubbleStream, ReaderView, DepthToggle 等
│   ├── api/        fetch 客户端
│   └── types/      TypeScript 类型
└── src-tauri/      Tauri 桌面壳 (Rust)
```

## 功能

- [x] TXT + EPUB 导入
- [x] AI 处理管线（Parse → L4语义分组 → L3场景聚合 → L2跨章事件 → L1宏观叙事）
- [x] SSE 实时进度追踪（步骤指示器 + 场景标题流）
- [x] 阅读器（章节/字号/主题/跳转定位）
- [x] 气泡流档案（L1-L3 展开搜索、L4 精简摘要）
- [x] 断点续处理
- [x] .hltz 导入导出
- [x] API Key + 端点 URL 配置
- [x] Tauri 桌面壳

## 路线图

- [ ] Character Agent + Relation Agent + 关系图
- [ ] BubbleMemoryManager（长书上下文压缩）
- [ ] 深色模式 / 书签
- [ ] 多 API 切换

详见 [docs/ROADMAP.md](../docs/ROADMAP.md)

## 数据存储

- SQLite 数据库：`~/.huluntunzao/hltz.db`
- 用户配置（API Key 等）：`~/.huluntunzao/config.json`

## License

MIT

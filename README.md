# 囫囵吞枣

AI 辅助阅读器。导入 TXT 小说 → 用 DeepSeek 大模型自动生成三层情节档案（气泡流）→ 在阅读器中边读边查看章节结构。

![](https://img.shields.io/badge/status-MVP-blue)
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

## MVP 功能

- [x] TXT 导入（多编码自动检测）
- [x] Parse Agent 规则引擎分章分句
- [x] Plot Agent DeepSeek Flash 自底向上 L4→L3→L2
- [x] Merge Agent DeepSeek Pro L2→L1 + 全书叙事概括
- [x] 阅读器（章节切换、滚动进度追踪、气泡跳转定位）
- [x] 气泡流档案（三档深度 L1/L2/L3、树形展开/收起）
- [x] 断点续处理（processing_state 每步 checkpoint）
- [x] Tauri 桌面壳一键启动后端
- [x] API Key 本地持久化（~/.huluntunzao/config.json）

## 待实现

- [ ] Character Agent + Relation Agent + 关系图视图
- [ ] EPUB 格式支持
- [ ] 故事时间排序（story_time sort）
- [ ] BubbleMemoryManager 上下文压缩（大书 >50 章需要）
- [ ] 深色模式 / 收纳面板

## 数据存储

- SQLite 数据库：`~/.huluntunzao/hltz.db`
- 用户配置（API Key 等）：`~/.huluntunzao/config.json`

## License

MIT

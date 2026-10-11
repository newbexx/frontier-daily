# 前沿简报

国内外科技资讯的本机阅读工具，使用原生 HTML、CSS、JavaScript 与 Python 标准库。以证据扎实程度组织阅读，支持筛选、收藏、阅读进度、AI 对话、笔记与分享卡片。

## 快速开始

需要 Python 3.10 或以上；运行 JavaScript 测试需要 Node.js。启动与计划任务脚本面向 Windows。

```powershell
python -X utf8 tools/init-demo.py
```

随后打开 `index.html` 或生成的 `前沿简报-国内外.html`。演示内容全部为虚构数据，演示链接指向 example.com，不包含个人新闻快照、学习记录或配置。页面的自动更新需要本机服务与有效 AI 配置。

双击 `启动简报.cmd` 可启动本机服务并打开页面；默认地址为 `http://127.0.0.1:8768/`。如果此端口已有其他项目运行，可改用手动 Python 启动其他端口，参阅 AI 接入指南。直接打开单文件可离线阅读和生成分享卡片；AI 提问与学习记录需要本机服务。

## 阅读与学习

界面使用冷灰纸底、浅色阅读面、宋体标题。顶部证据条可跳到新闻，条目显示「扎实」「初步」「说法」文字标签，旧记录无证据时显示「未标注」。主题、地区、日期与关键词可组合筛选，收藏保存于当前浏览器。

「问 AI」打开右侧抽屉，支持继续追问、复制、停止等待与从零解读；Enter 发送，Shift+Enter 换行。「我的学习」可筛选、搜索对话和笔记，回答可「收进笔记」。学习记录保存于本机 `data/notes/`，可以自行备份此目录。

选择 1–6 条新闻可生成分享卡片，支持两套画布风格、修改文字、排序、PNG 和 ZIP 导出。

## AI 与更新

AI 可以独立接入，无需安装 Codex。阅读提问与新闻编辑共用同一连接，支持 Chat Completions 和 Responses 两种兼容 API。首次接入请按 [AI 接入与首次运行](docs/AI接入.md) 完成以下步骤：

1. 将 `ai-settings.example.json` 复制为 `ai-settings.json`，填写服务商提供的 `endpoint`、准确的 `model` 和 `wireApi`。
2. 在 PowerShell 安全提示中输入自己的 Key，设置 `FRONTIER_API_KEY` 环境变量。密钥不写入项目文件。
3. 运行 `python -X utf8 tools/check-ai.py`，收到成功提示后，在同一终端启动服务并打开页面提问。

配置检查可用 `--config-only`，不会调用服务商；实际连接检查会发送一次小请求。页面「AI 配置已就绪」只表示配置可读取。服务商需要支持对应协议和请求参数；具体配置、故障排查及自动任务的环境变量设置见接入指南。

配置文件中的 `minScore`（0–5，默认 3）和 `limit`（正整数，默认 15）控制新闻编辑筛选。已有 Codex 配置可作为可选备用，独立项目配置优先。

新闻材料、问题与最近的相关对话会发送给所配置的 AI 服务。连接检查、阅读与 AI 编辑可能产生服务商费用。没有可用 AI 连接时，更新保留上一刊；已有页面可继续阅读。

```powershell
python -X utf8 tools/refresh.py --rebuild
```

上面的命令仅从现有数据重建页面，不采集、不调用 AI。双击 `立即更新.cmd` 才会联网采集并请求 AI 编辑。`安装自动更新.cmd` 是可选操作，会创建北京时间每日 08:00 的 Windows 计划任务，登录时补更；安装脚本要求系统时区为 UTC+08:00。

## 隐私与版本控制

本仓库仅包含源码、工具、测试和虚构演示数据。以下内容不应提交：

- `ai-settings.json`、API 密钥、账号凭据、环境文件和用户配置目录。
- `data/notes/`、实际新闻快照、历史与 AI 编辑缓存。
- 日志、浏览器状态、测试截图与导出文件、备份、个人交接和完成报告。
- 生成的根目录单文件 HTML，它可能内嵌实际数据。

`.gitignore` 默认排除全部运行数据，只允许 `data/demo.json`。不要使用 `git add -f` 提交这些排除项。仓库的 `demo/` 单文件预览由虚构数据生成。

## 验证

```powershell
python -X utf8 -m unittest discover -s tests -p "test_*.py"
node --test tests/test_app.cjs tests/test_reader.cjs tests/test_share.cjs
```

测试使用模拟接口和临时数据，不要求真实 AI 密钥。

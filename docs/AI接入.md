# AI 接入与首次运行

本工具可以独立运行，不需要安装 Codex，也不需要原作者的账号或配置。AI 阅读和新闻编辑共用同一连接。你需要自己的服务地址、模型 ID 和有效 API Key；包内没有密钥。

## 1. 准备并初始化

安装 Python 3.10 或以上，在安装程序中勾选加入 PATH。解压项目后，在含 README.md 的项目目录打开 PowerShell，确认：

```powershell
python --version
python -X utf8 tools/init-demo.py
```

运行只使用 Python 标准库，不需要 pip install；Node.js 仅供开发者运行 JavaScript 测试。Windows 支持启动脚本和计划任务，其他系统可以手动运行 Python 服务，不支持这些 Windows 脚本。

初始化会生成本地演示数据与单文件。如果已有 data/latest.json，命令会停止，避免覆盖现有刊物。已初始化的项目无需重复运行。直接打开 demo/前沿简报-演示.html 也可离线预览。

## 2. 填写服务地址和模型

```powershell
Copy-Item -LiteralPath ai-settings.example.json -Destination ai-settings.json
notepad ai-settings.json
```

已有 ai-settings.json 时直接编辑，避免覆盖个人配置。将示例中的占位值替换为服务商给你的实际信息，例如文件结构为：

```json
{
  "endpoint": "https://your-provider.example/v1",
  "model": "your-model-id",
  "wireApi": "chat",
  "apiKeyEnv": "FRONTIER_API_KEY",
  "minScore": 3,
  "limit": 15
}
```

这里的域名和模型名都是占位符，不能直接调用。

| 字段 | 如何填写 |
| --- | --- |
| endpoint | 服务商的 API 基础地址。服务商要求 /v1 时必须保留；通常不填写末尾的 /chat/completions 或 /responses。公网地址要求 HTTPS，HTTP 仅供本机测试。不要附带查询参数、密钥或账号密码。 |
| model | 服务商控制台给出的准确模型 ID，需要你的 Key 有调用权限。不能用网页产品名代替模型 ID。 |
| wireApi | Chat Completions 兼容接口填写 chat；Responses 兼容接口填写 responses。 |
| apiKeyEnv | 保存密钥的环境变量名，默认 FRONTIER_API_KEY。这里填变量名，不能填密钥本身。 |
| minScore / limit | 新闻编辑的最低分数（0–5）和条数上限（正整数），可保留示例值。 |

chat 模式向基础地址追加 /chat/completions，发送 messages、max_tokens；responses 模式追加 /responses，发送 input、max_output_tokens、store:false。均使用 Bearer 密钥与非流式请求。服务商和模型需要接受对应参数及返回格式；仅支持其他专用协议的服务不能直接接入。

## 3. 安全设置 API Key

在同一个 PowerShell 窗口粘贴以下命令，出现提示时输入 Key。输入隐藏，命令历史中不需要写密钥：

```powershell
$secureKey = Read-Host "API Key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:FRONTIER_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
Remove-Variable secureKey, keyPointer
```

这只设置当前窗口及随后启动的子进程，关闭窗口后不会为新的终端保留。不要将 Key 写入 JSON、源码、截图或上传文件。ai-settings.json 已被 Git 忽略，但网页上传需要你自行选择文件，不能依赖 Git 忽略规则过滤。

## 4. 检查后启动

```powershell
python -X utf8 tools/check-ai.py --config-only
python -X utf8 tools/check-ai.py
python -X utf8 tools/serve.py --port 8768
```

第一条只验证本地配置，不证明网络或额度可用。第二条向你配置的服务发送一次小请求，可能计费；出现「AI 连接测试成功」才表示已收到真实模型回复。第三条启动本机服务，保持终端运行，在浏览器打开 http://127.0.0.1:8768/，选择演示新闻点「问 AI」即可提问。Ctrl+C 停止服务。

也可在已设置密钥的同一窗口执行 `& '.\启动简报.cmd'`，让启动脚本继承环境变量。只在另一个窗口设置密钥后双击脚本，可能无法继承。已有服务需要先关闭再启动才能读取新环境变量；修改 ai-settings.json 则会在下一次调用时读取。

如果 8768 端口被其他项目占用，不要结束不明进程。手动使用 `python -X utf8 tools/serve.py --port 8770` 并访问对应端口即可；双击启动脚本固定使用 8768。

页面「AI 配置已就绪」只表示配置可读取。网络、模型权限和余额仍应通过连接检查或实际提问确认。

## 5. 采集与自动更新

连接成功后，可用页面的更新按钮或在同一终端执行：

```powershell
python -X utf8 tools/refresh.py
```

采集需要新闻来源可访问，编辑会调用同一 AI 连接并产生费用。连接检查通过不代表所有新闻来源可访问，也不代表一定能形成新刊；更新失败会保留上一刊。纯重建页面使用 `python -X utf8 tools/refresh.py --rebuild`，不联网、不请求 AI。

Windows 的「安装自动更新.cmd」会创建每天北京时间 08:00 的计划任务，并支持登录时补更，要求系统时区为 UTC+08:00。计划任务无法继承一次性终端密钥。如果需要自动任务，可以在设置密钥的终端中将其保存为当前 Windows 用户的环境变量：

```powershell
[Environment]::SetEnvironmentVariable('FRONTIER_API_KEY', $env:FRONTIER_API_KEY, 'User')
```

这会在本机用户环境中持久保存密钥，不会写入项目，但不是加密密钥库。重新登录 Windows 后再启动服务、安装并验证计划任务，确保新进程获取到变量。不需要持久保存时，用同样的命令将值改为 `$null`，重新登录并重启服务。不要把上述密钥变量内容输出给他人。

## 可选连接方式

也可不用 JSON，直接在同一终端设置 FRONTIER_API_BASE、FRONTIER_MODEL、FRONTIER_WIRE_API（chat 或 responses），并按上文设置 FRONTIER_API_KEY。三个连接字段的环境变量优先于项目文件；有项目配置时密钥变量名仍由 apiKeyEnv 决定。排查时注意旧环境变量可能覆盖文件中的值。

既有 Codex 用户可以保留原先的所选服务连接作为备用；显式项目或环境配置优先，错误配置会提示修正，不会自动切到其他服务。

页内手动 API 设置仅用于本次页面中的阅读对话，支持兼容 Chat Completions 的 HTTPS 公网 443 接口。Key 只保留在页面内存中，刷新后需重填。这种方式不会配置新闻编辑或计划任务；推荐使用上面的独立服务配置。

## 常见问题

| 现象 | 检查方法 |
| --- | --- |
| 找不到 python | 重新打开终端，确认 Python 已加入 PATH；也可试用 py -3，后续命令用同一解释器。 |
| 提示未设置 FRONTIER_API_KEY | 在启动服务的同一终端重新设置；若 apiKeyEnv 改名，设置对应变量。 |
| 401 / 403 | 确认 Key 有效、属于该服务，并有模型权限。不要把完整 Key 发给别人。 |
| 404 | 核对基础地址、是否需要 /v1、协议和模型 ID，避免重复接口路径。 |
| 400 | 确认协议和参数受支持；某些模型不接受 max_tokens 或 store 等字段，需要选择兼容模型或调整适配代码。 |
| 429 | 检查余额、额度与频率限制，稍后重试。 |
| 超时或网络失败 | 检查地址、网络、代理；Python 使用系统/环境代理设置。 |
| 检查成功但页面仍不可用 | 确认访问的是当前项目的本机服务、旧进程已重启，并在当前浏览器地址提问。 |
| 新刊更新失败 | 检查新闻来源网络和 AI 编辑结果；现有刊物仍可阅读，参阅本机日志。 |

本机服务仅监听回环地址，适合个人桌面使用。运行数据、笔记、日志、密钥和个人配置均不应加入 GitHub 上传包。

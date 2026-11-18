# 本地桌面助手

在 Windows 上通过自然语言完成文件整理、打开应用、更换壁纸和切换外观。程序、任务记录和配置都留在本机。云端模型默认关闭，文件内容和截屏不会自动外传。

## 能做什么

- 用中文或英文描述结果，例如“找到 invoice_2025.pdf 并打开”。
- 在下载、文档、桌面和图片目录中搜索、复制、重命名、移动和按扩展名整理文件。
- 删除前展示完整路径，确认后只移入回收站。回收站失败时不会改成永久删除。
- 用系统接口更换壁纸、切换浅色/深色外观，以及打开允许列表中的设置页。
- 打开记事本、计算器、画图和资源管理器。会议纪要和支出表会直接写成文件，不模拟一长串鼠标点击。
- 操控桌面时，本机视觉模型看屏幕后连续点击、输入和滚动，不再逐步确认。停止按钮可以中断。不会输入密码。
- 在需要时读取辅助功能树；只有你明确开启视觉模型后才会分析截屏。
- 可选连接你自己启用的 MCP 工具。外部工具默认按高风险处理，不能绕过确认。

每次高风险操作都只对当前预览生效。界面上有停止按钮，也可以设置任务超时。

## 安装

需要 Windows 10/11 和 Python 3.12 或更新版本。本机验证使用的是 Python 3.13。

```powershell
cd local-ai-desktop-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

可选的网页标题读取需要另装浏览器自动化，并且不会用于绕过登录或验证码：

```powershell
pip install -e ".[browser]"
playwright install chromium
```

## 运行

```powershell
.\.venv\Scripts\python.exe -m app.main
```

本地模型使用 Ollama，默认地址是 `http://127.0.0.1:11434`，默认模型是 `qwen2.5:7b`。没有模型时，上面这些明确的文件和外观指令仍可由内置规则完成。

在设置里可以改超时、切换到兼容 OpenAI 接口的云端服务，并单独决定是否允许发送路径、文件内容或截屏。API 密钥写入 Windows 凭据管理器，不写入 SQLite。

## 测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

自动化测试使用临时目录和假的系统接口，不会修改真实桌面、壁纸或回收站。

## 安全边界

程序没有提权、没有通用 shell，也不会执行模型临时写出的脚本。搜索范围默认不是整块硬盘。`C:\Windows`、Program Files 和 ProgramData 不能被这些工具修改。密码、密钥和令牌请求会被拒绝。

更细的结构说明见 [docs/architecture.md](docs/architecture.md)。

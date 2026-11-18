# Local Desktop Assistant

A Windows assistant that finishes file, application, wallpaper, and appearance tasks from plain English. The program, task history, and settings stay on this computer. Cloud models are off by default, and file contents and screenshots are not sent out automatically.

## What it can do

- Describe the result you want, for example “Find invoice_2025.pdf and open it.”
- Search, copy, rename, move, and organize files by extension in Downloads, Documents, Desktop, and Pictures.
- Show the full path before a deletion, then move the file to the Recycle Bin only after you confirm. If the Recycle Bin fails, the file is not permanently deleted.
- Change the wallpaper, switch light or dark appearance, and open an allow-listed Settings page through system interfaces.
- Open Notepad, Calculator, Paint, and File Explorer. Meeting notes and expense sheets are written as files directly, not by simulating a long series of mouse clicks.
- For desktop control, a local vision model looks at the screen and then clicks, types, and scrolls without asking before every step. The Stop button interrupts the task. Passwords are never typed.
- Read the accessibility tree when needed. Screenshots are analyzed only after you explicitly enable a vision model.
- Optionally connect MCP tools that you enable. External tools are treated as high risk and cannot skip confirmation.

Each high-risk action applies only to the current preview. The window has a Stop button, and you can set a task timeout.

## Install

Windows 10 or 11 and Python 3.12 or newer are required. This project was verified with Python 3.13.

```powershell
cd local-ai-desktop-agent
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Optional page-title reading needs a separate browser automation install. It is not used to bypass sign-in or CAPTCHA:

```powershell
pip install -e ".[browser]"
playwright install chromium
```

## Run

```powershell
.\.venv\Scripts\python.exe -m app.main
```

The local model is Ollama at `http://127.0.0.1:11434`, using `qwen2.5:7b` by default. Without a model, the specific file and appearance commands above still run through built-in rules.

Settings can change timeouts, switch to an OpenAI-compatible cloud service, and choose separately whether paths, file contents, or screenshots may be sent. API keys are stored in Windows Credential Manager, not in SQLite.

## Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

Automated tests use a temporary directory and a fake system interface. They do not change the real desktop, wallpaper, or Recycle Bin.

## Safety limits

The program does not elevate privileges, does not provide a general shell, and does not run scripts written by the model. Search is not the whole drive by default. `C:\Windows`, Program Files, and ProgramData cannot be modified by these tools. Requests for passwords, secrets, and tokens are refused.

See [docs/architecture.md](docs/architecture.md) for the structure.

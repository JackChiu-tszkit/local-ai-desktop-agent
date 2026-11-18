# Architecture

The assistant works in a loop: understand, plan, act, observe, and verify. LangGraph keeps one task inside plan, single-step execution, verification, and finish. Step count, retries, step timeout, and task timeout all have limits. The same tool and arguments stop after repeated failure instead of calling forever.

## Layers

- `app/ui` is the PySide6 desktop window. Tasks run on a background thread. Confirmation dialogs stay on the interface thread.
- `app/agent` plans and runs the LangGraph loop. A risk level suggested by the model is ignored and classified again by the program.
- `app/tools` holds typed tools. There is no shell, permanent delete, or arbitrary program launch.
- `app/security` checks paths, assigns risk, and records one-time confirmation.
- `app/platform` calls the Windows API. Tests replace it with a fake platform object.
- `app/storage` stores tasks, step checkpoints, and the audit log in SQLite. Secrets use the operating-system credential store.
- `app/mcp` starts only servers enabled in the user's settings, and still asks before a call.

## Tool priority

File search, moves, wallpaper, and appearance prefer the filesystem or a documented system interface. Ordinary files open through the system file association. Mouse, keyboard, and screenshots are secondary: coordinates are checked against the virtual screen, and keyboard input checks the foreground window first.

## Verification

After a move or rename, the source path must be gone and the destination must exist with the same size. Recycle Bin operations only check that the source path is gone. On failure the original file stays. Wallpaper and appearance are read back from the system. If a window cannot be confirmed, the step is a warning and is not treated as visually verified.

## Privacy

The default model is local Ollama. A cloud provider must be turned on in Settings. Even then, screenshots, file contents, and file paths each stay off unless enabled separately. Web page text and file text do not enter the next plan. The planner sees path counts, status, and a short message.

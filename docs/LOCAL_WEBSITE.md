# Running the website on your own computer

`tools/run_local_web.py` starts the website on http://127.0.0.1:8000/ with a local PostgreSQL 17
test cluster. It is for one person on one computer only. Never put it on the internet.

Run it from the project folder:

| Command | What it does |
|---|---|
| `python tools/run_local_web.py setup` | Once: creates local-only database roles, a database and private secrets |
| `python tools/run_local_web.py ai` | Add, change or remove a Gemini or Grok API key and model (typed hidden) |
| `python tools/run_local_web.py check` | Tests each saved key and model and times one tiny answer ("fast" means 15 seconds or less) |
| `python tools/run_local_web.py speed` | Times one tiny answer from each Gemini Flash text model your key can use, fastest first. Changes nothing |
| `python tools/run_local_web.py` | Every time: applies database updates, then starts the website |

## Where secrets live

Database passwords and AI keys are kept in `local-web-secrets.json` **outside the project**:

- On Windows: `%LOCALAPPDATA%\UCC`.
- Elsewhere: `~/.local/share/ucc`.
- Or any folder named in `UCC_LOCAL_HOME`.

The launcher refuses to keep them inside the project folder, `.gitignore` ignores the file
name, and `tools/check_repository_safety.py` fails if that file is ever tracked. Keys are
never printed. Never paste a key into a chat, an issue or a commit.

## Choosing a fast model

Speed depends mostly on the model. In November 2026 `gemini-3.6-flash` took 18–30 seconds even
for a one-word reply, and `gemini-3.5-flash-lite` took 1.6 seconds with the same key and
connection. Run `speed` to compare your models, then `ai` to save the one you want. Press
Enter at the key question to keep your saved key.

## AI speed setting

Gemini 3 models answer with a low "thinking" level by default (see
`docs/AI_STUDY_ASSISTANT.md`, "Speed"). If Google ever refuses that setting for your model,
`check` says so. Then, before starting the website, run this in the same PowerShell window:
`$env:UCC_GEMINI_THINKING="default"`.

## Adding Grok as a backup

1. Create an API key on the xAI console (https://console.x.ai). It may need billing or credits.
2. Run `python tools/run_local_web.py ai`, type `grok`, then `save`. Type the model name and
   paste the key; the key is not shown on screen.
3. Run `python tools/run_local_web.py check`. It lists the models your key can use and times
   a tiny answer.
4. Start the website. The confirm page then shows **Send** and **Send with the backup service**.

The older copy of the launcher in `%LOCALAPPDATA%\UCC\run_local_web.py` (from the
`launcher-download` branch) still works, but this one in the project is the one kept up to
date.

# Mega Zword (Dev Edition) — Brennan's Branch

> **Hey Brennan —**
> I built this tool to solve a real headache with modern AI coding: rate limits, vendor lock-in, and juggling five different subscriptions and browser tabs.
> 
> *Mega Zword* is a universal AI command center for your terminal. It routes prompts across Claude, Codex, Gemini, Grok, OpenRouter, and local Ollama models. It tracks token usage, picks the fastest/cheapest model for the job, and lets multiple models review your code in parallel.
> 
> This branch (`brennans-branch`) is stripped of all the extra internal noise so you can plug in your keys, fork it, break things, and make it your own.
> 
> *— Dad*

---

## ⚡ What It Does

- **Universal Terminal Chat:** Jump straight into interactive chat with any model from your command line (`megazword chat`).
- **Parallel Multi-AI Code Review:** Run `git diff` and let three different AI models review your changes side-by-side before you commit (`megazword review`).
- **Smart Prompt Routing:** Run `megazword run "explain this bug"` and let the engine automatically choose the right model based on task difficulty.
- **Native Desktop App & Dashboard:** Run it as a standalone Windows desktop app window with its own taskbar icon (`megazword` or double-click the desktop shortcut), complete with live meters and run boxes.
- **Free-First Architecture:** Automatically prioritizes free developer tiers (Google AI Studio, Groq, Ollama) before touching paid API credits.

---

## 🚀 3-Minute Quickstart

### On Windows (Recommended)
Open PowerShell and run:
```powershell
# Clone Brennan's branch
git clone -b brennans-branch https://github.com/edotwedo/mega-zword.git
cd mega-zword

# Run the installer with desktop app shortcut
.\scripts\install.ps1 -Shortcut
```
> **Tip:** The `-Shortcut` flag drops a **Mega Zword** app icon right on your Windows Desktop and Start Menu. Double-clicking it opens the native desktop app window!

---

### On Linux / macOS
```bash
git clone -b brennans-branch https://github.com/edotwedo/mega-zword.git
cd mega-zword

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Check Your Setup
Run diagnostics to see what models and tools are detected:
```bash
megazword doctor
```

### Configure Your Keys (Optional)
Copy the example environment template and add whatever keys you want to use:
```bash
cp .env.example .env
```
*(If you run **Ollama** locally, Mega Zword detects it automatically with zero configuration).*

---

## 🛠️ Daily Driver Cheatsheet

| Command | What It Does |
| :--- | :--- |
| `megazword chat` | Opens an interactive terminal chat with your default model. |
| `megazword run "Explain this regex"` | One-shot prompt; engine auto-selects the best model. |
| `megazword run -m claude "Refactor this"` | Forces execution with a specific model (e.g. `claude`, `codex`, `gemini`). |
| `megazword review` | Compares staged git changes and gets a multi-model code review. |
| `megazword dashboard` | Launches a local web GUI at `http://localhost:8000` with live meters and logs. |
| `megazword usage` | Shows live remaining token quotas across your connected providers. |
| `megazword map` | Generates a compact AST/symbol map of the current git repository. |

---

## 💡 How the Router Works

Under the hood in `src/megazword/`:
1. **Difficulty Classifier:** Evaluates your prompt's length, code blocks, and complexity (Easy, Medium, Hard).
2. **Fallback Ladder:** If your primary model is down, rate-limited, or out of tokens, Mega Zword immediately tries the next best candidate instead of crashing your workflow.
3. **Pacing & Quota Guard:** Prevents burning through your 5-hour or weekly API limits by smoothly throttling background calls.

---

## 🧪 Hacking & Extending

Feel free to customize your routing preferences in `config.toml`:
- Change your favorite models for easy vs. hard tasks in `[route]`.
- Add custom CLI aliases or local model endpoints.
- Tweak the prompt templates in `src/megazword/review.py` and `src/megazword/router.py`.

Have fun with it! If you find bugs or want to add a feature, push a commit to your branch.

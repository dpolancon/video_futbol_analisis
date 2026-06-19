# Together.ai Model Access — Handoff Guide

> **Audience**: Any repository or collaborator that needs to call the LLMs used in this project via the Together.ai API.
> **Origin repos**: `COMPOL_DigitalCapitalism` (primary research project) · `academic-research-skills` (ARS pipeline).

---

## 1 · What is Together.ai in this stack?

This project routes all LLM calls through [Together.ai](https://www.together.ai/), a third-party inference platform that hosts open-weight models (Qwen, Llama, Mistral, etc.) behind an **OpenAI-compatible REST API**.

The key insight is: **you use the standard `openai` Python library, but point it at Together.ai's base URL instead.**

```python
from openai import OpenAI

client = OpenAI(
    api_key="<your-TOGETHER_API_KEY>",
    base_url="https://api.together.ai/v1",  # ← only difference from plain OpenAI
)
```

No custom SDK is required. Any code already using `client.chat.completions.create(...)` works without modification — just swap `api_key` and `base_url`.

---

## 2 · Getting a Together.ai API Key

1. Go to **<https://api.together.ai>** and sign in / register.
2. Navigate to **Settings → API Keys**.
3. Click **Create new API key** and copy the token (format: `tgp_v1_…`).
4. Keep it secret — **never commit it to version control**.

---

## 3 · Setting Up the Key in a New Repo

### Option A — Environment variable (recommended for production & CI)

**Linux / macOS**:
```bash
export TOGETHER_API_KEY="tgp_v1_YOUR_KEY_HERE"
```

**Windows (PowerShell — session only)**:
```powershell
$env:TOGETHER_API_KEY = "tgp_v1_YOUR_KEY_HERE"
```

**Windows (persistent)**:
```powershell
[System.Environment]::SetEnvironmentVariable("TOGETHER_API_KEY", "tgp_v1_YOUR_KEY_HERE", "User")
```

---

### Option B — `.env` file (recommended for local development)

Create a `.env` file at the root of the new repo:

```dotenv
# .env  —  DO NOT COMMIT THIS FILE
TOGETHER_API_KEY=tgp_v1_YOUR_KEY_HERE
TOGETHER_BASE_URL=https://api.together.ai/v1
```

Load it in Python before making any API call:

```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("TOGETHER_API_KEY")
```

> **Important**: Add `.env` to your `.gitignore`:
> ```gitignore
> .env
> ```

---

### Option C — Gitignored plain-text fallback (ARS pipeline pattern)

The `academic-research-skills` pipeline checks for a plain-text file at:
```
docs/together_AI_baseURL_APIKEY.txt
```

Format:
```text
TOGETHER_API_KEY=tgp_v1_YOUR_KEY_HERE
TOGETHER_BASE_URL=https://api.together.ai/v1
```

This file is listed in `.gitignore` and is read only if `TOGETHER_API_KEY` is absent from the environment. **Do not rely on this in CI/CD** — use environment variables there.

---

## 4 · Python Installation

Install the required packages once in the target repo's virtual environment:

```bash
pip install openai python-dotenv
```

If the repo also uses Google Gemini (ARS dual-provider pattern):
```bash
pip install openai google-generativeai watchdog pyyaml python-dotenv
```

---

## 5 · Minimal Code Pattern

This is the exact pattern used in `src/utils/qwen_cli.py` in this repo:

```python
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("TOGETHER_API_KEY"),
    base_url="https://api.together.ai/v1",
)

response = client.chat.completions.create(
    model="Qwen/Qwen2.5-72B-Instruct",   # see §6 for available models
    messages=[
        {"role": "system", "content": "You are an academic research assistant."},
        {"role": "user",   "content": "Summarize the concept of digital capitalism."},
    ],
    temperature=0.2,
    max_tokens=4000,
)

print(response.choices[0].message.content)
```

---

## 6 · Models Used in This Project

| Model ID (Together.ai slug) | Use case | Size |
|---|---|---|
| `Qwen/Qwen2.5-72B-Instruct` | Primary research assistant (`COMPOL_DigitalCapitalism`) | 72B |
| `Qwen/Qwen3.5-9B` | Default model in ARS pipeline (`agent_config.yaml`) | 9B |

### Discovering other available models

Browse the full Together.ai model catalogue at:
```
https://api.together.ai/models
```

Or list them programmatically:
```python
models = client.models.list()
for m in models.data:
    print(m.id)
```

---

## 7 · `agent_config.yaml` Pattern (ARS Pipeline)

The `academic-research-skills` repo centralises all provider configuration in `agent_config.yaml` at the repository root:

```yaml
global_settings:
  default_provider: "together"
  default_model: "Qwen/Qwen3.5-9B"

providers:
  together:
    api_key_env: "TOGETHER_API_KEY"       # name of the env var to read
    base_url: "https://api.together.ai/v1"
  gemini:
    api_key_env: "GEMINI_API_KEY"
```

Copy and adapt this file to any new repo that uses the `LLMGateway` class.

**Priority resolution order** (highest → lowest):
1. CLI flags (`--model`, `--provider`, `--base-url`)
2. Environment variables (`DEFAULT_MODEL`, `DEFAULT_PROVIDER`)
3. `agent_config.yaml`
4. Hardcoded fallbacks (`together` / `Qwen/Qwen3.5-9B` / `https://api.together.ai/v1`)

---

## 8 · Using the Shared `LLMGateway` Class

The `academic-research-skills` repo ships a reusable gateway in `scripts/llm_gateway.py`. To use it from another repo:

```python
import sys
sys.path.insert(0, "/path/to/academic-research-skills/scripts")

from llm_gateway import LLMGateway

gateway = LLMGateway()   # reads agent_config.yaml + TOGETHER_API_KEY from env

result = gateway.generate(
    agent_name="my_agent",
    system_prompt="You are a research assistant.",
    user_prompt="What is surveillance capitalism?",
    override_model="Qwen/Qwen2.5-72B-Instruct",   # optional
    override_provider="together",                  # optional
)

print(result["content"])
```

The gateway also supports **tool/function calling** for both Together AI and Gemini. Refer to `scripts/llm_gateway.py` for the full interface.

---

## 9 · Security Checklist

Before committing anything to a new repo:

- [ ] `.env` is in `.gitignore`
- [ ] `docs/together_AI_baseURL_APIKEY.txt` is in `.gitignore`
- [ ] No API key appears as a literal string in any `.py`, `.r`, `.md`, or `.yaml` file
- [ ] CI/CD uses repository secrets (GitHub → Settings → Secrets and variables → Actions)
- [ ] Rotate the key immediately if it was ever accidentally committed

---

## 10 · Quick Start Checklist (TL;DR)

```
[ ] 1. Get API key from https://api.together.ai → Settings → API Keys
[ ] 2. pip install openai python-dotenv
[ ] 3. Create .env with: TOGETHER_API_KEY=tgp_v1_...
[ ] 4. Add .env to .gitignore
[ ] 5. Copy the minimal code pattern from §5 into your script
[ ] 6. Choose a model slug from §6 (default: Qwen/Qwen2.5-72B-Instruct)
[ ] 7. Run and verify output
```

---

## 11 · Related Files in This Project

| File | Location | Purpose |
|---|---|---|
| `src/utils/qwen_cli.py` | `COMPOL_DigitalCapitalism` | Standalone CLI to query Qwen via Together.ai |
| `requirements.txt` | `COMPOL_DigitalCapitalism` | Python dependencies for this repo |
| `scripts/llm_gateway.py` | `academic-research-skills` | Shared multi-provider gateway (Together + Gemini) |
| `agent_config.yaml` | `academic-research-skills` | Centralised provider/model configuration |
| `README.md` | `academic-research-skills` | Full ARS pipeline documentation |

---

*Last updated: 2026-06-18 · COMPOL Digital Capitalism project*

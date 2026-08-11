# Adding a New AI Model to Lydia

## Overview
This guide covers how to add a **new AI model provider** (like Kimi/Moonshot, OpenAI, Anthropic, Google Gemini, etc.) to Lydia's backend so you can switch to it with the `set_model` command.

Lydia's architecture is **multi-provider** — she already supports Groq (primary) and DeepSeek (fallback/reasoner). Adding a new provider involves: getting an API key, wiring the OpenAI-compatible client in `config.py`, and adding the model to `BRAIN_MODELS` and `BRAIN_CHAIN`.

---

## Step 1: Get an API Key from the Provider

### Kimi / Moonshot (月之暗面)
- Go to **[platform.moonshot.cn](https://platform.moonshot.cn)** and log in with your phone
- Navigate to **API Key Management** and create a new key
- Copy the key (starts with `sk-`)

### Other Providers
- **OpenAI**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Anthropic Claude**: [console.anthropic.com](https://console.anthropic.com)
- **Google Gemini**: [aistudio.google.com](https://aistudio.google.com) — get an AIza... key
- **Groq** (already wired): [console.groq.com/keys](https://console.groq.com/keys)
- **DeepSeek** (already wired): [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

---

## Step 2: Add the API Key to the .env File

Navigate to `C:\Users\book\Desktop\Lydia\.env` and add:

```env
KIMI_API_KEY=sk-your-key-here
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

The `.env` file is read by `config.py` via `python-dotenv` — keys go here, **never** in the code.

---

## Step 3: Wire the New Provider in `config.py`

Open `C:\Users\book\Desktop\Lydia\lydia\config.py`.

### 3a. Add environment variable reads (around line 12-20, near the other API keys)

```python
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
```

### 3b. Add the model to `BRAIN_MODELS` (around line 70-80)

This is the dictionary that maps friendly names like `"fast"`, `"smart"`, `"deepseek"` to actual model IDs. Add a new entry:

```python
BRAIN_MODELS = {
    "fast":     ("groq", "openai/gpt-oss-20b"),
    "smart":    ("groq", "openai/gpt-oss-120b"),
    "deepseek": ("deepseek", "deepseek-chat"),
    "kimi":     ("kimi", "kimi-k2.6"),               # <-- ADD THIS LINE
}
```

> **Note:** Kimi's model is `kimi-k2.6` as of July 2025. If they release newer versions, replace it accordingly.

### 3c. Add the model to `BRAIN_MODELS` → modeling aliases (around line 85-95)

So you can say "switch to kimi" or "use Kimi" by voice:

```python
MODEL_ALIASES = {
    # ... existing aliases ...
    "kimi": "kimi", "kimi": "kimi", "moonshot": "kimi", "moon": "kimi",
}
```

---

## Step 4: Wire the OpenAI Client in `brain.py`

Open `C:\Users\book\Desktop\Lydia\lydia\brain.py`.

### 4a. Add the new client in `Brain.__init__` (around where the chain is built, lines ~120-170)

Find where the chain of providers is built — you'll see something like:

```python
self.chain = []
if config.GROQ_API_KEY:
    groq_client = openai.OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL)
    self.chain.append({"client": groq_client, "model": config.BRAIN_MODEL, "label": "groq"})
if config.DEEPSEEK_API_KEY:
    ds_client = openai.OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_BASE_URL)
    self.chain.append({"client": ds_client, "model": config.DEEPSEEK_CHAT, "label": "deepseek"})
```

Add after the DeepSeek block:

```python
if config.KIMI_API_KEY:
    kimi_client = openai.OpenAI(api_key=config.KIMI_API_KEY, base_url=config.KIMI_BASE_URL)
    self.chain.append({"client": kimi_client, "model": "kimi-k2.6", "label": "kimi"})
```

### 4b. Add the model to `self.models`

In the same `__init__`, find where `self.models` is populated (maps friendly keys to chain nodes):

```python
self.models = {}
for key, (prov, mod) in config.BRAIN_MODELS.items():
    node = next((n for n in self.chain
                 if n["model"] == mod and n["label"].split(":")[0] == prov), None)
    if node:
        self.models[key] = node
```

If you added `("kimi", "moonshot-v1-8k")` to `BRAIN_MODELS` in step 3b, and the chain node's label is `"kimi"` with model `"moonshot-v1-8k"`, it should match automatically.

---

## Step 5: Restart Lydia

1. **Stop Lydia** — press Ctrl+C in the terminal, or run `stop.bat` in `C:\Users\book\Desktop\Lydia`
2. **Restart** — run `run.bat`
3. **Check the logs** — Lydia should print something like:
   ```
   Brain chain: groq:openai/gpt-oss-20b, deepseek:deepseek-chat, kimi:moonshot-v1-8k
   ```

---

## Step 6: Switch to the New Model

Once running, just say or type:

> **"switch to Kimi"**

Or use the `set_model` tool:

```
set_model kimi
```

Lydia will confirm and use the new model for all subsequent conversation and tool calls.

---

## Optional: Make Kimi the Primary Model

If you want Kimi to be the default brain instead of just a switchable option:

1. In `.env`, set:
   ```env
   BRAIN_PROVIDER=kimi
   BRAIN_MODEL=moonshot-v1-8k
   BRAIN_MODE_DEFAULT=kimi
   ```
2. Put Kimi first in `BRAIN_CHAIN` in `config.py`:
   ```python
   BRAIN_FALLBACKS = os.getenv(
       "BRAIN_FALLBACKS",
       "groq:openai/gpt-oss-20b,deepseek:deepseek-chat",
   )
   ```
   (Kimi would need to be the first entry in the chain built in `brain.py`.)

---

## Files Summary

| File | What to Edit |
|------|-------------|
| `.env` | Add `KIMI_API_KEY`, `KIMI_BASE_URL` |
| `lydia/config.py` | Add env var reads, add to `BRAIN_MODELS`, add to `MODEL_ALIASES` |
| `lydia/brain.py` | Add OpenAI client to chain, match model to models dict |

---

## Troubleshooting

- **"I don't know model 'kimi'"** — the model key wasn't found in `BRAIN_MODELS` in config.py (step 3b)
- **"The kimi model isn't available right now"** — the chain node didn't match (step 4b), probably the label or model name didn't align
- **Rate limiting** — add a fallback: `BRAIN_FALLBACKS` will auto-retry on Groq/DeepSeek if Kimi hits rate limits
- **API not compatible** — Lydia uses the OpenAI Python SDK (`openai.OpenAI`). The provider MUST support an OpenAI-compatible API format. Kimi/Moonshot does. Some older or custom APIs don't — check the provider's docs for an OpenAI-compatible endpoint

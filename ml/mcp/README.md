# ATLAS MCP Agent

Self-contained autonomous browser agent. It launches a Playwright MCP server
(Node), feeds the browser tools to an LLM, and runs an agentic loop that
navigates, clicks, and types to complete a natural-language task.

## Prerequisites

1. Python 3.10+ and the core Python dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Node.js and npx. The agent runs `npx @playwright/mcp@latest` to start the
   browser MCP server. Install Node.js from https://nodejs.org and confirm:
   ```
   npx --version
   ```
   The `@playwright/mcp` package is fetched by npx at runtime and is pinned to
   `@latest`. To pin a specific version, edit the `@playwright/mcp@latest`
   string in `browser_agent.py` and `test_connection.py`.
3. Google Chrome. Required only when `CHROME_PROFILE=true` (the default), which
   drives your real Chrome via the Chrome DevTools Protocol so logged-in
   sessions are available. Set `CHROME_PROFILE=false` to use a clean Playwright
   Chromium instead.
4. Optional local model backend (only for `LLM_BACKEND=llama`):
   ```
   pip install -r requirements-llama.txt
   ```
   This is a heavyweight source build and is not needed for the gemini or
   openai backends.

## Configure

Copy the example env file and fill in your values:

```
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```

The default backend is `openai` (works with OpenAI and any OpenAI-compatible
endpoint such as OpenRouter). Set `OPENAI_API_KEY` (and, for OpenRouter,
`OPENAI_BASE_URL` and `OPENAI_MODEL`). See `.env.example` for gemini and llama
alternatives, Chrome profile options, and `CDP_PORT`.

If you start the agent without a configured API key, it exits with a message
naming the exact environment variable to set and pointing at `.env.example`.

## Smoke test (no API key needed)

Verify that Node, npx, and the Playwright MCP server work and that browser
tools are discoverable:

```
python test_connection.py
```

## Run

Run these from inside `ml/mcp/`:

```
python run.py "Go to google.com and search for ATLAS AI"   # single task
python run.py                                              # interactive REPL
python run.py --help                                       # usage, no API key needed
```

`run.py` is the recommended entry point. Do not use `python -m mcp`: this
folder is named `mcp` and collides with the installed `mcp` Python SDK that the
code imports, so the `-m mcp` form fails to resolve `from mcp import
ClientSession`. Running `python run.py` (or `python __main__.py`) from inside
this folder avoids the collision.

## Files

- `run.py` - recommended runner (collision-free entry point).
- `__main__.py` - direct entry point (`python __main__.py "task"`).
- `cli.py` - shared CLI logic used by both entry points.
- `browser_agent.py` - MCP connection, Chrome/CDP launch, and the agent loop.
- `llm_backend.py` - gemini, openai, and llama backends.
- `config.py` - settings loaded from environment / `.env`.
- `test_connection.py` - no-API-key smoke test.
- `.env.example` - template for your `.env`.
- `requirements.txt` - core deps; `requirements-llama.txt` - optional llama backend.

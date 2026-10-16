# Argon Antigravity Proxy & Sub-Agent Bridge (`gemini-4-argon`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Google GenAI SDK](https://img.shields.io/badge/google--genai-2.18+-green.svg)](https://github.com/googleapis/python-genai)

A lightweight, multi-mode proxy and bridge to use **Gemini 4 Argon** (`gemini-4-argon`) inside **Google Antigravity** (IDE, Web, CLI, or Sub-Agent workflows) using your Google AI Studio API Key and the **$10 USD/mo GenAI credit** from the Google Developer Program / Google AI Pro.

---

## 💡 Why this exists

The native model selector in **Antigravity IDE** often restricts reasoning workloads or quickly consumes session quotas. Meanwhile, developers with a Google AI Pro subscription or Google Developer Program membership receive **$10 USD/month of GenAI credits** in Google AI Studio / Google Cloud.

This project bridges that gap by providing:
1. **Model Context Protocol (MCP) Server**: Exposes native `ask_argon` and `argon_telemetry` tools directly inside your Antigravity chat.
2. **Local HTTP Proxy (FastAPI)**: Exposes an OpenAI-compatible endpoint (`POST /v1/chat/completions`) and a native direct endpoint (`POST /api/argon`).
3. **CLI & Sub-Agent Tool**: Direct terminal interface with automatic token accounting and **Google Implicit Caching** (giving a **95% discount** on input tokens when inspecting whole repositories).

---

## ⚡ Key Features

* **3-in-1 Architecture**: Runs as an MCP stdio server, a local FastAPI proxy, or a standalone CLI tool in a single Python file.
* **Implicit Caching Support (`--repo-dir`)**: Automatically packages project files and places them first in the context window. When repository tokens exceed Google's threshold, input pricing drops from `$2.00 / 1M` to **`$0.10 / 1M` (95% discount)**.
* **Accurate Token & Cost Telemetry**: Calculates exact dollar costs for uncached input, cached input, and reasoning/output tokens, tracking cumulative spend against your $10 USD monthly credit in `~/.gemini/argon-telemetry.json`.
* **Windows & PowerShell Hardened**: Strips UTF-8 BOM (`\ufeff`) from standard input pipes to prevent JSON-RPC crashes on Windows.
* **Transient 503 Auto-Retry**: Implements exponential backoff to transparently handle high-demand spikes (`503 UNAVAILABLE`) from Google's reasoning clusters.

---

## 🛠️ Quick Installation

### 1. Clone the repository
```bash
git clone https://github.com/Dardo-sys/antigravity-argon-proxy.git
cd antigravity-argon-proxy
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure your API Key
Copy the template and paste your Google AI Studio API key:
```bash
cp .env.example .env
```
Inside `.env`:
```env
GEMINI_API_KEY="your_ai_studio_api_key_here"
```
*(The proxy also automatically detects `GEMINI_API_KEY` from `~/.gemini/.env` or system environment variables).*

---

## 🚀 Modes of Operation

### Mode 1: Antigravity IDE (MCP Server over stdio)

Add the server to your Antigravity configuration (either in `.agents/mcp_config.json` inside your project root or globally in `~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "argon-proxy": {
      "command": "python",
      "args": [
        "/ABSOLUTE/PATH/TO/antigravity-argon-proxy/argon_antigravity_proxy.py",
        "--mode",
        "mcp"
      ],
      "env": {
        "GEMINI_API_KEY": "your_ai_studio_api_key_here"
      }
    }
  }
}
```

Restart Antigravity IDE or reload MCP. You will now have two native tools available:
* **`ask_argon`**: Delegates deep architectural reviews, multi-file debugging, or heavy reasoning to `gemini-4-argon`.
* **`argon_telemetry`**: Checks your accumulated consumption and remaining balance.

---

### Mode 2: Local HTTP Proxy (FastAPI)

Run the local server on port 8000:
```bash
python argon_antigravity_proxy.py --mode http --port 8000
```
*(On Windows, you can also double-click `INICIAR_PROXY_HTTP.bat`).*

* **OpenAI-Compatible Endpoint:** `http://127.0.0.1:8000/v1/chat/completions`  
  Works out of the box with any OpenAI SDK client, Cursor, Continue, or web UI.
* **Native Endpoint:** `http://127.0.0.1:8000/api/argon`

#### Example OpenAI request:
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain metaplasticity in AI agents"}],
    "reasoning_effort": "medium"
  }'
```

---

### Mode 3: Direct CLI & Sub-Agent Tool

Query Argon directly from the command line:

```bash
# Simple query with medium thinking
python argon_antigravity_proxy.py --prompt "Audit this algorithm" --thinking-level medium

# Whole repository review with 95% discount implicit caching
python argon_antigravity_proxy.py --prompt "Review architecture and race conditions" --repo-dir ./src --thinking-level high

# Attach specific files or screenshots
python argon_antigravity_proxy.py --prompt "Find the bug in this script" --file app.py --file error_screenshot.png
```
*(On Windows, double-click `CONSULTAR_ARGON_CLI.bat` for an interactive prompt, or `VER_SALDO_TELEMETRIA.bat` to inspect accumulated spend).*

---

## 📌 Important Setup Notes (Google AI Studio Billing)

To use `gemini-4-argon`, Google requires the AI Studio project to be in **Pay-as-you-go** or **Cloud Prepay** mode:

1. **Free Tier Restriction (Error 429)**: In a purely unbilled Free Tier project, Google sets the quota of `gemini-4-argon` to `0`.
2. **Cloud Prepay Requirement (Error 402)**: In countries where Google Cloud operates on prepaid billing, the account requires a minimum positive balance (e.g., $5 USD initial deposit) to open the API gateway.
3. **Credit Application**: Google automatically applies your promotional credits (such as the **$10 USD/mo** from Google Developer Program) **first** before touching your prepaid deposit:
   > *"Eligible Google Cloud credits will automatically be applied to usage first."*

---

## 💰 Cost Control & Safe Usage (How to not burn your credits)

To ensure you never burn through your credits unintentionally, follow these best practices:

### 1. Division of Labor (95% Free vs. 5% Surgical)
* **Daily Development ($0.00 Cost):** Let your primary Antigravity model (e.g., Gemini Flash) handle routine tasks like code editing, shell commands, unit tests, and general questions. This consumes zero API credits.
* **On-Demand Deep Reasoning:** Only invoke Argon when dealing with difficult tasks: intricate concurrency bugs, full-repo architectural audits, or formal proofs. In chat, Argon is strictly triggered on-demand (e.g., *"Ask Argon to review..."*).

### 2. Set a Hard Spending Limit in Google AI Studio
In your [Google AI Studio Spend Dashboard](https://aistudio.google.com/app/spend), click **"Set monthly budget limit"** (or *Establecer límite de inversión*) and set a cap (e.g., **$10 USD**).
* Once the cap is reached, Google cuts API access immediately.
* It is physically impossible to incur unwanted excess charges.

### 3. Automatic Google Implicit Caching (95% Discount)
* When reviewing whole repositories with `--repo-dir` or attaching multi-file context, Google caches the prompt prefix automatically.
* Cached input tokens cost only **$0.10 / 1M tokens** (down from $2.00 / 1M), allowing hundreds of large queries within the $10 USD allowance.

### 4. Built-in Telemetry & Ledger
Every query outputs a real-time accounting block and persists metrics to `~/.gemini/argon-telemetry.json`:
* Check remaining balance anytime via the MCP tool `argon_telemetry` or by running `VER_SALDO_TELEMETRIA.bat`.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

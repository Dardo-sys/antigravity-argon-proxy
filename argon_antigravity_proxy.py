#!/usr/bin/env python3
"""
Argon Antigravity Proxy & Sub-Agent Bridge (gemini-4-argon)
===========================================================
Multipurpose proxy to access Gemini 4 Argon (`gemini-4-argon`) from Google
Antigravity (IDE, Web, CLI, or Sub-Agent scripts) using a Google AI Studio API key
(e.g., leveraging the $10 USD/mo GenAI credit from Google Developer Program / Google AI Pro).

Supports 3 execution modes in a single lightweight script:
  1. MCP Server (stdio) for Antigravity IDE / Agent tool use:
     python argon_antigravity_proxy.py --mode mcp

  2. Local HTTP Proxy (FastAPI - compatible with OpenAI /v1/chat/completions and /api/argon):
     python argon_antigravity_proxy.py --mode http --port 8000

  3. CLI / Sub-Agent Tool (with token telemetry, cost breakdown, and implicit repo caching):
     python argon_antigravity_proxy.py --prompt "Audit this code" --thinking-level high --repo-dir .
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Suppress verbose third-party loggers and warnings
warnings.filterwarnings("ignore")
logging.getLogger("google.genai").setLevel(logging.ERROR)
os.environ["PYTHONWARNINGS"] = "ignore"

# Ensure UTF-8 on Windows stdin/stdout/stderr pipes
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Model constants and official pricing (USD per 1M tokens)
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gemini-4-argon"
PRICE_INPUT_UNCACHED_PER_1M = 2.00
PRICE_INPUT_CACHED_PER_1M = 0.10
PRICE_OUTPUT_PER_1M = 10.00

MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".agents",
    ".idea",
    ".vscode",
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".sql", ".sh", ".rs",
    ".go", ".java", ".c", ".cpp", ".h", ".hpp",
}


# ---------------------------------------------------------------------------
# Configuration and API Key loader
# ---------------------------------------------------------------------------
def load_api_key() -> str:
    """Finds GEMINI_API_KEY in environment, script dir, cwd, or ~/.gemini/.env."""
    env_candidates = [
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
        Path.home() / ".gemini" / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists():
            try:
                for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(
                            k.strip(), v.strip().strip('"').strip("'")
                        )
            except Exception:
                pass

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key and "PASTE_YOUR" not in api_key:
        return api_key

    settings_path = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            key = data.get("gemini_api_key") or data.get("apiKey")
            if key and "PASTE_YOUR" not in key:
                return key
        except Exception:
            pass

    raise RuntimeError(
        "GEMINI_API_KEY not found. Set it as an environment variable, "
        "in a .env file (GEMINI_API_KEY=your_key) or in ~/.gemini/.env."
    )


def get_telemetry_path() -> Path:
    return Path.home() / ".gemini" / "argon-telemetry.json"


def record_telemetry(
    uncached_input: int,
    cached_input: int,
    output_tokens: int,
    thinking_level: str,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """Calculates call cost and records it to ~/.gemini/argon-telemetry.json."""
    cost_usd = (
        (uncached_input * (PRICE_INPUT_UNCACHED_PER_1M / 1_000_000))
        + (cached_input * (PRICE_INPUT_CACHED_PER_1M / 1_000_000))
        + (output_tokens * (PRICE_OUTPUT_PER_1M / 1_000_000))
    )
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "thinking_level": thinking_level,
        "uncached_input_tokens": uncached_input,
        "cached_input_tokens": cached_input,
        "output_tokens": output_tokens,
        "cost_usd": round(cost_usd, 6),
    }

    telemetry_file = get_telemetry_path()
    ledger: List[Dict[str, Any]] = []
    if telemetry_file.exists():
        try:
            loaded = json.loads(telemetry_file.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                ledger = loaded
        except Exception:
            ledger = []

    ledger.append(entry)
    try:
        telemetry_file.parent.mkdir(parents=True, exist_ok=True)
        telemetry_file.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    total_spent = sum(item.get("cost_usd", 0.0) for item in ledger)
    entry["cumulative_cost_usd"] = round(total_spent, 5)
    entry["remaining_from_10usd_credit"] = round(max(0.0, 10.0 - total_spent), 4)
    return entry


# ---------------------------------------------------------------------------
# Context packaging (files, images, repos)
# ---------------------------------------------------------------------------
def collect_repo_context(repo_dir: Path, max_bytes: int = 500_000) -> str:
    """Traverses repository files to build a cacheable prefix for Gemini 4 Argon."""
    if not repo_dir.exists() or not repo_dir.is_dir():
        return ""

    chunks: List[str] = [f"=== REPOSITORY CONTEXT: {repo_dir.resolve()} ==="]
    accumulated = 0

    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for fname in sorted(files):
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                rel = fpath.relative_to(repo_dir)
                content = fpath.read_text(encoding="utf-8", errors="replace")
                block = f"\n--- FILE: {rel} ---\n{content}\n"
                if accumulated + len(block.encode("utf-8")) > max_bytes:
                    chunks.append("\n[... Context truncated by safety byte limit ...]")
                    return "\n".join(chunks)
                chunks.append(block)
                accumulated += len(block.encode("utf-8"))
            except Exception:
                continue

    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# Core Gemini 4 Argon client (google-genai SDK)
# ---------------------------------------------------------------------------
def call_argon(
    prompt: str,
    thinking_level: str = "medium",
    system_instruction: Optional[str] = None,
    files: Optional[List[str]] = None,
    repo_dir: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Executes a query against `gemini-4-argon` using the official `google-genai` SDK.
    Places repository and file context first to maximize Implicit Caching (95% discount).
    """
    api_key = load_api_key()
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "The 'google-genai' package is not installed. Run: pip install google-genai"
        ) from exc

    contents: List[Any] = []

    # 1. Repo context first (to maximize 95% discount via implicit caching)
    if repo_dir:
        repo_blob = collect_repo_context(Path(repo_dir))
        if repo_blob:
            contents.append(repo_blob)

    # 2. Individual files (images/PDFs as bytes, code/text as blocks)
    for file_str in files or []:
        fpath = Path(file_str)
        if not fpath.exists():
            continue
        suffix = fpath.suffix.lower()
        if suffix in MIME_BY_SUFFIX:
            contents.append(
                types.Part.from_bytes(
                    data=fpath.read_bytes(), mime_type=MIME_BY_SUFFIX[suffix]
                )
            )
        else:
            text_data = fpath.read_text(encoding="utf-8", errors="replace")
            contents.append(f"--- FILE: {fpath} ---\n{text_data}\n")

    # 3. Support for @file prompt prefix
    resolved_prompt = prompt
    if prompt.startswith("@"):
        prompt_file = Path(prompt[1:])
        if prompt_file.is_file():
            resolved_prompt = prompt_file.read_text(encoding="utf-8")

    contents.append(resolved_prompt)

    client = genai.Client(api_key=api_key)

    config_kwargs: Dict[str, Any] = {
        "thinking_config": types.ThinkingConfig(
            thinking_level=thinking_level.lower()
        )
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if temperature is not None:
        config_kwargs["temperature"] = temperature
    if max_output_tokens is not None:
        config_kwargs["max_output_tokens"] = max_output_tokens

    config = types.GenerateContentConfig(**config_kwargs)

    # Retry loop with backoff for transient 503 / high demand spikes
    max_retries = 4
    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            break
        except Exception as exc:
            err_msg = str(exc)
            if ("503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise

    usage = getattr(response, "usage_metadata", None)
    uncached_in = getattr(usage, "prompt_token_count", 0) or 0
    cached_in = getattr(usage, "cached_content_token_count", 0) or 0
    if cached_in > 0 and uncached_in >= cached_in:
        uncached_in -= cached_in
    out_tokens = getattr(usage, "candidates_token_count", 0) or 0

    telemetry = record_telemetry(
        uncached_input=uncached_in,
        cached_input=cached_in,
        output_tokens=out_tokens,
        thinking_level=thinking_level,
        model=model,
    )

    return {
        "text": response.text or "",
        "telemetry": telemetry,
    }


def generate_answer(
    context: str,
    thinking_level: str = "medium",
    system_instruction: str = "You are a reflective principal software engineer operating on Gemini 4 Argon.",
) -> str:
    """Direct callable wrapper for Antigravity Conscious Mode or custom Python scripts."""
    result = call_argon(
        prompt=context,
        thinking_level=thinking_level,
        system_instruction=system_instruction,
    )
    return result["text"]


# ---------------------------------------------------------------------------
# MODE 1: MCP Server (Model Context Protocol over stdio) for Antigravity IDE
# ---------------------------------------------------------------------------
MCP_TOOLS = [
    {
        "name": "ask_argon",
        "description": (
            "Delegate complex architecture design, multi-file debugging, "
            "security audits, or deep reasoning tasks to Gemini 4 Argon (gemini-4-argon)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed instruction and problem context for Argon.",
                },
                "thinking_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                    "description": "Reasoning effort level for Argon (low, medium, high).",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of file paths or images (.png, .jpg, .pdf, code) to attach.",
                },
                "repo_dir": {
                    "type": "string",
                    "description": "Optional root directory path to package and cache the repository prefix.",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "argon_telemetry",
        "description": "Query cumulative token consumption and remaining monthly credit balance.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


def handle_mcp_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params") or {}

    if method == "notifications/initialized" or req_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "argon-antigravity-proxy",
                    "version": "1.0.0",
                },
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS},
        }

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}

        try:
            if tool_name == "ask_argon":
                res = call_argon(
                    prompt=args.get("prompt", ""),
                    thinking_level=args.get("thinking_level", "medium"),
                    files=args.get("files"),
                    repo_dir=args.get("repo_dir"),
                )
                tel = res["telemetry"]
                footer = (
                    f"\n\n---\n"
                    f"**Argon Telemetry** (`{tel['thinking_level']}`): "
                    f"In: `{tel['uncached_input_tokens']:,}` | "
                    f"Cached: `{tel['cached_input_tokens']:,}` | "
                    f"Out+Think: `{tel['output_tokens']:,}` | "
                    f"Cost: `${tel['cost_usd']:.5f} USD` "
                    f"(Total Spent: `${tel['cumulative_cost_usd']:.4f} USD` | "
                    f"Remaining $10 Credit: `${tel['remaining_from_10usd_credit']:.2f} USD`)"
                )
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": res["text"] + footer}
                        ],
                        "isError": False,
                    },
                }

            if tool_name == "argon_telemetry":
                tpath = get_telemetry_path()
                ledger = (
                    json.loads(tpath.read_text(encoding="utf-8"))
                    if tpath.exists()
                    else []
                )
                total_cost = sum(x.get("cost_usd", 0.0) for x in ledger)
                summary = {
                    "total_calls": len(ledger),
                    "total_cost_usd": round(total_cost, 5),
                    "remaining_from_10usd_credit": round(max(0.0, 10.0 - total_cost), 4),
                    "last_5_calls": ledger[-5:],
                }
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(summary, indent=2, ensure_ascii=False),
                            }
                        ],
                        "isError": False,
                    },
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error calling Argon: {exc}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {},
    }


def run_mcp_stdio_server() -> None:
    """Main JSON-RPC stdio loop for Antigravity MCP with Windows BOM stripping."""
    for raw_line in sys.stdin:
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_mcp_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as exc:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse/Internal error: {exc}"},
            }
            sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# MODE 2: Local HTTP Proxy (FastAPI) - Compatible with OpenAI & Antigravity Web
# ---------------------------------------------------------------------------
def run_http_proxy(host: str = "127.0.0.1", port: int = 8000) -> None:
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
        import uvicorn
    except ImportError:
        sys.stderr.write(
            "Error: HTTP mode requires fastapi and uvicorn:\n"
            "  pip install fastapi uvicorn google-genai\n"
        )
        sys.exit(1)

    app = FastAPI(
        title="Argon Antigravity Proxy",
        description="Local proxy to Gemini 4 Argon (gemini-4-argon) compatible with OpenAI and Antigravity.",
        version="1.0.0",
    )

    class ArgonDirectRequest(BaseModel):
        prompt: str
        thinking_level: str = "medium"
        system_instruction: Optional[str] = None
        files: Optional[List[str]] = None
        repo_dir: Optional[str] = None

    class OpenAIMessage(BaseModel):
        role: str
        content: Any

    class OpenAIChatRequest(BaseModel):
        model: str = DEFAULT_MODEL
        messages: List[OpenAIMessage]
        reasoning_effort: Optional[str] = "medium"
        temperature: Optional[float] = None
        max_tokens: Optional[int] = None

    @app.get("/health")
    def health() -> Dict[str, str]:
        return {"status": "ok", "target_model": DEFAULT_MODEL}

    @app.get("/v1/models")
    def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": DEFAULT_MODEL,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "google",
                }
            ],
        }

    @app.post("/api/argon")
    def api_argon(req: ArgonDirectRequest) -> Dict[str, Any]:
        try:
            return call_argon(
                prompt=req.prompt,
                thinking_level=req.thinking_level,
                system_instruction=req.system_instruction,
                files=req.files,
                repo_dir=req.repo_dir,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/chat/completions")
    def openai_chat_completions(req: OpenAIChatRequest) -> Dict[str, Any]:
        try:
            sys_parts: List[str] = []
            convo_parts: List[str] = []
            for msg in req.messages:
                content_str = (
                    msg.content
                    if isinstance(msg.content, str)
                    else json.dumps(msg.content, ensure_ascii=False)
                )
                if msg.role == "system":
                    sys_parts.append(content_str)
                else:
                    convo_parts.append(f"[{msg.role.upper()}]: {content_str}")

            prompt_text = "\n\n".join(convo_parts)
            sys_inst = "\n".join(sys_parts) if sys_parts else None
            level = (req.reasoning_effort or "medium").lower()
            if level not in ("low", "medium", "high"):
                level = "medium"

            res = call_argon(
                prompt=prompt_text,
                thinking_level=level,
                system_instruction=sys_inst,
                temperature=req.temperature,
                max_output_tokens=req.max_tokens,
                model=DEFAULT_MODEL,
            )
            tel = res["telemetry"]
            prompt_tokens = tel["uncached_input_tokens"] + tel["cached_input_tokens"]
            completion_tokens = tel["output_tokens"]

            return {
                "id": f"chatcmpl-argon-{int(time.time())}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": DEFAULT_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": res["text"]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "argon_telemetry": tel,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    uvicorn.run(app, host=host, port=port)


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Argon Antigravity Proxy & Sub-Agent Bridge (gemini-4-argon)."
    )
    parser.add_argument(
        "--mode",
        choices=["cli", "mcp", "http"],
        default="cli",
        help="Operating mode: 'mcp' (Antigravity stdio server), 'http' (FastAPI local proxy), or 'cli' (direct invocation).",
    )
    parser.add_argument(
        "--thinking-level",
        choices=["low", "medium", "high"],
        default="medium",
        help="Gemini 4 Argon reasoning effort level (default: medium).",
    )
    parser.add_argument(
        "--prompt",
        help="Prompt text or @path/to/prompt.txt for CLI mode.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Path to file or image (.png, .jpg, .webp, .pdf, code) to attach. Repeatable.",
    )
    parser.add_argument(
        "--repo-dir",
        help="Project directory to package and leverage Google Implicit Caching ($0.10/1M tokens).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for HTTP mode (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP mode (default: 8000).",
    )

    args = parser.parse_args()

    if args.mode == "mcp":
        run_mcp_stdio_server()
        return

    if args.mode == "http":
        run_http_proxy(host=args.host, port=args.port)
        return

    if not args.prompt:
        parser.error("In 'cli' mode, --prompt is required (or use --mode mcp / --mode http).")

    try:
        res = call_argon(
            prompt=args.prompt,
            thinking_level=args.thinking_level,
            files=args.file,
            repo_dir=args.repo_dir,
        )
    except Exception as exc:
        sys.stderr.write(f"Error: {exc}\n")
        sys.exit(1)

    if res["text"]:
        print(res["text"])

    tel = res["telemetry"]
    print("\n" + "=" * 68)
    print(
        f"Argon Telemetry [{tel['thinking_level']}]: "
        f"In: {tel['uncached_input_tokens']:,} | "
        f"Cached: {tel['cached_input_tokens']:,} | "
        f"Out+Think: {tel['output_tokens']:,} | "
        f"Est. Cost: ${tel['cost_usd']:.5f} USD "
        f"(Remaining from $10 Credit: ${tel['remaining_from_10usd_credit']:.2f} USD)"
    )
    print("=" * 68)


if __name__ == "__main__":
    main()

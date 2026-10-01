"""Run the PS-MCP eval suite.

For each prompt in prompts.yaml, opens a fresh MCP session and runs the
unharnessed agent ``EVAL_REPEATS`` times. Full traces are written as JSONL to
``evals/results/run-<timestamp>.jsonl`` for the scorer to consume.

Usage:
    uv run python evals/runner.py
    uv run python evals/runner.py --only downstream_customer_count
"""

import argparse
import asyncio
import datetime
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

# Support running as a script or a module.
try:
    from .config import EvalConfig, load_config
    from .mcp_agent import run_prompt
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config import EvalConfig, load_config
    from mcp_agent import run_prompt

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("evals.runner")


def _load_prompts(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    prompts = data.get("prompts", []) if isinstance(data, dict) else []
    if not prompts:
        raise ValueError(f"No prompts found in {path}")
    return prompts


def _build_llm(cfg: EvalConfig) -> Any:
    """Construct an OpenAI-compatible client from config."""
    if cfg.use_azure:
        from openai import AzureOpenAI

        import os

        return AzureOpenAI(
            api_key=cfg.openai_key,
            azure_endpoint=cfg.openai_base_url or "",
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    from openai import OpenAI

    return OpenAI(api_key=cfg.openai_key, base_url=cfg.openai_base_url or None)


def _insecure_httpx_factory(cfg: EvalConfig):
    """Build an httpx client factory that honors the SSL verify setting.

    fastmcp's OAuth helper creates its own httpx clients for the discovery and
    token exchanges; we must inject verify=False for internal Esri certs.
    """
    import httpx

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        # Accept whatever fastmcp passes (headers, timeout, auth,
        # follow_redirects, ...) and force our SSL verify setting.
        kwargs.setdefault("follow_redirects", True)
        kwargs["verify"] = cfg.verify_ssl
        return httpx.AsyncClient(**kwargs)

    return factory


def _make_client(cfg: EvalConfig) -> Client:
    """Create a FastMCP client for the configured server URL and auth mode.

    - bearer: send a static Authorization header (works with USE_ARCGIS_AUTH
      servers and open servers).
    - oauth: run the OAuth 2.1 flow via the browser; fastmcp caches the issued
      token. Required for OAuthProxy deployments (USE_ARCGIS_OAUTH).
    """
    if cfg.auth_mode == "oauth":
        from fastmcp.client.auth import OAuth

        oauth = OAuth(
            mcp_url=cfg.mcp_url,
            callback_port=cfg.oauth_callback_port,
            httpx_client_factory=_insecure_httpx_factory(cfg),
        )
        transport = StreamableHttpTransport(
            url=cfg.mcp_url,
            auth=oauth,
            verify=cfg.verify_ssl,
            httpx_client_factory=_insecure_httpx_factory(cfg),
        )
        return Client(transport)

    transport = StreamableHttpTransport(
        url=cfg.mcp_url,
        headers=cfg.auth_headers,
        verify=cfg.verify_ssl,
    )
    return Client(transport)


async def _run_suite(cfg: EvalConfig, only: str | None) -> Path:
    prompts = _load_prompts(cfg.prompts_path)
    if only:
        prompts = [p for p in prompts if p.get("id") == only]
        if not prompts:
            raise ValueError(f"No prompt with id={only!r}")

    llm = _build_llm(cfg)

    cfg.results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = cfg.results_dir / f"run-{stamp}.jsonl"

    logger.info(
        "Running %d prompt(s) x %d repeat(s) against %s (model=%s)",
        len(prompts),
        cfg.repeats,
        cfg.mcp_url,
        cfg.model,
    )

    with out_path.open("w", encoding="utf-8") as out:
        for prompt in prompts:
            pid = prompt["id"]
            text = prompt["prompt"].strip()
            expects = prompt.get("expects", {})
            for run_idx in range(cfg.repeats):
                # Fresh session per run — no memory carryover.
                async with _make_client(cfg) as client:
                    trace = await run_prompt(
                        client=client,
                        llm=llm,
                        model=cfg.model,
                        prompt_id=pid,
                        prompt_text=text,
                        max_steps=cfg.max_steps,
                    )
                record = {
                    "prompt_id": pid,
                    "run_index": run_idx,
                    "model": cfg.model,
                    "expects": expects,
                    "trace": trace.to_json(),
                }
                out.write(json.dumps(record, default=str) + "\n")
                out.flush()
                status = "ok" if not trace.error else f"ERR({trace.error})"
                logger.info("  %s run %d/%d -> %s", pid, run_idx + 1, cfg.repeats, status)

    logger.info("Wrote results to %s", out_path)
    return out_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the PS-MCP eval suite.")
    parser.add_argument("--only", help="Run a single prompt id")
    args = parser.parse_args(argv)

    cfg = load_config()
    if not cfg.mcp_token:
        logger.error(
            "No token set. Export EVAL_MCP_TOKEN (or ARCGIS_TOKEN) before running."
        )
        sys.exit(1)
    if not cfg.openai_key:
        logger.error("No LLM key set. Export OPENAI_KEY before running.")
        sys.exit(1)

    asyncio.run(_run_suite(cfg, args.only))


if __name__ == "__main__":
    main()

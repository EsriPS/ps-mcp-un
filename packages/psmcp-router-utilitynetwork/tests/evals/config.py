"""Environment-driven configuration for the PS-MCP eval harness."""

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_URL = "https://bnundev.esri.com/psmcp"
_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_REPEATS = 5
_DEFAULT_MAX_STEPS = 12


@dataclass(frozen=True)
class EvalConfig:
    """Resolved eval configuration.

    All values come from environment variables so the same harness can target
    different servers, models, and repeat counts without code changes.
    """

    mcp_url: str
    mcp_token: str | None
    model: str
    repeats: int
    max_steps: int
    use_azure: bool
    openai_key: str | None
    openai_base_url: str | None
    prompts_path: Path
    results_dir: Path
    verify_ssl: bool = True
    auth_mode: str = "bearer"  # "bearer" | "oauth"
    oauth_callback_port: int = 8765
    extra_headers: dict[str, str] = field(default_factory=dict)

    @property
    def auth_headers(self) -> dict[str, str]:
        """Return the Authorization header block for the MCP client, if a token is set."""
        headers = dict(self.extra_headers)
        if self.mcp_token:
            headers["Authorization"] = f"Bearer {self.mcp_token}"
        return headers


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_config() -> EvalConfig:
    """Build an :class:`EvalConfig` from the current environment.

    Returns:
        A frozen config object. Raises no error if the token is missing so that
        ``--dry-run`` style discovery-only checks can still run; the runner
        validates the token before making authenticated calls.
    """
    here = Path(__file__).resolve().parent
    # SSL verification: EVAL_VERIFY_SSL wins if set, otherwise follow the
    # project-wide ARCGIS_VERIFY_SSL convention (default True). Internal Esri
    # servers with self-signed certs need this set to false.
    verify_raw = os.getenv("EVAL_VERIFY_SSL") or os.getenv("ARCGIS_VERIFY_SSL", "True")
    return EvalConfig(
        mcp_url=os.getenv("EVAL_MCP_URL", _DEFAULT_URL).rstrip("/"),
        mcp_token=os.getenv("EVAL_MCP_TOKEN") or os.getenv("ARCGIS_TOKEN"),
        model=os.getenv("EVAL_MODEL", _DEFAULT_MODEL),
        repeats=_int_env("EVAL_REPEATS", _DEFAULT_REPEATS),
        max_steps=_int_env("EVAL_MAX_STEPS", _DEFAULT_MAX_STEPS),
        use_azure=os.getenv("AZURE_OPENAI", "false").lower() == "true",
        openai_key=os.getenv("OPENAI_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        prompts_path=here / "prompts.yaml",
        results_dir=here / "results",
        verify_ssl=verify_raw.lower() != "false",
        auth_mode=os.getenv("EVAL_AUTH_MODE", "bearer").strip().lower(),
        oauth_callback_port=_int_env("EVAL_OAUTH_CALLBACK_PORT", 8765),
    )

"""Run analysis passes through the Claude CLI in headless mode.

Each pass is a one-shot `claude -p` call with tools disabled — the agent gets a
prompt containing verified figures and filing text, and returns structured JSON.
No filesystem or network access is needed for analysis, so we grant none.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = os.environ.get("ER_MODEL", "claude-opus-5")
DEFAULT_TIMEOUT = int(os.environ.get("ER_TIMEOUT", "600"))


class AnalysisError(RuntimeError):
    pass


@dataclass
class AnalysisResult:
    output: dict | str
    session_id: str | None
    cost_usd: float | None
    raw: dict


def _claude_binary() -> str:
    path = shutil.which("claude")
    if not path:
        raise AnalysisError("`claude` not found on PATH. Install the Claude Code CLI first.")
    return path


def run_pass(
    prompt: str,
    *,
    schema: dict | None = None,
    system_prompt: str | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> AnalysisResult:
    """Execute one headless analysis pass.

    With `schema`, Claude is forced to return an object matching it, surfaced in
    the response's `structured_output` field. Without one, you get plain text.
    """
    cmd = [
        _claude_binary(),
        "-p",
        "--output-format",
        "json",
        "--model",
        model,
        # Analysis is pure reasoning over the prompt; deny every tool so an
        # unattended run can never touch the filesystem or the network.
        "--allowedTools",
        "",
        "--permission-mode",
        "default",
    ]

    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]

    schema_file: Path | None = None
    if schema is not None:
        fd, name = tempfile.mkstemp(suffix=".json", prefix="er-schema-")
        schema_file = Path(name)
        with os.fdopen(fd, "w") as handle:
            json.dump(schema, handle)
        cmd += ["--json-schema", str(schema_file)]

    try:
        completed = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,  # returncode is inspected below for a better message
        )
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError(f"Analysis pass timed out after {timeout}s") from exc
    finally:
        if schema_file is not None:
            schema_file.unlink(missing_ok=True)

    if completed.returncode != 0:
        raise AnalysisError(
            f"claude exited {completed.returncode}: {completed.stderr.strip()[:2000]}"
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"Could not parse claude output: {completed.stdout[:2000]}") from exc

    if payload.get("is_error"):
        raise AnalysisError(f"Analysis pass failed: {payload.get('result')}")

    output: dict | str
    if schema is not None:
        output = payload.get("structured_output") or {}
        if not output:
            raise AnalysisError("Schema was requested but no structured_output returned")
    else:
        output = payload.get("result", "")

    return AnalysisResult(
        output=output,
        session_id=payload.get("session_id"),
        cost_usd=payload.get("total_cost_usd"),
        raw=payload,
    )

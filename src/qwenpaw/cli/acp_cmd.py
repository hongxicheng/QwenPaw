# -*- coding: utf-8 -*-
"""``qwenpaw acp`` — run QwenPaw as an ACP agent over stdio."""
from __future__ import annotations

import asyncio
import logging
import sys

import click


@click.command("acp")
@click.option(
    "--agent",
    default=None,
    help="Agent ID to use (defaults to active agent)",
)
@click.option(
    "--workspace",
    default=None,
    type=click.Path(exists=False),
    help="Workspace directory override",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging to stderr",
)
@click.option(
    "--local-diagnostics",
    is_flag=True,
    default=False,
    help=(
        "Surface raw unexpected error text to the ACP client. Intended for "
        "local clients that own this ACP subprocess, such as the TUI."
    ),
)
@click.option(
    "--runtime-provider",
    type=click.Choice(["openai-env"], case_sensitive=False),
    default=None,
    help=(
        "Use an ephemeral provider from OPENAI_BASE_URL, "
        "OPENAI_API_KEY, and OPENAI_MODEL."
    ),
)
@click.option(
    f"--agent-mode",
    type=str,
    metavar=f"MODE_ID",
    default=None,
    help=(
        f"Select a QwenPaw agent loop mode (e.g. goal, mission, "
        f"custom:<id>, plugin:<name>), or 'coding' to enable Code Mode "
        f"before the workspace starts. Loop modes apply their registered "
        f"slash command to the first message of each new session. "
        f"This does not change ACP permission settings."
    ),
)
@click.option(
    f"--goal-token-budget",
    type=click.IntRange(min=-1),
    default=0,
    show_default=True,
    help=f"Token budget per goal. -1 or 0 means unlimited.",
)
@click.option(
    "--mode",
    type=click.Choice(["coding"]),
    default=None,
    hidden=True,
    help=f"Deprecated alias for --agent-mode coding.",
)
def acp_cmd(
    agent: str | None,
    workspace: str | None,
    debug: bool,
    local_diagnostics: bool,
    runtime_provider: str | None,
    agent_mode: str | None,
    goal_token_budget: int,
    mode: str | None,
) -> None:
    """Start QwenPaw as an ACP agent (stdio)."""
    from pathlib import Path

    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )

    workspace_dir = Path(workspace) if workspace else None
    provider_config = None
    if runtime_provider == "openai-env":
        from ..agents.acp.runtime_provider import (
            OpenAIRuntimeProviderConfig,
        )

        try:
            provider_config = OpenAIRuntimeProviderConfig.from_env()
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc

    from ..agents.acp.server import run_qwenpaw_agent, silence_stdout

    # Warm-up heavy native imports before the event loop starts. In the full
    # ACP runtime, the first `import numpy` (via agentscope.embedding inside
    # workspace bootstrap) can block indefinitely on the Windows loader lock
    # (all threads waiting, no concurrent import activity). Importing here,
    # before asyncio.run, completes the DLL load while nothing else is
    # contended and makes the workspace bootstrap pass through immediately.
    # Best-effort and Windows-only: numpy is a transitive dependency, not a
    # declared one, so environments without it must keep starting normally.
    if sys.platform == "win32":
        try:
            import numpy  # noqa: E401,F402  pylint: disable=unused-import
        except ModuleNotFoundError:
            pass

    # ``coding`` is a toolkit switch, not a loop mode. Keep it out of
    # ``agent_mode`` so the first-message slash-command path never sees it.
    code_mode = mode == "coding"
    if agent_mode == "coding":
        code_mode = True
        agent_mode = None

    try:
        asyncio.run(
            run_qwenpaw_agent(
                agent_id=agent,
                workspace_dir=workspace_dir,
                local_diagnostics=local_diagnostics,
                runtime_provider=provider_config,
                agent_mode=agent_mode,
                goal_token_budget=goal_token_budget,
                code_mode=code_mode,
            ),
        )
    finally:
        # The client may have closed both pipe directions. Redirect fd 1
        # before interpreter shutdown so the final flush cannot fail.
        silence_stdout()

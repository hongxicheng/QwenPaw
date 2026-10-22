# -*- coding: utf-8 -*-
"""Tests for ACP Code Mode activation."""
# pylint: disable=protected-access
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agents.acp.server import QwenPawACPAgent


def _config(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(coding_mode=SimpleNamespace(enabled=enabled))


def test_agent_mode_coding_normalizes_to_code_mode():
    agent = QwenPawACPAgent(agent_mode=f"coding")

    assert agent._code_mode is True
    assert agent._agent_mode is None
    assert agent._apply_agent_mode(f"Solve", f"session", None) == f"Solve"


def test_code_mode_can_combine_with_a_loop_mode():
    agent = QwenPawACPAgent(agent_mode=f"goal", code_mode=True)

    assert agent._code_mode is True
    assert agent._agent_mode == f"goal"


def test_default_does_not_enable_code_mode():
    agent = QwenPawACPAgent()

    assert agent._code_mode is False
    assert agent._agent_mode is None


def test_enable_coding_mode_flips_and_saves(monkeypatch):
    saved = []
    monkeypatch.setattr(
        "qwenpaw.agents.acp.server.load_agent_config",
        lambda agent_id: _config(False),
    )
    monkeypatch.setattr(
        "qwenpaw.config.config.save_agent_config",
        lambda agent_id, config: saved.append((agent_id, config)),
    )

    QwenPawACPAgent._enable_coding_mode("default")

    assert len(saved) == 1
    agent_id, config = saved[0]
    assert agent_id == "default"
    assert config.coding_mode.enabled is True


def test_enable_coding_mode_is_idempotent(monkeypatch):
    saved = []
    monkeypatch.setattr(
        "qwenpaw.agents.acp.server.load_agent_config",
        lambda agent_id: _config(True),
    )
    monkeypatch.setattr(
        "qwenpaw.config.config.save_agent_config",
        lambda agent_id, config: saved.append((agent_id, config)),
    )

    QwenPawACPAgent._enable_coding_mode("default")

    assert not saved

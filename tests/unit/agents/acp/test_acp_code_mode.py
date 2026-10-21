# -*- coding: utf-8 -*-
"""Tests for ACP ``--mode coding`` activation."""
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agents.acp.server import QwenPawACPAgent


def _config(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(coding_mode=SimpleNamespace(enabled=enabled))


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

    assert saved == []

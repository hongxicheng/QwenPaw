# -*- coding: utf-8 -*-
"""Tests for Code Mode Linux sandbox selection and Landlock wiring."""
# pylint: disable=protected-access
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from qwenpaw.modes.coding import _process
from qwenpaw.sandbox import MountSpec, SandboxConfig, SandboxMode


def _capability(
    mode: SandboxMode,
    abi_version: int = 0,
    supported: bool = True,
    reason: str = f"ok",
) -> SimpleNamespace:
    return SimpleNamespace(
        supported=supported,
        mode=mode,
        reason=reason,
        landlock_abi_version=abi_version,
    )


def test_auto_uses_probe_result(monkeypatch):
    monkeypatch.setenv(f"QWENPAW_CODE_MODE_SANDBOX", f"auto")
    monkeypatch.setattr(
        _process,
        f"probe_sandbox_support",
        lambda: _capability(SandboxMode.LANDLOCK, 4),
    )

    mode, abi_version = asyncio.run(_process._linux_sandbox_mode())

    assert mode == SandboxMode.LANDLOCK
    assert abi_version == 4


def test_auto_fails_closed_without_sandbox(monkeypatch):
    monkeypatch.setenv(f"QWENPAW_CODE_MODE_SANDBOX", f"auto")
    monkeypatch.setattr(
        _process,
        f"probe_sandbox_support",
        lambda: _capability(
            SandboxMode.NONE,
            supported=False,
            reason=f"no user namespaces",
        ),
    )

    with pytest.raises(RuntimeError, match=f"no sandbox"):
        asyncio.run(_process._linux_sandbox_mode())


def test_explicit_landlock_uses_landlock_probe(monkeypatch):
    monkeypatch.setenv(f"QWENPAW_CODE_MODE_SANDBOX", f"landlock")
    monkeypatch.setattr(
        _process,
        f"_probe_linux_landlock",
        lambda: _capability(SandboxMode.LANDLOCK, 3),
    )

    assert asyncio.run(_process._linux_sandbox_mode()) == (
        SandboxMode.LANDLOCK,
        3,
    )


def test_explicit_none_is_allowed(monkeypatch):
    monkeypatch.setenv(f"QWENPAW_CODE_MODE_SANDBOX", f"none")

    assert asyncio.run(_process._linux_sandbox_mode()) == (
        SandboxMode.NONE,
        0,
    )


def test_unknown_value_is_rejected(monkeypatch):
    monkeypatch.setenv(f"QWENPAW_CODE_MODE_SANDBOX", f"seatbelt")

    with pytest.raises(RuntimeError, match=f"must be auto"):
        asyncio.run(_process._linux_sandbox_mode())


def test_landlock_command_writes_restricted_wrapper(tmp_path):
    directory = str(tmp_path)
    config = SandboxConfig(
        mode=SandboxMode.SEATBELT,
        workspace_dir=directory,
        allow_read_all=False,
        mounts=[MountSpec(directory, writable=True)],
        network_allow=[],
    )
    command = [f"/usr/bin/python3", f"-I", f"-S", f"-u", f"worker.py"]

    wrapped = _process.WorkerProcess._landlock_command(
        command,
        config,
        directory,
        4,
    )

    wrapper = Path(directory) / "landlock-wrapper.py"
    script = wrapper.read_text(encoding=f"utf-8")
    assert wrapped == [
        f"/usr/bin/python3",
        f"-I",
        f"-S",
        f"-u",
        str(wrapper),
    ]
    assert f"libc.syscall" in script
    assert f"PR_SET_NO_NEW_PRIVS" in script
    assert f"restrict_self" in script
    assert f"exec /usr/bin/python3" in script
    assert directory in script
    # The shared /tmp grant is dropped; only the worker directory stays.
    assert f"add_path('/tmp'" not in script

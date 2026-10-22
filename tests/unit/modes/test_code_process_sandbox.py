# -*- coding: utf-8 -*-
"""Tests for Code Mode Linux sandbox selection and Landlock wiring."""
# pylint: disable=protected-access
from __future__ import annotations

import asyncio
import subprocess
import sys
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


@pytest.mark.skipif(
    sys.platform != f"linux",
    reason=f"Landlock is Linux-only",
)
def test_landlock_wrapper_blocks_paths_outside_workspace(tmp_path):
    from qwenpaw.sandbox.config import _probe_linux_landlock

    capability = _probe_linux_landlock()
    if not capability.supported:
        pytest.skip(capability.reason)

    allowed = tmp_path / f"allowed"
    denied = tmp_path / f"denied"
    allowed.mkdir()
    denied.mkdir()
    secret = denied / f"secret.txt"
    secret.write_text(f"secret", encoding=f"utf-8")
    result = allowed / f"result.txt"
    probe = allowed / f"probe.py"
    probe.write_text(
        f"from pathlib import Path\n"
        f"try:\n"
        f"    Path({str(secret)!r}).read_text()\n"
        f"except Exception:\n"
        f"    Path({str(result)!r}).write_text('denied')\n"
        f"else:\n"
        f"    Path({str(result)!r}).write_text('readable')\n",
        encoding=f"utf-8",
    )
    config = SandboxConfig(
        mode=SandboxMode.SEATBELT,
        workspace_dir=str(allowed),
        allow_read_all=False,
        mounts=[MountSpec(str(allowed), writable=True)],
        network_allow=[],
    )
    wrapped = _process.WorkerProcess._landlock_command(
        [sys.executable, str(probe)],
        config,
        str(allowed),
        capability.landlock_abi_version,
    )

    completed = subprocess.run(
        wrapped,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert result.read_text(encoding=f"utf-8") == f"denied"

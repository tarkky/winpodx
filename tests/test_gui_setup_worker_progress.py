# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

_FINISH_PROVISIONING_STAGES: tuple[tuple[str, str], ...] = (
    ("wait_ready", "Waiting for the pod to become responsive..."),
    ("agent_settle", "Guest agent settling..."),
    ("apply_fixes", "Applying Windows-side runtime fixes..."),
    ("discovery", "Discovering and registering apps..."),
    ("reverse_open", "Starting reverse-open listener..."),
)


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_setup_worker_exposes_progress_signal() -> None:
    _ensure_qapp()
    from winpodx.gui._setup_wizard_worker import SetupWorker

    assert hasattr(SetupWorker, "progress")


def test_setup_worker_forwards_handle_setup_stage_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_qapp()

    def _fake_handle_setup(args, *, on_progress=None) -> None:
        assert on_progress is not None
        for stage, detail in _FINISH_PROVISIONING_STAGES:
            on_progress(stage, detail)

    monkeypatch.setattr("winpodx.cli.setup_cmd.handle_setup", _fake_handle_setup)
    from winpodx.gui._setup_wizard_worker import SetupWorker

    worker = SetupWorker(argparse.Namespace(), reinstall=False)
    stages: list[tuple[str, str]] = []
    worker.progress.connect(lambda stage, detail: stages.append((stage, detail)))
    done: list[tuple[bool, str]] = []
    worker.finished.connect(lambda ok, err: done.append((ok, err)))

    worker.run()

    assert stages == list(_FINISH_PROVISIONING_STAGES)
    assert done == [(True, "")]

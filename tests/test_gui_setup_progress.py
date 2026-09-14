# SPDX-License-Identifier: MIT
"""Regression tests for setup-wizard chrome and install-progress rendering.

Two confirmed defects on current main, each locked here by behaviour
(widgets / signals), never by implementation prose:

1. ``SetupWizardDialog`` does not use the default frameless ``TitleBar``
   chrome the rest of the GUI uses, and ignores ``WINPODX_NATIVE_TITLEBAR=1``.
2. The wizard never connects worker progress into the ``InstallPage``
   checklist / visible log, so multi-stage progression is invisible.

Everything is patched at the lookup site; no real podman/docker/system
state is touched.
"""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from winpodx.setup_wizard.host_state import HostState  # noqa: E402

# The real finish_provisioning stage slugs on the podman/docker path, in order,
# each with a distinct detail so log + checklist advancement is verifiable. The
# manual-backend-only "backend" early-return stage is not on this path.
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


def _ok_state() -> HostState:
    return HostState(
        in_kvm_group=True,
        kvm_group_exists=True,
        dev_kvm_present=True,
        dev_kvm_readable=True,
        subuid_configured=True,
        subgid_configured=True,
        kvm_module_persistent=True,
    )


def _patch_detect(monkeypatch: pytest.MonkeyPatch, detect) -> None:
    monkeypatch.setattr("winpodx.gui._setup_wizard_prereq.detect_host_state", detect)
    monkeypatch.setattr("winpodx.setup_wizard.host_state.detect_host_state", detect)


def _wait_until(pred, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    app = QApplication.instance()
    while time.monotonic() < deadline:
        if pred():
            return
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    raise AssertionError("timed out waiting for wizard state")


# --------------------------------------------------------------------------
# Defect 1 — SetupWizardDialog chrome: frameless TitleBar + native opt-out
# --------------------------------------------------------------------------


def test_wizard_uses_frameless_titlebar_chrome_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_qapp()
    _patch_detect(monkeypatch, _ok_state)
    monkeypatch.setattr("winpodx.cli.setup_cmd.handle_setup", lambda args: None)
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)
    from winpodx.gui._frameless import FramelessMixin
    from winpodx.gui._setup_wizard import SetupWizardDialog

    dlg = SetupWizardDialog(None, mode="first-run")
    try:
        # Given: the default (no native-titlebar) environment.
        # Then: the wizard opts into the same frameless chrome as the main UI.
        assert isinstance(dlg, FramelessMixin)
        assert getattr(dlg, "_frameless_active", False) is True
        assert bool(dlg.windowFlags() & Qt.WindowType.FramelessWindowHint) is True
        assert getattr(dlg, "title_bar", None) is not None
        assert dlg.title_bar.objectName() == "titleBar"
    finally:
        dlg.close()


def test_wizard_honors_native_titlebar_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _ensure_qapp()
    _patch_detect(monkeypatch, _ok_state)
    monkeypatch.setattr("winpodx.cli.setup_cmd.handle_setup", lambda args: None)
    monkeypatch.setenv("WINPODX_NATIVE_TITLEBAR", "1")
    from winpodx.gui._setup_wizard import SetupWizardDialog

    dlg = SetupWizardDialog(None, mode="first-run")
    try:
        # Given: WINPODX_NATIVE_TITLEBAR=1.
        # Then: the wizard keeps native decorations (no frameless hint).
        assert getattr(dlg, "_frameless_active", True) is False
        assert bool(dlg.windowFlags() & Qt.WindowType.FramelessWindowHint) is False
    finally:
        dlg.close()


# --------------------------------------------------------------------------
# Defect 2 — wizard wires worker progress into checklist + visible log
# --------------------------------------------------------------------------


def test_wizard_reflects_worker_progress_in_checklist_and_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_qapp()
    _patch_detect(monkeypatch, _ok_state)

    def _fake_handle_setup(args, *, on_progress=None) -> None:
        assert on_progress is not None
        for stage, detail in _FINISH_PROVISIONING_STAGES:
            on_progress(stage, detail)

    monkeypatch.setattr("winpodx.cli.setup_cmd.handle_setup", _fake_handle_setup)
    from winpodx.gui._setup_wizard import SetupWizardDialog

    dlg = SetupWizardDialog(None, mode="first-run")
    dlg.show()
    try:
        for _ in range(4):
            dlg.next_btn.click()
        _wait_until(lambda: dlg.pages.currentIndex() == 5)

        progress = dlg.install.progress
        assert progress is not None

        # Then: every stage's distinct detail reached the visible log, and each
        #       of the five stages advanced its own checklist row (all five
        #       custom rows started, not just the first two).
        log_text = dlg.install.log_text()
        assert "pod log unavailable" not in log_text
        for _stage, detail in _FINISH_PROVISIONING_STAGES:
            assert detail in log_text

        started_rows = len(progress._phase_started_at)
        assert started_rows == len(_FINISH_PROVISIONING_STAGES)
        assert dlg._scroll.verticalScrollBar().maximum() == 0
    finally:
        _wait_until(lambda: dlg._thread is None)
        dlg.close()

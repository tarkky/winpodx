# SPDX-License-Identifier: MIT
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_custom_phase_header_uses_run_specific_label() -> None:
    _ensure_qapp()
    from winpodx.gui._main_window_bringup import BringUpProgressDialog

    dlg = BringUpProgressDialog(
        None,
        on_cancel=lambda: None,
        cfg=None,
        phases=(("phase_1_pod", "Install Windows", "usually 5-10 min", False),),
    )
    try:
        dlg.on_phase("phase_1_pod", "Downloading and installing Windows...")
        header = dlg.header.text()
        assert "Install Windows" in header
        assert "Pod ready" not in header
    finally:
        dlg.close()

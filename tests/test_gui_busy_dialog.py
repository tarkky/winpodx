# SPDX-License-Identifier: MIT
"""``BusyDialog`` on the shared DialogChrome (DESIGN.md DD-004)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
)

from winpodx.gui import theme  # noqa: E402
from winpodx.gui._dialog_chrome import ChromeDialog  # noqa: E402
from winpodx.gui._title_bar import TitleBar  # noqa: E402
from winpodx.gui._widget_helpers import BusyDialog  # noqa: E402

_BODY_W = 480
_BODY_H = 168


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _frameless_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)


def test_busy_dialog_opens_with_close_only_chrome_showing_its_own_title(
    qapp: QApplication,
) -> None:
    dlg = BusyDialog(None, "Scanning", "Looking for applications")
    try:
        assert isinstance(dlg, ChromeDialog)
        assert dlg._frameless_active is True
        assert dlg.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dlg.windowTitle() == "Scanning"

        bar = dlg.title_bar
        assert isinstance(bar, TitleBar)
        assert bar.height() == theme.TITLE_BAR_H
        assert bar.title_label.text() == "Scanning"
        assert [b.objectName() for b in bar.findChildren(QPushButton)] == ["captionClose"]
        assert bar.btn_minimize is None and bar.btn_maximize is None
        assert dlg.chrome_height == theme.TITLE_BAR_H
    finally:
        dlg.close()


def test_busy_dialog_body_sits_below_the_chrome_with_the_prior_room(
    qapp: QApplication,
) -> None:
    dlg = BusyDialog(None, "Working", "Doing a thing...", eta_hint="usually ~1 min")
    try:
        assert dlg.minimumSize().width() == _BODY_W
        assert dlg.minimumSize().height() == _BODY_H + theme.TITLE_BAR_H
        assert dlg.isModal()

        body_labels = [label.text() for label in dlg.content_widget.findChildren(QLabel)]
        assert body_labels == ["Doing a thing...", "usually ~1 min"]
        progress = dlg.content_widget.findChild(QProgressBar)
        assert progress is not None
        assert progress.minimum() == 0 and progress.maximum() == 0

        dlg.show()
        qapp.processEvents()
        assert dlg.title_bar.geometry().top() == 0
        assert dlg.content_widget.geometry().top() == theme.TITLE_BAR_H
        assert dlg.content_widget.height() >= _BODY_H
        assert dlg.content_widget.width() >= _BODY_W
    finally:
        dlg.close()


def test_busy_dialog_keeps_the_prior_floor_under_native_titlebar(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WINPODX_NATIVE_TITLEBAR", "1")
    dlg = BusyDialog(None, "Working", "Doing a thing...")
    try:
        assert dlg._frameless_active is False
        assert not (dlg.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert dlg.title_bar is not None and dlg.title_bar.isHidden()
        assert dlg.chrome_height == 0
        assert dlg.minimumSize().width() == _BODY_W
        assert dlg.minimumSize().height() == _BODY_H
    finally:
        dlg.close()


def test_busy_dialog_finish_still_accepts(qapp: QApplication) -> None:
    dlg = BusyDialog(None, "Working", "First message")
    dlg.set_message("Second message")

    dlg.finish()

    assert dlg._msg.text() == "Second message"
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert dlg.content_widget.findChildren(QPushButton) == []


def test_busy_dialog_cancel_lives_in_the_body_and_still_fires_callbacks(
    qapp: QApplication,
) -> None:
    cancelled: list[bool] = []
    dlg = BusyDialog(None, "Scanning", "Looking for applications", cancellable=True)
    dlg.on_cancel(lambda: cancelled.append(True))
    dlg.show()
    try:
        body_buttons = dlg.content_widget.findChildren(QPushButton)
        assert [b.text() for b in body_buttons] == ["Cancel"]
        assert body_buttons[0] is not dlg.title_bar.btn_close

        body_buttons[0].click()

        assert cancelled == [True]
        assert body_buttons[0].text() == "Cancelling..."
        assert not body_buttons[0].isEnabled()
        assert dlg.isVisible()  # cancel is best-effort; caller closes via finish()
    finally:
        dlg.close()


def test_caption_close_rejects_the_busy_dialog(qapp: QApplication) -> None:
    dlg = BusyDialog(None, "Working", "Doing a thing...")
    rejected: list[bool] = []
    dlg.rejected.connect(lambda: rejected.append(True))
    dlg.show()
    qapp.processEvents()

    dlg.title_bar.btn_close.click()
    qapp.processEvents()

    assert rejected == [True]
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()

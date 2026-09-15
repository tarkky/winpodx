# SPDX-License-Identifier: MIT
"""Contract tests for ``ChromeDialog`` (DESIGN.md "DialogChrome")."""

from __future__ import annotations

import os
import re
import weakref
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from winpodx.gui import theme  # noqa: E402
from winpodx.gui._dialog_chrome import ChromeDialog  # noqa: E402
from winpodx.gui._frameless import FramelessMixin  # noqa: E402
from winpodx.gui._title_bar import TitleBar  # noqa: E402
from winpodx.gui.theme_manager import instance as theme_manager_instance  # noqa: E402

_GUI_DIR = Path(__file__).resolve().parents[1] / "src" / "winpodx" / "gui"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _frameless_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)


class _Confirm(ChromeDialog):
    def __init__(self) -> None:
        super().__init__(None, title="Delete app?")
        self.setStyleSheet(theme.DIALOG)
        body = QVBoxLayout(self.content_widget)
        body.addWidget(QLabel("Really?"))
        self.ok = QPushButton("OK")
        self.ok.clicked.connect(self.accept)
        body.addWidget(self.ok)


def test_chrome_dialog_is_a_frameless_qdialog_with_close_only_bar(qapp: QApplication) -> None:
    dlg = _Confirm()
    try:
        assert isinstance(dlg, QDialog)
        assert isinstance(dlg, FramelessMixin)
        assert dlg._frameless_active is True
        assert dlg.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dlg.windowTitle() == "Delete app?"

        bar = dlg.title_bar
        assert isinstance(bar, TitleBar)
        assert bar.objectName() == "titleBar"
        assert bar.height() == theme.TITLE_BAR_H
        assert bar.title_label.text() == "Delete app?"
        assert [b.objectName() for b in bar.findChildren(QPushButton)] == ["captionClose"]
        assert bar.btn_minimize is None and bar.btn_maximize is None
        assert dlg.chrome_height == theme.TITLE_BAR_H
    finally:
        dlg.close()


def test_edge_resizer_filter_tracks_dialog_visibility(qapp: QApplication) -> None:
    dlg = _Confirm()
    try:
        assert dlg._edge_resizer_installed is False

        dlg.show()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is True

        dlg.hide()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is False

        dlg.show()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is True

        dlg.reject()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is False
    finally:
        dlg.close()


def test_edge_resizer_filter_cleanup_survives_repeated_dialogs(qapp: QApplication) -> None:
    for _ in range(50):
        dlg = _Confirm()
        assert dlg._edge_resizer_installed is False
        dlg.show()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is True
        dlg.close()
        qapp.processEvents()
        assert dlg._edge_resizer_installed is False


def test_closed_dialog_does_not_wait_for_cyclic_gc(
    qapp: QApplication, capsys: pytest.CaptureFixture[str]
) -> None:
    def close_dialog() -> weakref.ReferenceType[_Confirm]:
        dlg = _Confirm()
        ref = weakref.ref(dlg)
        dlg.show()
        qapp.processEvents()
        dlg.close()
        qapp.processEvents()
        return ref

    assert close_dialog()() is None
    qapp.processEvents()
    assert "Error calling Python override" not in capsys.readouterr().err


def test_title_bar_is_first_in_a_zero_margin_layout_over_transparent_content(
    qapp: QApplication,
) -> None:
    dlg = _Confirm()
    try:
        outer = dlg.layout()
        assert outer.contentsMargins().left() == 0
        assert outer.contentsMargins().top() == 0
        assert outer.contentsMargins().right() == 0
        assert outer.contentsMargins().bottom() == 0
        assert outer.spacing() == 0
        assert outer.count() == 2
        assert outer.itemAt(0).widget() is dlg.title_bar
        assert outer.itemAt(1).widget() is dlg.content_widget
        assert dlg.content_widget.objectName() == "dialogContent"
        assert "transparent" in dlg.content_widget.styleSheet()
        assert dlg.content_widget.hasMouseTracking()

        dlg.resize(400, 300)
        dlg.show()
        qapp.processEvents()
        assert dlg.title_bar.geometry().top() == 0
        assert dlg.content_widget.geometry().top() == theme.TITLE_BAR_H
        assert dlg.title_bar.width() == dlg.width()
    finally:
        dlg.close()


def test_caption_close_rejects_like_a_plain_qdialog(qapp: QApplication) -> None:
    dlg = _Confirm()
    rejected: list[bool] = []
    dlg.rejected.connect(lambda: rejected.append(True))
    dlg.show()
    qapp.processEvents()

    dlg.title_bar.btn_close.click()
    qapp.processEvents()

    assert rejected == [True]
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()


def test_accept_and_modality_are_untouched(qapp: QApplication) -> None:
    dlg = _Confirm()
    dlg.setModal(True)
    dlg.show()
    qapp.processEvents()
    assert dlg.isModal()

    dlg.ok.click()
    qapp.processEvents()

    assert dlg.result() == QDialog.DialogCode.Accepted
    assert not dlg.isVisible()


def test_native_titlebar_env_keeps_wm_decorations_and_hides_the_bar(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WINPODX_NATIVE_TITLEBAR", "1")
    dlg = _Confirm()
    try:
        assert dlg._frameless_active is False
        assert not (dlg.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert dlg.title_bar is not None
        assert dlg.title_bar.isHidden()
        assert dlg.chrome_height == 0

        dlg.show()
        qapp.processEvents()
        assert not dlg.title_bar.isVisible()
        assert dlg.content_widget.geometry().top() == 0
    finally:
        dlg.close()


def test_chrome_false_builds_no_bar_for_embedded_use(qapp: QApplication) -> None:
    dlg = ChromeDialog(None, title="Embedded", chrome=False)
    try:
        assert dlg.title_bar is None
        assert dlg._frameless_active is False
        assert not (dlg.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert dlg.chrome_height == 0
        assert dlg.windowTitle() == "Embedded"
        outer = dlg.layout()
        assert outer.count() == 1
        assert outer.itemAt(0).widget() is dlg.content_widget
    finally:
        dlg.close()


def test_scheme_change_restyles_the_bar_only(qapp: QApplication) -> None:
    previous = theme.current_scheme()
    manager = theme_manager_instance()
    dlg = _Confirm()
    body_style = dlg.styleSheet()
    try:
        manager.set_scheme("dark")
        assert theme.nav_pane_color() in dlg.title_bar.styleSheet()
        assert dlg.styleSheet() == body_style

        manager.set_scheme("light")
        assert theme.nav_pane_color() in dlg.title_bar.styleSheet()
        assert dlg.styleSheet() == body_style
    finally:
        manager.set_scheme(previous)
        dlg.close()


_PX_CALL = re.compile(
    r"\.(setContentsMargins|setSpacing|setFixedHeight|setFixedWidth|setFixedSize|"
    r"setMinimumSize|setMinimumHeight|setMinimumWidth|resize)\(([^)]*)\)"
)


def test_dialog_chrome_module_introduces_no_raw_colours_or_spacing() -> None:
    source = (_GUI_DIR / "_dialog_chrome.py").read_text(encoding="utf-8")

    assert re.search(r"#[0-9A-Fa-f]{6}\b", source) is None
    assert re.search(r"\brgba?\(", source) is None
    for _method, args in _PX_CALL.findall(source):
        for arg in (a.strip() for a in args.split(",") if a.strip()):
            assert arg == "0" or arg.startswith("theme."), (_method, arg)


def test_title_bar_module_keeps_only_its_pre_existing_colours() -> None:
    source = (_GUI_DIR / "_title_bar.py").read_text(encoding="utf-8")

    found = {m.upper() for m in re.findall(r"#[0-9A-Fa-f]{6}\b", source)}
    assert found == {"#C42B1C", "#B12A1B", "#FFFFFF"}

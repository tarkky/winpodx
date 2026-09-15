# SPDX-License-Identifier: MIT
"""Fluent restyle pins for ``gui.app_dialog.AppProfileDialog``."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QMargins, QPoint, QSize, Qt  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QFrame,
    QMessageBox,
    QPushButton,
    QWidget,
)

from winpodx.gui import theme  # noqa: E402
from winpodx.gui._dialog_chrome import ChromeDialog  # noqa: E402
from winpodx.gui.app_dialog import AppProfileDialog  # noqa: E402

_OLD_HEX = ("#0d1117", "#161b22", "#21262d", "#58a6ff", "#e6edf3")


def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _frameless_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)


def _button(dlg: AppProfileDialog, text: str) -> QPushButton:
    return next(btn for btn in dlg.findChildren(QPushButton) if btn.text() == text)


def test_app_dialog_has_no_legacy_hex_and_primary_is_32px() -> None:
    _ensure_qapp()
    dlg = AppProfileDialog()
    try:
        styles = [dlg.styleSheet() or ""]
        styles.extend(child.styleSheet() or "" for child in dlg.findChildren(QWidget))
        joined = "\n".join(styles).lower()
        for hex_color in _OLD_HEX:
            assert hex_color not in joined
        primary = next(
            btn for btn in dlg.findChildren(QPushButton) if btn.text() in {"Create", "Save"}
        )
        assert primary.minimumHeight() >= 32
    finally:
        dlg.deleteLater()


def test_app_dialog_rebuild_uses_current_theme() -> None:
    _ensure_qapp()
    previous = theme.current_scheme()
    try:
        theme.rebuild("light")
        light = AppProfileDialog()
        light_primary = next(
            btn for btn in light.findChildren(QPushButton) if btn.text() == "Create"
        )
        assert theme.C.MANTLE in light.styleSheet()
        assert theme.C.BLUE in light_primary.styleSheet()
        assert "#2B2B2B" not in light.styleSheet()
        light.deleteLater()

        theme.rebuild("dark")
        dark = AppProfileDialog()
        dark_primary = next(btn for btn in dark.findChildren(QPushButton) if btn.text() == "Create")
        assert "#191919" in dark.styleSheet()
        assert theme.C.BLUE in dark_primary.styleSheet()
        dark.deleteLater()
    finally:
        theme.rebuild(previous)


def test_app_dialog_has_a_button_strip_and_32px_fields() -> None:
    from PySide6.QtWidgets import QFrame, QLineEdit

    _ensure_qapp()
    dlg = AppProfileDialog()
    try:
        strip = dlg.findChild(QFrame, "dialogButtonStrip")
        assert strip is not None
        for field in dlg.findChildren(QLineEdit):
            assert field.minimumHeight() >= 32
        primary = next(
            btn for btn in dlg.findChildren(QPushButton) if btn.text() in {"Create", "Save"}
        )
        assert primary.minimumWidth() >= 96
        assert primary.minimumHeight() >= 32
    finally:
        dlg.deleteLater()


@pytest.mark.parametrize(("edit_mode", "title"), [(False, "Add App"), (True, "Edit App")])
def test_app_dialog_wears_close_only_chrome_with_its_window_title(
    edit_mode: bool, title: str
) -> None:
    _ensure_qapp()
    dlg = AppProfileDialog(edit_mode=edit_mode)
    try:
        assert isinstance(dlg, ChromeDialog)
        assert dlg._frameless_active is True
        assert dlg.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dlg.windowTitle() == title
        bar = dlg.title_bar
        assert bar is not None
        assert bar.title_label.text() == title
        assert [b.objectName() for b in bar.findChildren(QPushButton)] == ["captionClose"]
        assert bar.btn_minimize is None and bar.btn_maximize is None
    finally:
        dlg.close()


def test_app_dialog_mounts_header_form_and_strip_on_the_chrome_content_widget() -> None:
    qapp = _ensure_qapp()
    dlg = AppProfileDialog()
    try:
        outer = dlg.layout()
        assert outer.count() == 2
        assert outer.itemAt(0).widget() is dlg.title_bar
        assert outer.itemAt(1).widget() is dlg.content_widget

        body = dlg.content_widget.layout()
        assert body.contentsMargins() == QMargins(0, 0, 0, 0)
        assert body.spacing() == 0
        assert body.count() == 3
        strip = dlg.findChild(QFrame, "dialogButtonStrip")
        assert body.itemAt(2).widget() is strip
        assert strip.parentWidget() is dlg.content_widget
        assert dlg._avatar.parentWidget() is body.itemAt(0).widget()
        assert dlg.input_name.parentWidget() is body.itemAt(1).widget()

        dlg.show()
        qapp.processEvents()
        assert dlg.title_bar.geometry().top() == 0
        assert dlg.content_widget.geometry().top() == theme.TITLE_BAR_H
        header = body.itemAt(0).widget()
        assert header.mapTo(dlg, QPoint(0, 0)).y() == theme.TITLE_BAR_H
        assert header.width() == dlg.width()
        assert strip.mapTo(dlg, QPoint(0, strip.height())).y() == dlg.height()
    finally:
        dlg.close()


def test_app_dialog_adds_the_chrome_on_top_of_its_prior_body_space() -> None:
    qapp = _ensure_qapp()
    dlg = AppProfileDialog()
    try:
        assert dlg.chrome_height == theme.TITLE_BAR_H
        assert dlg.minimumSize() == QSize(580, 540 + theme.TITLE_BAR_H)
        assert dlg.size() == QSize(600, 560 + theme.TITLE_BAR_H)

        dlg.show()
        qapp.processEvents()
        assert dlg.content_widget.height() == 560
    finally:
        dlg.close()


def test_app_dialog_native_titlebar_env_keeps_prior_dimensions_and_wm_decorations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WINPODX_NATIVE_TITLEBAR", "1")
    qapp = _ensure_qapp()
    dlg = AppProfileDialog(edit_mode=True)
    try:
        assert dlg._frameless_active is False
        assert not (dlg.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert dlg.windowTitle() == "Edit App"
        assert dlg.title_bar is not None
        assert dlg.title_bar.isHidden()
        assert dlg.chrome_height == 0
        assert dlg.minimumSize() == QSize(580, 540)
        assert dlg.size() == QSize(600, 560)

        dlg.show()
        qapp.processEvents()
        assert not dlg.title_bar.isVisible()
        assert dlg.content_widget.geometry().top() == 0
        assert dlg.content_widget.height() == 560
    finally:
        dlg.close()


def test_app_dialog_caption_close_rejects_and_leaves_the_form_untouched() -> None:
    qapp = _ensure_qapp()
    dlg = AppProfileDialog(name="word", full_name="Word", executable="C:\\word.exe")
    rejected: list[bool] = []
    dlg.rejected.connect(lambda: rejected.append(True))
    dlg.show()
    qapp.processEvents()

    dlg.title_bar.btn_close.click()
    qapp.processEvents()

    assert rejected == [True]
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()
    assert dlg.get_result()["name"] == "word"


def test_app_dialog_cancel_button_confirms_before_discarding_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qapp = _ensure_qapp()
    asked: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda _parent, title, _text: asked.append(title) or QMessageBox.StandardButton.No
        ),
    )
    dlg = AppProfileDialog(name="word", full_name="Word", executable="C:\\word.exe")
    rejected: list[bool] = []
    dlg.rejected.connect(lambda: rejected.append(True))
    dlg.show()
    qapp.processEvents()
    dlg.input_full_name.setText("Word 365")

    _button(dlg, "Cancel").click()
    qapp.processEvents()

    assert asked == ["Discard changes?"]
    assert rejected == []
    assert dlg.isVisible()
    dlg.close()


def test_app_dialog_cancel_button_rejects_a_clean_form_without_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    qapp = _ensure_qapp()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *_a, **_k: pytest.fail("clean form must not prompt")),
    )
    dlg = AppProfileDialog(name="word", full_name="Word", executable="C:\\word.exe")
    dlg.show()
    qapp.processEvents()

    _button(dlg, "Cancel").click()
    qapp.processEvents()

    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()

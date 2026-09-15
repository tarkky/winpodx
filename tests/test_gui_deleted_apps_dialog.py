# SPDX-License-Identifier: MIT
"""Tests for gui.deleted_apps_dialog — the un-delete UI for tombstoned app slugs.

The dialog owns no business logic: it lists tombstoned slugs and hands the chosen
ones back through ``on_restore``. These tests drive the real widgets under the
offscreen platform and click the actual buttons rather than calling the slots.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from winpodx.gui import theme  # noqa: E402
from winpodx.gui.deleted_apps_dialog import DeletedAppsDialog  # noqa: E402


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _frameless_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)


def _make(slugs):
    _ensure_qapp()
    restored: list[list[str]] = []
    dialog = DeletedAppsDialog(slugs=list(slugs), on_restore=restored.append)
    return dialog, restored


def _row_restore_button(dialog, slug: str):
    from PySide6.QtWidgets import QPushButton

    return dialog._rows[slug].findChild(QPushButton)


def test_rows_are_created_for_every_slug() -> None:
    dialog, _ = _make(["word", "excel"])

    assert set(dialog._rows) == {"word", "excel"}


def test_deleted_apps_dialog_rebuild_uses_current_theme() -> None:
    previous = theme.current_scheme()
    try:
        theme.rebuild("light")
        light, _ = _make(["word"])
        assert theme.C.MANTLE in light.styleSheet()
        assert "#2B2B2B" not in light.styleSheet()
        light.deleteLater()

        theme.rebuild("dark")
        dark, _ = _make(["word"])
        assert "#191919" in dark.styleSheet()
        dark.deleteLater()
    finally:
        theme.rebuild(previous)


def test_rows_are_listed_in_sorted_order() -> None:
    dialog, _ = _make(["word", "acrobat", "excel"])

    assert list(dialog._rows) == ["acrobat", "excel", "word"]


def test_empty_state_is_shown_when_nothing_is_tombstoned() -> None:
    dialog, _ = _make([])

    assert dialog._empty_lbl.isVisibleTo(dialog) is True
    assert dialog._restore_all_btn.isEnabled() is False


def test_empty_state_is_hidden_when_rows_exist() -> None:
    dialog, _ = _make(["word"])

    assert dialog._empty_lbl.isVisibleTo(dialog) is False
    assert dialog._restore_all_btn.isEnabled() is True


def test_restoring_one_reports_only_that_slug() -> None:
    dialog, restored = _make(["word", "excel"])

    _row_restore_button(dialog, "word").click()

    assert restored == [["word"]]


def test_restoring_one_drops_its_row() -> None:
    dialog, _ = _make(["word", "excel"])

    _row_restore_button(dialog, "word").click()

    assert list(dialog._rows) == ["excel"]


def test_restoring_the_last_row_returns_to_the_empty_state() -> None:
    dialog, _ = _make(["word"])

    _row_restore_button(dialog, "word").click()

    assert dialog._empty_lbl.isVisibleTo(dialog) is True
    assert dialog._restore_all_btn.isEnabled() is False


def test_restore_all_reports_every_remaining_slug() -> None:
    dialog, restored = _make(["word", "excel"])

    dialog._restore_all_btn.click()

    assert restored == [["excel", "word"]]


def test_restore_all_excludes_an_already_restored_slug() -> None:
    dialog, restored = _make(["word", "excel"])

    _row_restore_button(dialog, "word").click()
    dialog._restore_all_btn.click()

    assert restored == [["word"], ["excel"]]


def test_restore_all_closes_the_dialog() -> None:
    from PySide6.QtWidgets import QDialog

    dialog, _ = _make(["word"])

    dialog._restore_all_btn.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_restore_all_is_a_noop_with_no_rows() -> None:
    dialog, restored = _make([])

    dialog._on_restore_all()

    assert restored == []


_OLD_HEX = ("#0d1117", "#161b22", "#21262d", "#58a6ff", "#e6edf3")


def test_deleted_apps_dialog_has_no_legacy_hex_and_primary_is_32px() -> None:
    from PySide6.QtWidgets import QWidget

    dialog, _ = _make(["word"])
    styles = [dialog.styleSheet() or ""]
    styles.extend(child.styleSheet() or "" for child in dialog.findChildren(QWidget))
    joined = "\n".join(styles).lower()
    for hex_color in _OLD_HEX:
        assert hex_color not in joined
    assert dialog._restore_all_btn.minimumHeight() >= 32


def test_deleted_apps_dialog_has_a_button_strip() -> None:
    from PySide6.QtWidgets import QFrame

    dialog, _ = _make(["word"])
    strip = dialog.findChild(QFrame, "dialogButtonStrip")
    assert strip is not None
    assert dialog._restore_all_btn.minimumWidth() >= 96


def test_deleted_apps_dialog_wears_close_only_chrome_with_its_window_title() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    from winpodx.gui._dialog_chrome import ChromeDialog

    dialog, _ = _make(["word"])
    try:
        assert isinstance(dialog, ChromeDialog)
        assert dialog._frameless_active is True
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert dialog.windowTitle() == "Deleted Apps"
        bar = dialog.title_bar
        assert bar is not None
        assert bar.title_label.text() == "Deleted Apps"
        assert [b.objectName() for b in bar.findChildren(QPushButton)] == ["captionClose"]
        assert bar.btn_minimize is None and bar.btn_maximize is None
    finally:
        dialog.close()


def test_deleted_apps_dialog_mounts_its_body_on_the_chrome_content_widget() -> None:
    from PySide6.QtCore import QMargins, QPoint
    from PySide6.QtWidgets import QFrame, QLabel

    qapp = _ensure_qapp()
    dialog, _ = _make(["word"])
    try:
        outer = dialog.layout()
        assert outer.count() == 2
        assert outer.itemAt(0).widget() is dialog.title_bar
        assert outer.itemAt(1).widget() is dialog.content_widget

        body = dialog.content_widget.layout()
        assert body.contentsMargins() == QMargins(24, 20, 24, 20)
        assert body.spacing() == theme.SPACE_M
        heading = body.itemAt(0).widget()
        assert isinstance(heading, QLabel)
        assert heading.text() == "Restore deleted apps"
        strip = dialog.findChild(QFrame, "dialogButtonStrip")
        assert body.itemAt(body.count() - 1).widget() is strip
        assert strip.parentWidget() is dialog.content_widget
        assert dialog._rows["word"].window() is dialog

        dialog.show()
        qapp.processEvents()
        assert dialog.title_bar.geometry().top() == 0
        assert dialog.content_widget.geometry().top() == theme.TITLE_BAR_H
        assert heading.mapTo(dialog, QPoint(0, 0)) == QPoint(24, theme.TITLE_BAR_H + 20)
    finally:
        dialog.close()


def test_deleted_apps_dialog_adds_the_chrome_on_top_of_its_prior_minimum() -> None:
    from PySide6.QtCore import QSize

    dialog, _ = _make(["word"])
    try:
        assert dialog.chrome_height == theme.TITLE_BAR_H
        assert dialog.minimumSize() == QSize(440, 420 + theme.TITLE_BAR_H)
    finally:
        dialog.close()


def test_deleted_apps_dialog_native_titlebar_env_keeps_prior_minimum_and_wm_decorations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PySide6.QtCore import QSize, Qt

    monkeypatch.setenv("WINPODX_NATIVE_TITLEBAR", "1")
    qapp = _ensure_qapp()
    dialog, _ = _make(["word"])
    try:
        assert dialog._frameless_active is False
        assert not (dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        assert dialog.windowTitle() == "Deleted Apps"
        assert dialog.title_bar is not None
        assert dialog.title_bar.isHidden()
        assert dialog.chrome_height == 0
        assert dialog.minimumSize() == QSize(440, 420)

        dialog.show()
        qapp.processEvents()
        assert not dialog.title_bar.isVisible()
        assert dialog.content_widget.geometry().top() == 0
    finally:
        dialog.close()


def test_deleted_apps_dialog_caption_close_rejects_without_restoring() -> None:
    from PySide6.QtWidgets import QDialog

    qapp = _ensure_qapp()
    dialog, restored = _make(["word", "excel"])
    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))
    dialog.show()
    qapp.processEvents()

    dialog.title_bar.btn_close.click()
    qapp.processEvents()

    assert rejected == [True]
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert not dialog.isVisible()
    assert restored == []
    assert list(dialog._rows) == ["excel", "word"]

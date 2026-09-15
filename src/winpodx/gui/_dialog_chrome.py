# SPDX-License-Identifier: MIT
"""App-owned dialog chrome: the main window's title bar policy on a QDialog."""

from __future__ import annotations

from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from winpodx.gui._frameless import FramelessMixin
from winpodx.gui._title_bar import DIALOG_CONTROLS, TitleBar
from winpodx.gui.theme_manager import instance as theme_manager_instance


class ChromeDialog(FramelessMixin, QDialog):
    """QDialog that shares the main window's chrome (DESIGN.md "DialogChrome").

    Frameless with a close-only ``TitleBar`` showing ``title`` by default;
    ``WINPODX_NATIVE_TITLEBAR=1`` keeps WM decorations and hides the bar.
    ``chrome=False`` builds no bar and sets no frameless hint, for a dialog
    hosted inside another surface. Subclasses fill ``content_widget`` and own
    their body styling; modality and result codes are plain ``QDialog``.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "",
        chrome: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.title_bar: TitleBar | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if chrome:
            self._install_frameless(defer_edge_resizer=True)
            self.title_bar = TitleBar(self, title=title, controls=DIALOG_CONTROLS)
            self.title_bar.setVisible(self._frameless_active)
            outer.addWidget(self.title_bar)
            theme_manager_instance().scheme_changed.connect(self.title_bar.restyle)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("dialogContent")
        self.content_widget.setStyleSheet("QWidget#dialogContent { background: transparent; }")
        self.content_widget.setMouseTracking(True)
        outer.addWidget(self.content_widget, 1)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._install_edge_resizer()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        self._remove_edge_resizer()
        super().hideEvent(event)

    @property
    def chrome_height(self) -> int:
        if self.title_bar is None or not self._frameless_active:
            return 0
        return self.title_bar.height()

# SPDX-License-Identifier: MIT
"""Frameless main window: custom caption bar + system-driven edge resizing."""

from __future__ import annotations

import os
import weakref

from PySide6.QtCore import QEvent, QObject, QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from winpodx.gui import theme

_CURSOR_FOR_EDGES = {
    Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.TopEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.BottomEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.TopEdge | Qt.Edge.RightEdge: Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.BottomEdge | Qt.Edge.LeftEdge: Qt.CursorShape.SizeBDiagCursor,
}


def native_titlebar_requested() -> bool:
    return os.environ.get("WINPODX_NATIVE_TITLEBAR", "").strip().lower() in ("1", "true", "yes")


def edges_at(pos: QPoint, width: int, height: int, margin: int) -> Qt.Edge:
    edges = Qt.Edge(0)
    if pos.x() < margin:
        edges |= Qt.Edge.LeftEdge
    elif pos.x() >= width - margin:
        edges |= Qt.Edge.RightEdge
    if pos.y() < margin:
        edges |= Qt.Edge.TopEdge
    elif pos.y() >= height - margin:
        edges |= Qt.Edge.BottomEdge
    return edges


class _EdgeResizer(QObject):
    """App-level filter: presses on the window border start a system resize."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window_ref = weakref.ref(window)
        self._cursor_set = False

    @property
    def _window(self) -> QWidget:
        window = self._window_ref()
        if window is None:
            raise RuntimeError("frameless window no longer exists")
        return window

    def _window_pos(self, event: QMouseEvent) -> QPoint:
        return self._window.mapFromGlobal(event.globalPosition().toPoint())

    def _edges(self, event: QMouseEvent) -> Qt.Edge:
        if self._window.isMaximized() or self._window.isFullScreen():
            return Qt.Edge(0)
        pos = self._window_pos(event)
        return edges_at(pos, self._window.width(), self._window.height(), theme.RESIZE_MARGIN)

    def _set_cursor(self, edges: Qt.Edge) -> None:
        shape = _CURSOR_FOR_EDGES.get(edges)
        if shape is None:
            if self._cursor_set:
                QApplication.restoreOverrideCursor()
                self._cursor_set = False
            return
        if self._cursor_set:
            QApplication.changeOverrideCursor(shape)
        else:
            QApplication.setOverrideCursor(shape)
            self._cursor_set = True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not isinstance(event, QMouseEvent) or not isinstance(watched, QWidget):
            return False
        window = self._window_ref()
        if window is None or watched.window() is not window:
            return False
        if event.type() == QEvent.Type.MouseMove and not event.buttons():
            self._set_cursor(self._edges(event))
            return False
        if event.type() == QEvent.Type.MouseButtonPress and (
            event.button() == Qt.MouseButton.LeftButton
        ):
            edges = self._edges(event)
            handle = self._window.windowHandle()
            if edges and handle is not None and handle.startSystemResize(edges):
                return True
        return False


class FramelessMixin:
    """Opt the main window out of native decorations unless the user asks for them."""

    _frameless_active: bool = False
    _edge_resizer: _EdgeResizer | None = None
    _edge_resizer_installed: bool = False

    def _install_frameless(self, *, defer_edge_resizer: bool = False) -> None:
        self._remove_edge_resizer()
        if native_titlebar_requested():
            self._frameless_active = False
            return
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._frameless_active = True
        self._edge_resizer = _EdgeResizer(self)
        if not defer_edge_resizer:
            self._install_edge_resizer()
        for widget in (self, getattr(self, "centralWidget", lambda: None)()):
            if widget is not None:
                widget.setMouseTracking(True)

    def _install_edge_resizer(self) -> None:
        if not self._frameless_active or self._edge_resizer is None or self._edge_resizer_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._edge_resizer)
            self._edge_resizer_installed = True

    def _remove_edge_resizer(self) -> None:
        if self._edge_resizer is None or not self._edge_resizer_installed:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._edge_resizer)
        self._edge_resizer._set_cursor(Qt.Edge(0))
        self._edge_resizer_installed = False

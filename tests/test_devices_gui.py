# SPDX-License-Identifier: MIT
"""Headless smoke tests for the GUI Devices tab (#286, _main_window_devices)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QDialogButtonBox,
    QPushButton,
    QWidget,
)

import winpodx.gui._main_window_devices as devices_mod  # noqa: E402
import winpodx.gui._main_window_devices_cards as devices_cards  # noqa: E402
from winpodx.cli import device as DC  # noqa: E402
from winpodx.core import devices as D  # noqa: E402
from winpodx.core.config import Config  # noqa: E402
from winpodx.core.i18n import tr  # noqa: E402
from winpodx.gui import theme  # noqa: E402
from winpodx.gui._dialog_chrome import ChromeDialog  # noqa: E402
from winpodx.gui._main_window_devices import DevicesMixin  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def host(qapp, monkeypatch, tmp_path):
    # Isolate config to a temp XDG dir and stub the host enumeration / state.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = Config()
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(Config, "save", lambda self: None)
    monkeypatch.setattr(DC, "_guest_running", lambda _c: False)
    monkeypatch.setattr(
        DC,
        "_enumerate_host",
        lambda: [
            D.HostDevice(dtype="usb", did="1234:5678", label="ACME Dongle"),
            D.HostDevice(
                dtype="pci", did="0000:01:00.0", label="GPU", pci_class="03", iommu_group="15"
            ),
        ],
    )

    class _Host(DevicesMixin):
        pass

    h = _Host()
    # Keep a reference to the page so its Qt widget tree (and the column
    # layouts) isn't garbage-collected out from under the test.
    h._page = h._build_devices_page()  # type: ignore[attr-defined]
    h._cfg = cfg  # type: ignore[attr-defined]
    return h


def test_page_builds_and_populates(host):
    # Both devices unassigned -> 2 rows + a stretch in the host column.
    assert host._dev_host_col.count() == 3
    # Guest column empty -> placeholder + stretch.
    assert host._dev_guest_col.count() == 2


@pytest.mark.parametrize(
    ("pci_class", "class_label"),
    [("03", "Graphics"), ("ff", "PCI device")],
)
def test_pci_metadata_translates_ui_labels_only(host, monkeypatch, pci_class, class_label):
    calls: list[str] = []

    def fake_tr(text: str) -> str:
        calls.append(text)
        return f"T<{text}>"

    monkeypatch.setattr(devices_cards, "tr", fake_tr)
    row = host._device_row(
        D.HostDevice(
            dtype="pci",
            did="0000:01:00.0",
            label="Example Vendor Example Adapter",
            pci_class=pci_class,
            iommu_group="15",
        ),
        assigned=False,
    )
    texts = [label.text() for label in row.findChildren(devices_mod.QLabel)]

    assert any("T<IOMMU 15>" in text and f"T<{class_label}>" in text for text in texts)
    assert "IOMMU {group}" in calls
    assert class_label in calls
    assert "Example Vendor Example Adapter" not in calls
    assert "0000:01:00.0" not in calls


def test_usb_bus_metadata_is_translated_without_translating_the_device(host, monkeypatch):
    calls: list[str] = []

    def fake_tr(text: str) -> str:
        calls.append(text)
        return f"T<{text}>"

    monkeypatch.setattr(devices_cards, "tr", fake_tr)
    row = host._device_row(
        D.HostDevice(
            dtype="usb",
            did="1234:5678",
            label="Example Security Dongle",
            bus="003",
        ),
        assigned=False,
    )
    texts = [label.text() for label in row.findChildren(devices_mod.QLabel)]

    assert any("T<Bus 003>" in text for text in texts)
    assert "Bus {bus}" in calls
    assert "Example Security Dongle" not in calls
    assert "1234:5678" not in calls


def test_attach_usb_persists_and_moves_column(host):
    host._on_attach(D.HostDevice(dtype="usb", did="1234:5678", label="ACME Dongle"))
    assert host._cfg.pod.devices == ["usb|1234:5678|ACME Dongle"]
    # USB moved to guest column; only the PCI remains on the host side.
    assert host._dev_guest_col.count() == 2  # 1 row + stretch
    assert host._dev_host_col.count() == 2  # 1 row + stretch
    assert "Assigned" in host._devices_status.text()


def test_detach_persists(host):
    host._cfg.pod.devices = ["usb|1234:5678|ACME Dongle"]
    host._on_detach(D.HostDevice(dtype="usb", did="1234:5678", label="ACME Dongle"))
    assert host._cfg.pod.devices == []
    assert "Released" in host._devices_status.text()


def test_attach_usb_live_is_nonblocking(host, monkeypatch):
    # The slow live attach must run off the GUI thread — `_on_attach` returns
    # immediately with a "busy" status instead of freezing the window.
    import time

    monkeypatch.setattr(DC, "_guest_running", lambda _c: True)
    monkeypatch.setattr(host, "_render_devices", lambda: None)  # no off-thread widget rebuild
    started: list = []

    def _slow_attach(be, c, dc):
        started.append(dc.did)
        time.sleep(0.5)  # would freeze the GUI if run on the main thread

    monkeypatch.setattr(D, "live_attach", _slow_attach)

    t0 = time.monotonic()
    host._on_attach(D.HostDevice(dtype="usb", did="1234:5678", label="ACME"))
    elapsed = time.monotonic() - t0

    assert elapsed < 0.3  # returned without waiting for the 0.5s work
    assert host._dev_busy is True
    assert "Attaching" in host._devices_status.text()
    # drain the worker so it doesn't bleed into other tests
    for _ in range(100):
        if not host._dev_busy:
            break
        time.sleep(0.02)
    assert started == ["1234:5678"]


def test_pci_attach_requires_confirmation(host, monkeypatch):
    # The risky-PCI confirm is now a custom dialog (_confirm_risky_pci, which
    # renders the plain-language "host will lose ..." warning callout), not a
    # bare QMessageBox.warning. Mock that method's verdict.
    # Decline -> nothing persisted.
    monkeypatch.setattr(host, "_confirm_risky_pci", lambda host_dev, safety: False)
    host._on_attach(D.HostDevice(dtype="pci", did="0000:01:00.0", label="GPU", pci_class="03"))
    assert host._cfg.pod.devices == []

    # Accept -> persisted.
    monkeypatch.setattr(host, "_confirm_risky_pci", lambda host_dev, safety: True)
    host._on_attach(D.HostDevice(dtype="pci", did="0000:01:00.0", label="GPU", pci_class="03"))
    assert host._cfg.pod.devices == ["pci|0000:01:00.0|GPU"]


# ----- the risky-PCI confirm dialog itself --------------------------------


class _ConfirmHost(DevicesMixin, QWidget):
    """``host`` above is a plain object; a real dialog needs a QWidget parent."""


_RISKY_GPU = D.HostDevice(
    dtype="pci", did="0000:01:00.0", label="GPU", pci_class="03", iommu_group="15"
)
_UNSAFE = D.Safety(safe=False, reasons=["boot GPU", "IOMMU group 15 is shared"])


@pytest.fixture()
def confirm_host(qapp, monkeypatch):
    monkeypatch.setattr(D, "list_host_pci", lambda: [])
    h = _ConfirmHost()
    yield h
    h.deleteLater()


@pytest.fixture()
def driven_dialog(monkeypatch):
    """``act`` presses a real control from inside ``exec()``'s nested loop.

    The parented 4s guard rejects a dialog nothing closed, so a regression
    fails the test instead of hanging the suite.
    """
    monkeypatch.delenv("WINPODX_NATIVE_TITLEBAR", raising=False)

    class _Driven(ChromeDialog):
        seen: list = []

        @staticmethod
        def act(dlg) -> None:
            dlg.reject()

        def exec(self):  # noqa: A003 - mirrors QDialog.exec
            type(self).seen.append(self)
            QTimer.singleShot(0, lambda: type(self).act(self))
            guard = QTimer(self)
            guard.setSingleShot(True)
            guard.timeout.connect(self.reject)
            guard.start(4000)
            try:
                return super().exec()
            finally:
                guard.stop()

    monkeypatch.setattr(devices_mod, "ChromeDialog", _Driven)
    return _Driven


def _ok_button(dlg: QDialog) -> QPushButton:
    return dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)


def _cancel_button(dlg: QDialog) -> QPushButton:
    return dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel)


def test_confirm_risky_pci_wears_shared_chrome_and_pass_through_confirms(
    confirm_host, driven_dialog
):
    driven_dialog.act = staticmethod(lambda dlg: _ok_button(dlg).click())

    assert confirm_host._confirm_risky_pci(_RISKY_GPU, _UNSAFE) is True

    (dlg,) = driven_dialog.seen
    assert isinstance(dlg, ChromeDialog)
    assert dlg.parent() is confirm_host
    assert dlg.isModal()
    assert dlg.minimumWidth() == 460
    assert dlg.windowTitle() == tr("Risky passthrough")
    assert dlg.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert dlg.title_bar.title_label.text() == tr("Risky passthrough")
    assert dlg.title_bar.btn_minimize is None and dlg.title_bar.btn_maximize is None
    assert dlg.title_bar.btn_close is not None
    assert dlg.chrome_height == theme.TITLE_BAR_H
    assert dlg.layout().itemAt(0).widget() is dlg.title_bar
    assert dlg.layout().itemAt(1).widget() is dlg.content_widget

    body = dlg.content_widget.layout()
    assert body is not None
    assert body.contentsMargins().left() == theme.SPACE_L
    assert body.spacing() == theme.SPACE_M
    callout = body.itemAt(0).widget()
    assert callout.objectName() == "winpodxCallout"
    assert callout.parentWidget() is dlg.content_widget
    reasons = body.itemAt(1).widget()
    assert "• boot GPU" in reasons.text()
    assert "• IOMMU group 15 is shared" in reasons.text()
    assert _ok_button(dlg).text() == tr("Pass through anyway")
    assert _ok_button(dlg).parentWidget().parentWidget() is dlg.content_widget
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert not dlg.isVisible()


def test_confirm_risky_pci_cancel_declines(confirm_host, driven_dialog):
    driven_dialog.act = staticmethod(lambda dlg: _cancel_button(dlg).click())

    assert confirm_host._confirm_risky_pci(_RISKY_GPU, _UNSAFE) is False

    (dlg,) = driven_dialog.seen
    assert dlg.result() == QDialog.DialogCode.Rejected


def test_confirm_risky_pci_caption_close_declines(confirm_host, driven_dialog):
    driven_dialog.act = staticmethod(lambda dlg: dlg.title_bar.btn_close.click())

    assert confirm_host._confirm_risky_pci(_RISKY_GPU, _UNSAFE) is False

    (dlg,) = driven_dialog.seen
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert not dlg.isVisible()

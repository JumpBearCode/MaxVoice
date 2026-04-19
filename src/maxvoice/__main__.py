import sys
import traceback

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .app import App
from .gui.dictionary import DictionaryDialog
from .gui.history import HistoryDialog
from .gui.metrics import MetricsDialog
from .gui.settings import SettingsDialog
from .gui.tray import Tray


def _install_excepthook() -> None:
    # PyQt6 + Python 3.8+ aborts the process on any unhandled exception raised
    # inside a Qt slot. Replace excepthook so the tray app survives slot errors
    # (we still log them so they're not invisible).
    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb)
        try:
            QMessageBox.critical(None, "MaxVoice", f"{exc_type.__name__}: {exc}")
        except Exception:
            pass
    sys.excepthook = hook


def main() -> int:
    _install_excepthook()
    # On macOS, Qt swaps Ctrl/Meta by default. Disable it so keyPressEvent reports
    # physical modifiers faithfully (so we record the keys the user actually pressed).
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "MaxVoice", "System tray is not available on this system."
        )
        return 1

    app = App()
    tray = Tray()
    tray.show()
    print(f"[main] tray visible={tray.isVisible()}, sys tray available={QSystemTrayIcon.isSystemTrayAvailable()}", flush=True)

    # Show transient messages on transcription results / errors.
    def on_state(state: str) -> None:
        tray.set_state(state)

    def on_done(rec) -> None:
        preview = (rec.refined_text or rec.raw_text)[:60]
        tray.showMessage(
            f"Transcribed ({rec.duration_seconds:.1f}s)",
            preview,
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def on_error(msg: str) -> None:
        tray.showMessage("MaxVoice error", msg, QSystemTrayIcon.MessageIcon.Critical, 5000)

    app.state_changed.connect(on_state)
    app.transcription_done.connect(on_done)
    app.error.connect(on_error)

    # History / Metrics windows are cached so they can stay open; Settings is modal.
    history_win: dict = {"w": None}
    metrics_win: dict = {"w": None}

    def open_settings() -> None:
        try:
            dlg = SettingsDialog(app.cfg)
            if dlg.exec() == SettingsDialog.DialogCode.Accepted:
                app.apply_config(dlg.result_config())
                if history_win["w"] is not None and history_win["w"].isVisible():
                    history_win["w"].reload()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(None, "MaxVoice Settings", f"{type(e).__name__}: {e}")

    def open_history() -> None:
        if history_win["w"] is None:
            history_win["w"] = HistoryDialog()
        w = history_win["w"]
        w.reload()
        w.show()
        w.raise_()
        w.activateWindow()

    def open_metrics() -> None:
        if metrics_win["w"] is None:
            metrics_win["w"] = MetricsDialog()
        w = metrics_win["w"]
        w.reload()
        w.show()
        w.raise_()
        w.activateWindow()

    def open_dictionary() -> None:
        try:
            dlg = DictionaryDialog(app.cfg)
            if dlg.exec() == DictionaryDialog.DialogCode.Accepted:
                app.apply_config(dlg.result_config())
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(None, "MaxVoice Dictionary", f"{type(e).__name__}: {e}")

    tray.act_settings.triggered.connect(open_settings)
    tray.act_history.triggered.connect(open_history)
    tray.act_metrics.triggered.connect(open_metrics)
    tray.act_dictionary.triggered.connect(open_dictionary)
    tray.act_quit.triggered.connect(qapp.quit)

    app.start()
    qapp.aboutToQuit.connect(app.stop)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

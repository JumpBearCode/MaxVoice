import sys

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from .app import App
from .gui.history import HistoryDialog
from .gui.settings import SettingsDialog
from .gui.tray import Tray


def main() -> int:
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

    # History window is cached so it can stay open; Settings is modal, one-shot.
    history_win: dict = {"w": None}

    def open_settings() -> None:
        dlg = SettingsDialog(app.cfg)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            app.apply_config(dlg.result_config())

    def open_history() -> None:
        if history_win["w"] is None:
            history_win["w"] = HistoryDialog()
        w = history_win["w"]
        w.reload()
        w.show()
        w.raise_()
        w.activateWindow()

    tray.act_settings.triggered.connect(open_settings)
    tray.act_history.triggered.connect(open_history)
    tray.act_quit.triggered.connect(qapp.quit)

    app.start()
    qapp.aboutToQuit.connect(app.stop)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())

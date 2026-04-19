from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from . import icons


class Tray(QSystemTrayIcon):
    def __init__(self, parent=None) -> None:
        super().__init__(icons.idle_icon(), parent)
        self.setToolTip("MaxVoice — idle")
        self.menu = QMenu()
        self.act_status = self.menu.addAction("Idle")
        self.act_status.setEnabled(False)
        self.menu.addSeparator()
        self.act_settings = self.menu.addAction("Settings…")
        self.act_history = self.menu.addAction("History…")
        self.act_metrics = self.menu.addAction("Metrics…")
        self.act_dictionary = self.menu.addAction("Dictionary…")
        self.menu.addSeparator()
        self.act_quit = self.menu.addAction("Quit")
        self.setContextMenu(self.menu)

    def set_state(self, state: str) -> None:
        if state == "recording":
            self.setIcon(icons.recording_icon())
            self.setToolTip("MaxVoice — recording")
            self.act_status.setText("● Recording")
        elif state == "transcribing":
            self.setIcon(icons.transcribing_icon())
            self.setToolTip("MaxVoice — transcribing")
            self.act_status.setText("Transcribing…")
        else:
            self.setIcon(icons.idle_icon())
            self.setToolTip("MaxVoice — idle")
            self.act_status.setText("Idle")

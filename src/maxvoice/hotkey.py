from collections.abc import Callable

from pynput import keyboard


class HotkeyListener:
    """Toggle-mode global hotkey. First press fires the callback with True,
    the next press fires it with False. pynput handles key parsing."""

    def __init__(self, hotkey: str, on_toggle: Callable[[bool], None]) -> None:
        self._hotkey_str = hotkey
        self._on_toggle = on_toggle
        self._listener: keyboard.GlobalHotKeys | None = None
        self._active = False

    def _fire(self) -> None:
        self._active = not self._active
        print(f"[hotkey] fired — active={self._active}", flush=True)
        try:
            self._on_toggle(self._active)
        except Exception as e:
            print(f"[hotkey] callback error: {e}", flush=True)

    def start(self) -> None:
        self.stop()
        print(f"[hotkey] starting listener with combo: {self._hotkey_str!r}", flush=True)
        self._listener = keyboard.GlobalHotKeys({self._hotkey_str: self._fire})
        self._listener.start()
        print("[hotkey] listener started", flush=True)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def update(self, hotkey: str) -> None:
        self._hotkey_str = hotkey
        self.start()

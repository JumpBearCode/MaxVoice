from collections.abc import Callable

from pynput import keyboard


class HotkeyListener:
    """Toggle-mode global hotkey listener supporting multiple bindings.

    Accepts a {combo_string: mode_name} map. First press of any combo starts
    that mode (fires on_toggle(mode, True)); next press of the SAME combo stops
    it (fires on_toggle(mode, False)). Presses of a different combo while a
    mode is already active are ignored — the recorder can only be in one state,
    so trying to start a second mode mid-recording would be a bug trap.
    """

    def __init__(
        self,
        hotkeys: dict[str, str],
        on_toggle: Callable[[str, bool], None],
    ) -> None:
        self._hotkeys: dict[str, str] = dict(hotkeys)
        self._on_toggle = on_toggle
        self._listener: keyboard.GlobalHotKeys | None = None
        self._active_mode: str | None = None

    def _fire(self, mode: str) -> None:
        if self._active_mode is None:
            self._active_mode = mode
            active = True
        elif self._active_mode == mode:
            self._active_mode = None
            active = False
        else:
            print(
                f"[hotkey] ignoring {mode!r} press — "
                f"{self._active_mode!r} is already active",
                flush=True,
            )
            return
        print(f"[hotkey] fired mode={mode!r} active={active}", flush=True)
        try:
            self._on_toggle(mode, active)
        except Exception as e:
            print(f"[hotkey] callback error: {e}", flush=True)

    def start(self) -> None:
        self.stop()
        print(
            f"[hotkey] starting listener with combos: {self._hotkeys!r}",
            flush=True,
        )
        # Bind each combo to a closure that captures its own mode — a plain
        # lambda in the loop would close over the last mode for every entry.
        bindings = {
            combo: (lambda m=mode: self._fire(m))
            for combo, mode in self._hotkeys.items()
        }
        self._listener = keyboard.GlobalHotKeys(bindings)
        self._listener.start()
        print("[hotkey] listener started", flush=True)

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def update(self, hotkeys: dict[str, str]) -> None:
        # Restarting the pynput listener tears down + reinstalls a CGEventTap on
        # macOS, which races with Qt's event loop and crashes the process. Skip
        # the restart when the combos haven't actually changed.
        new = dict(hotkeys)
        if new == self._hotkeys and self._listener is not None:
            return
        self._hotkeys = new
        self.start()

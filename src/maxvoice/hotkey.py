from collections.abc import Callable

from AppKit import (
    NSEvent,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagOption,
    NSEventModifierFlagShift,
)

# Only the four user-facing modifiers count for hotkey matching. Caps Lock,
# numeric-pad, function, and help bits in modifierFlags() must be masked out
# or the same combo with Caps Lock on/off would compare as different.
_RELEVANT_MODS = (
    NSEventModifierFlagCommand
    | NSEventModifierFlagControl
    | NSEventModifierFlagOption
    | NSEventModifierFlagShift
)

_TOKEN_TO_MOD = {
    "<cmd>": NSEventModifierFlagCommand,
    "<ctrl>": NSEventModifierFlagControl,
    "<alt>": NSEventModifierFlagOption,
    "<shift>": NSEventModifierFlagShift,
}

# macOS virtual key codes for keys whose `charactersIgnoringModifiers` is
# either non-printable or layout-dependent. Letters/digits go through the
# character-comparison path instead.
_TOKEN_TO_KEYCODE = {
    "<space>": 49,
    "<tab>": 48,
    "<enter>": 36,
    "<return>": 36,
    "<esc>": 53,
    "<f1>": 122, "<f2>": 120, "<f3>": 99,  "<f4>": 118,
    "<f5>": 96,  "<f6>": 97,  "<f7>": 98,  "<f8>": 100,
    "<f9>": 101, "<f10>": 109, "<f11>": 103, "<f12>": 111,
    "<f13>": 105, "<f14>": 107, "<f15>": 113, "<f16>": 106,
    "<f17>": 64,  "<f18>": 79,  "<f19>": 80,  "<f20>": 90,
}


def _parse_combo(combo: str) -> tuple[int, str | None, int | None] | None:
    """Parse '<ctrl>+<alt>+q' → (modifier_mask, char_or_None, keycode_or_None).

    Returns None if the combo is unparseable. Exactly one of `char` /
    `keycode` will be set (the actual key); the other is None.
    """
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    char: str | None = None
    keycode: int | None = None
    for p in parts:
        token = p.lower()
        if token in _TOKEN_TO_MOD:
            mods |= _TOKEN_TO_MOD[token]
        elif token in _TOKEN_TO_KEYCODE:
            keycode = _TOKEN_TO_KEYCODE[token]
        elif len(p) == 1:
            char = p.lower()
        else:
            return None
    if char is None and keycode is None:
        return None
    return (mods, char, keycode)


class HotkeyListener:
    """Toggle-mode global hotkey listener using Cocoa NSEvent monitors.

    Uses NSEvent global + local monitors (handlers fire on the main thread)
    instead of pynput's CGEventTap on a background thread. This avoids two
    macOS-specific crashes pynput hit:
      1. TSM (`TISIsDesignatedRomanModeCapsLockSwitchAllowed`) asserting
         dispatch_assert_queue when Caps Lock fires the tap callback off
         the main thread — happened any time a Cocoa text input client was
         active in the process (e.g. while a Qt dialog was open).
      2. CGEventTap teardown/reinstall racing the Qt event loop on
         hotkey reconfiguration.

    Public API matches the previous pynput-backed implementation.
    """

    def __init__(
        self,
        hotkeys: dict[str, str],
        on_toggle: Callable[[str, bool], None],
    ) -> None:
        self._hotkeys: dict[str, str] = dict(hotkeys)
        self._on_toggle = on_toggle
        self._active_mode: str | None = None
        self._global_token = None
        self._local_token = None
        self._parsed: list[tuple[int, str | None, int | None, str]] = []
        self._reparse()

    def _reparse(self) -> None:
        self._parsed = []
        for combo, mode in self._hotkeys.items():
            parsed = _parse_combo(combo)
            if parsed is None:
                print(f"[hotkey] cannot parse combo {combo!r} — skipped", flush=True)
                continue
            mods, char, keycode = parsed
            self._parsed.append((mods, char, keycode, mode))

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

    def _match(self, event) -> str | None:
        if event.isARepeat():
            return None
        ev_mods = int(event.modifierFlags()) & _RELEVANT_MODS
        ev_chars = (event.charactersIgnoringModifiers() or "").lower()
        ev_keycode = int(event.keyCode())
        for mods, char, keycode, mode in self._parsed:
            if mods != ev_mods:
                continue
            if keycode is not None and ev_keycode == keycode:
                return mode
            if char is not None and ev_chars == char:
                return mode
        return None

    def _global_handler(self, event) -> None:
        mode = self._match(event)
        if mode:
            self._fire(mode)

    def _local_handler(self, event):
        mode = self._match(event)
        if mode:
            self._fire(mode)
        # Pass through so the focused widget still sees the key — matches
        # pynput behavior, avoids surprising "my hotkey ate my keystroke" UX.
        return event

    def start(self) -> None:
        self.stop()
        if not self._parsed:
            print("[hotkey] no parseable combos — not installing monitors", flush=True)
            return
        print(
            f"[hotkey] installing NSEvent monitors for combos: {self._hotkeys!r}",
            flush=True,
        )
        self._global_token = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, self._global_handler
        )
        self._local_token = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, self._local_handler
        )
        if self._global_token is None:
            # macOS silently returns nil here when the process lacks
            # Accessibility permission. Local monitor still works (only when
            # MaxVoice is focused), but the user expects global hotkeys.
            print(
                "[hotkey] WARNING: global monitor returned nil — Accessibility "
                "permission likely missing. Grant it to your terminal in "
                "System Settings → Privacy & Security → Accessibility, then "
                "restart MaxVoice.",
                flush=True,
            )
        else:
            print("[hotkey] monitors installed", flush=True)

    def stop(self) -> None:
        if self._global_token is not None:
            NSEvent.removeMonitor_(self._global_token)
            self._global_token = None
        if self._local_token is not None:
            NSEvent.removeMonitor_(self._local_token)
            self._local_token = None

    def update(self, hotkeys: dict[str, str]) -> None:
        # Cheap short-circuit: nothing to do if combos are unchanged.
        # NSEvent add/remove is main-thread and safe to repeat, so this
        # is a perf optimization rather than a crash guard.
        new = dict(hotkeys)
        if new == self._hotkeys and self._global_token is not None:
            return
        self._hotkeys = new
        self._reparse()
        self.start()

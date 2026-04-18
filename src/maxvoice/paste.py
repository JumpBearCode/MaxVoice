import time

import pyperclip


def deliver(text: str, auto_paste: bool) -> bool:
    """Put text in clipboard; if auto_paste, also simulate Cmd+V.
    Returns True if auto-paste was attempted."""
    pyperclip.copy(text)
    if not auto_paste:
        return False
    # Import lazily: pyautogui has a heavy import cost on macOS.
    try:
        import pyautogui

        time.sleep(0.05)
        pyautogui.hotkey("command", "v")
        return True
    except Exception as e:
        print(f"[paste] auto-paste failed, text kept in clipboard: {e}")
        return False

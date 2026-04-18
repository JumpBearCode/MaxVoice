# MaxVoice

Typeless-like voice dictation, powered by **Azure AI Foundry**. Press a hotkey,
speak, press again to stop — the transcription lands at your cursor.

- **Pluggable STT** (layer 1): `gpt-4o-mini-transcribe` (default), `gpt-4o-transcribe`
- **Pluggable refinement** (layer 2): `gpt-5.4-nano` (default), `gpt-5.4-mini`, `claude-haiku-4-5`
- **Toggle hotkey** (default `Right-Option + Q`, configurable in Settings)
- **No length cap** — streams audio until you press the hotkey again
- **SQLite history** with productivity estimate (time saved vs typing)
- **Auto-paste** to cursor, or falls back to clipboard

> **On model names**: as of April 2026 there is no `gpt-5.4-transcribe` — OpenAI's
> audio line stays under the `gpt-4o-*-transcribe` name, and the Dec 2025 version
> is SOTA. Text refinement uses the GPT-5.4 family.

## Setup

```bash
git clone <this-repo>
cd maxvoice
cp .env.example .env   # fill in Azure endpoint, key, deployment names
uv sync
uv run maxvoice
```

The tray icon appears in the menu bar. Use **Settings** to change the hotkey
and models, **History** to browse past recordings and see total time saved.

## Azure setup

In Azure AI Foundry, create deployments for the models you want and put the
deployment names in `.env`. You only need deployments for the models you plan
to use — if you skip one, just don't select it in Settings.

## macOS permissions

macOS will prompt for:
- **Microphone** — for recording
- **Accessibility** — so `pynput` can listen for global hotkeys and
  `pyautogui` can simulate `Cmd+V`

Grant both in *System Settings → Privacy & Security*.

## Data

Everything lives under `~/Library/Application Support/maxvoice/`:
- `audio/*.wav` — raw recordings
- `maxvoice.db` — SQLite history
- `config.json` — user preferences (hotkey, models, WPM)

## Project layout

```
src/maxvoice/
├── __main__.py          # uv run entry point
├── app.py               # coordinator (hotkey → record → STT → refine → paste → db)
├── config.py            # .env + config.json
├── recorder.py          # sounddevice streaming, no length cap
├── hotkey.py            # pynput global toggle hotkey
├── paste.py             # Cmd+V simulation / clipboard fallback
├── db.py                # SQLite + productivity estimate
├── stt/                 # pluggable STT providers
│   ├── base.py
│   ├── azure_openai.py  # gpt-4o-transcribe, gpt-4o-mini-transcribe
│   └── registry.py
├── refine/              # pluggable refinement providers
│   ├── base.py
│   ├── azure_chat.py    # GPT-5.4-nano/mini, Claude Haiku 4.5 (via Foundry)
│   └── registry.py
└── gui/
    ├── tray.py
    ├── settings.py
    ├── history.py
    └── hotkey_edit.py
```

## Adding a new provider

Subclass `STTProvider` or `RefineProvider`, then add to the respective
`registry.py`. It will appear in the Settings dropdown automatically.

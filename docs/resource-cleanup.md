# Resource Cleanup in MaxVoice

A tour of how resources (files, sockets, threads, memory, native handles) are
released during normal use and shutdown. Written in plain language for future
reference; no deep Qt / Python GC knowledge assumed.

## Three cleanup tiers

Every resource the app allocates falls into one of three tiers based on *when*
it gets released:

| Tier | Meaning | Analogy |
|------|---------|---------|
| **A** | Released synchronously the moment we're done with it | You wash your dish right after eating |
| **B** | Released eventually when Python's garbage collector runs | A waiter clears the table a few minutes after you leave |
| **C** | Released only when the process exits | The cleaning crew sweeps the whole restaurant at closing time |

Tier A is the tightest. Tier B is fine as long as GC runs often enough (it
usually does — within seconds). Tier C is only acceptable when the resource is
cheap and you *want* it to live for the app's whole life.

**MaxVoice does not spawn subprocesses, so tier C is a clean sweep** — when
the Python process dies, macOS reclaims every fd, socket, thread, and memory
page we allocated. Nothing survives as orphaned child processes.

## Current classification

### Tier A (synchronous, clean)

| Resource | How it's released |
|----------|-------------------|
| WAV file write (recorder) | `with wave.open(...)` — closed when the block exits |
| WAV file read (STT upload) | `with audio_path.open("rb")` |
| SQLAlchemy session | `with Session(engine())` — commits/rollbacks + closes cursor |
| `sounddevice` InputStream | `recorder.stop()` explicitly calls `.stop()` + `.close()` |
| pynput GlobalHotKeys listener thread | `hotkey.stop()` on `App.stop()` (wired to `QApplication.aboutToQuit`) |

These are the resources that would *actually* cause problems if leaked — open
fds accumulating, audio device locked, DB locked, etc. All of them are
deterministically released.

### Tier B (deferred, waiting on Python GC)

Each of these is an "accidental B" — fixable without losing anything, but the
cost of leaving it alone is invisible in practice.

#### 1. Old `TranscribeWorker` (`QThread`) Python objects

Each recording creates a new `TranscribeWorker`:
```python
self._worker = TranscribeWorker(audio_path, duration, audio, self.cfg)
```
The assignment drops the reference to the previous worker. Its OS thread has
already exited (its `run()` returned before we got here), but the Python
wrapper object + PyQt's C++ `QThread` object linger until GC.

**Impact**: a few KB of Python + C++ state per stale worker. GC reclaims them
within seconds.

**Upgrade path (→ A)**:
```python
self._worker.finished.connect(self._worker.deleteLater)
```
One line. Tells Qt to destroy the C++ `QThread` object as soon as its event
loop finishes. The Python wrapper still waits on GC, but the expensive native
bits release immediately.

#### 2. `httpx.Client` inside Azure OpenAI SDK calls

`stt/azure_openai.py::_client()` and `refine/azure_chat.py::_client()` both
return a fresh `AzureOpenAI(...)` per call. Each instance wraps an internal
`httpx.Client` with a connection pool. When the outer function returns, the
`AzureOpenAI` object is unreferenced; its `__del__` eventually closes the
httpx client, which eventually closes the pooled TCP sockets.

**Symptom**: after a few calls, `lsof -p <pid>` shows a handful of TCP fds in
`CLOSED` state — the kernel has torn down the sockets, but Python hasn't
reaped the fd entries yet. Harmless, but it's how you can *see* the lag.

**Upgrade path (→ A)**:
```python
with _client() as client:
    resp = client.audio.transcriptions.create(...)
```
Context manager closes the httpx client (and its connection pool) at block
exit. TCP fds are released immediately.

#### 3. Signal/slot connections on stale workers

When we do `self._worker.finished_ok.connect(self._on_transcription)`, Qt
records a connection between the worker object and the App slot. If the
worker is replaced before GC, the old connection sits there until the old
worker object is destroyed.

**Impact**: purely logical — there is no double-fire risk, because the old
worker's `run()` has already returned and it can't emit again.

**Upgrade path (→ A)**: fixed for free by (1). `deleteLater` detaches the
connection when Qt destroys the object.

#### 4. numpy audio buffer inside a worker

The worker holds `self.audio` (the int16 mono array handed over from the
recorder). A typical 30-second recording is ~1 MB. The buffer is only
released when the worker object itself is GC'd — same lifecycle as (1).

**Upgrade path (→ A)**: either fixed by (1), or set `self.audio = None` at
the end of `run()`.

### Tier B/C (deliberate — keeping these around is a feature)

| Resource | Lifetime | Why not A |
|----------|----------|-----------|
| **SQLAlchemy `engine`** (`db._engine`) | Whole process | It *is* the connection pool. Recreating it per request loses the pool and makes every write ~10× slower. SQLite handles cleanup at process exit. |
| **Silero VAD ONNX model + onnxruntime session** | Whole process | Model load is ~200–500 ms. Reloading per recording would add half a second of latency to every dictation. Keeping it cached makes VAD basically free after the first run. Peak cost: ~15 MB RAM. |
| **PyQt6 singleton objects** (tray icon, main window, hotkey bridge) | Whole process | These literally represent the app's UI and event routing — they must live as long as the app does. |

These are tier C *on purpose*. Performance or correctness requires the
resource to stick around; process exit is a clean enough sweep for any of
them because they're all in-process state.

### Tier C (safety net — not a plan)

If the app crashes mid-recording, whatever tier A cleanup we normally do
doesn't run. In that case:

- PortAudio audio stream → closed by the OS (the audio device gets released)
- SQLite DB → WAL file may be left behind, SQLite recovers on next open
- In-flight HTTP requests → TCP connections reset by the kernel
- WAV file currently being written → may be truncated; next run ignores it

Nothing leaks to persistent state. The worst case is losing the current
in-progress recording.

## Summary of what would actually help

Three changes totalling ~5 lines of code, zero behavior change, moves the
remaining "accidental B" resources to tier A:

1. `self._worker.finished.connect(self._worker.deleteLater)` in `App._stop_recording`
2. `with _client() as client:` in both `_AzureTranscribe.transcribe` and `_AzureChatRefine._complete`
3. (Optional) `self.audio = None` at the end of `TranscribeWorker.run`

After these, the only tier-B/C resources left are the deliberate ones
(engine, VAD model, UI singletons) that would hurt the app to change.

## What not to do

- **Don't** rebuild the SQLAlchemy engine per request. It is a pool, not a
  connection; burning it every time makes SQLite writes an order of magnitude
  slower.
- **Don't** reload the Silero VAD model per recording. First-run latency is
  acceptable; per-recording latency is not.
- **Don't** try to gc.collect() on a schedule. Python's GC is already tuned
  for our workload. Forcing it doesn't help and can introduce pauses.

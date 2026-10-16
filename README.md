# SIDHU AI

A real Windows assistant MVP built with Python and PySide6. This repository is the first functional slice of the supplied master specification, **not the complete seven-phase product**. No celebrity voice, likeness or pretrained custom wake-word model is bundled. An optional original procedural 3D character is included; it is not a realistic licensed likeness.

## Windows 10/11 quick start

Install 64-bit Python 3.12 from python.org, then run in this repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[desktop,dev]'
.\.venv\Scripts\python.exe -m sidhu.app
```

The default state is microphone muted and memory disabled. Open Settings to configure your microphone index, extracted Vosk model directory, installed Windows voice ID, allowed applications, approved search folders and optional AI model. Use **List microphone devices** to find the index. Download an appropriate model from the official https://alphacephei.com/vosk/models page and extract it locally; model downloads are deliberately not automatic. Review each model's license. English/Hindi recognition depends on the selected model. Punjabi availability and Hinglish accuracy are not verified; do not assume a single Vosk model supports all four languages. Wake recognition depends on that model transcribing Sidhu correctly. This MVP runs continuous local ASR with a wake-phrase gate, not an optimized dedicated wake-word detector.

Enable the microphone, say “Hey Sidhu”, pause for the ready status, then say “open Chrome”. Alternatively say “Hey Sidhu open Chrome” in one utterance. The local follow-up window defaults to 12 seconds and is configurable. Audio is not saved or uploaded. Explicit AI chat sends your typed/spoken question to the configured endpoint only when you use `ask`.

Windows Settings → Privacy → Microphone must permit desktop application access. No administrator access is needed. The selected audio device must support mono 16 kHz capture; unsupported devices report an error. No custom denoiser is included. Vosk supplies recognition endpointing. After recoverable stream errors the listener retries up to three times, then exposes the failure. The Enable/mute control closes capture before acknowledging mute. The model remains loaded until the listener exits.

## Commands implemented

- `open Chrome`, `Chrome kholo`, `क्रोम खोलो`, `ਕ੍ਰੋਮ ਖੋਲ` (text intent support; speech depends on model).
- `open Edge`, `open Explorer`, `open Notepad` — only enabled fixed applications, no shell commands.
- `open https://example.com` — dispatches to the default Windows browser; does not verify the loaded page.
- `diagnostics`, `performance check`, `battery` — actual psutil readings; no invented sensors or diagnoses.
- `volume 50` — Windows master endpoint volume, with readback.
- `latest PDF`, `find report` — returns matching filenames inside explicitly approved folders, newest first. Search never opens or executes a file and caps traversal at 20,000 file/directory entries.
- `remember <note>`, `memories` — explicit local SQLite notes, only when memory is enabled. Delete notes using Settings with confirmation.
- `ask <question>` — OpenAI-compatible chat, no tool execution. Set a model and base URL in Settings. Default local endpoint is `http://localhost:11434/v1` for an independently installed Ollama server. For cloud services, use HTTPS and supply the key through the named environment variable before launching. Never paste keys into the settings file or a prompt.
- `help`, `cancel` — cancellation can stop a file search and discard an AI response. The dashboard Stop speech / cancel task control also terminates speech output and clears queued utterances. Cancellation cannot undo app dispatch or abort an in-flight HTTP request; AI requests use 30-second I/O timeouts and elapsed-time checks between response chunks; a blocked read can delay cancellation or the elapsed cutoff by another I/O interval.

The GUI rejects additional tasks while a task is active. Specialization is currently deterministic routing to Windows, Files, Diagnostics, Memory, Browser dispatch and AI chat handlers. It is not yet an autonomous multi-agent planner or a coding agent.

## Tray, startup, privacy and power

Closing the dashboard hides it to the tray on a system with tray support. It does not exit or mute the listener. The tray provides Open, Enable/mute microphone and Exit. Exit shuts down capture. Without tray support, closing exits. Enable **Start in tray at Windows sign-in** in Settings to register a per-user Run entry using `--supervise --background`; it launches without a developer terminal. Startup listening is attempted only at sign-in; missing models/devices report unavailable. Disable startup in Settings to remove the Run entry. The installer removes that entry on uninstall. Development startup uses the environment's `pythonw.exe`; keep the repository and virtual environment at their installed paths. Packaged startup uses the installed executable.

Normal foreground launches begin muted; a configured sign-in background launch attempts listening. TTS uses installed system voices, with adjustable rate. A Punjabi-accented male voice is not guaranteed by Windows defaults. There is no voice cloning. Listening is suppressed during speech to prevent self-triggering. **Spoken barge-in and lip sync are not implemented.** Use Stop speech / cancel task to interrupt speech. TTS runs in an isolated spawned process so a blocked audio driver can be terminated without stopping the assistant. Each utterance starts a fresh worker, adding startup latency; no low-latency claim has been measured on Windows. Speech is capped at 120 seconds per utterance. Output failure is shown separately from microphone status.

The app cannot listen during shutdown, hibernation or sleep. Locked-session microphone availability depends on Windows policy, device and session; untested here. Optional power behavior: with your consent, use Windows Settings → System → Power to set plugged-in screen timeout separately from sleep, allowing screen-off while awake. SIDHU never changes power or security policies itself.

Local settings and opt-in notes live under `%LOCALAPPDATA%\SidhuAI`. The conversation shown in the dashboard stays in memory and is not logged to disk. Disabling memory prevents note reads/writes but does not erase existing notes; use Delete notes to remove them. API credentials are read from the named environment variable and are not saved in SQLite/settings. Cloud prompts go to the selected provider under its own data policy.

## Test and package

```powershell
.\.venv\Scripts\python.exe -m pytest
powershell -ExecutionPolicy RemoteSigned -File installer\build.ps1
# With Inno Setup 6 installed:
ISCC installer\sidhu.iss
```

The build script produces `dist\SidhuAI\SidhuAI.exe` and fails on dependency, test or packaging errors. The Inno recipe creates a per-user installer. Builds are not signed. Packaging and installer operation require Windows validation; no working Windows binary is claimed from Linux. Dependency ranges are bounded but not hash-locked; exact build reproducibility remains release work.

For non-desktop development on Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest
SIDHU_DATA_DIR=/workspace/scratch/sidhu-data .venv/bin/python -m sidhu.app --command diagnostics
```

See [capability and acceptance status](documentation/ACCEPTANCE.md). The full requested realistic character and phoneme lip sync, browser form/click automation, continuous/window-specific screen understanding, software-development tools, advanced workflow scheduling, productivity integrations and advanced background-service capabilities remain future work. They are not represented by simulated results.

The `SIDHU_DATA_DIR` override above is for this cloud workspace; on a normal Linux machine you can omit it to use `$XDG_DATA_HOME/SidhuAI` (or `~/.local/share/SidhuAI`). It can also override the data location on Windows. The original full specification is preserved in [MASTER_SPEC.md](documentation/MASTER_SPEC.md).

## Windows build automation

`.github/workflows/windows.yml` runs the tests, builds the windowed application, compiles the Inno Setup installer and uploads unsigned artifacts on pull requests, pushes to main or manual dispatch. The workflow is provided as source only: it has not been pushed or run from this cloud session. A successful CI build would still not validate microphone hardware, acoustic accuracy, sign-in behavior or install/uninstall on the Acer.

## Browser inspection

Install the optional browser integration in development:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[browser]'
.\.venv\Scripts\python.exe -m playwright install chromium
```

In Settings enable browser inspection and enter exact approved hostnames, for example `example.com,www.example.com`. Then run `inspect https://example.com`. You can configure an existing compatible Chromium/Chrome executable instead of installing Playwright's browser. Packaged builds include Playwright's driver but do not bundle a browser: configure an installed compatible Chrome/Chromium executable. The system default browser is separate from this inspection browser.

Inspection uses a new headless context without your saved login, verifies the HTTP response, then reads the final URL, title, rendered body text (up to 8,000 characters) and link count. It reports HTTP errors and closes the browser afterward. It waits for DOMContentLoaded, not every asynchronously loaded element, and does not diagnose a whole website from one page. TLS verification and Chromium's sandbox remain enabled. Every routed request requires an approved HTTPS hostname and GET/HEAD; third-party hosts, other methods, WebSockets, service workers and download acceptance are blocked. Redirect destinations must also be approved. Browser traffic necessarily contacts the approved site. Page text is shown as untrusted content and cannot invoke tools or become a workflow. Cancellation checks occur before and after navigation; navigation can take up to its 15-second timeout, followed by bounded extraction operations.

**Cloud limitation:** this host's system Chromium failed sandbox initialization because its sandbox helper is not root-owned and the host prevents user-namespace setup. Browser inspection remains unverified in a real browser here. The application reports this failure and keeps sandboxing enabled. Policy/navigation tests use controlled test doubles and do not prove browser execution. A supported Windows environment must run the browser acceptance checks below.

## Saved workflows

Open **Workflows** to create or edit a JSON object, for example:

```json
{
  "work setup": ["open Chrome", "open https://example.com", "diagnostics"]
}
```

Save, then type or speak `run workflow work setup` after activation. `workflows` lists saved names. Workflows persist locally in the settings file independently of conversational memory. Remove a name in the editor to delete a workflow.

Each workflow contains 1–10 commands; at most 30 workflows are supported. Only `open`, `inspect`, `find`, `volume`, `diagnostics`, `battery`, `latest PDF`, `read`, `search text`, `recent files`, `duplicates`, `document`, `summarize file` and `analyze csv` steps are accepted. These use the same application allowlists and approved domains/folders as direct commands. No AI-generated plan, shell, recursive workflow, note write, payment or external message tool is available through workflows. Steps run sequentially, show progress, stop on failure and preserve cancellation between steps. Dispatched actions cannot be rolled back; a workflow completion retains each step's dispatch/verification limitations. There is no scheduler or parallel planner yet.

## File and document tools

These tools operate only in the existing approved folders configured in Settings; no filesystem writes, moves, renames or deletes are performed:

- `read report.txt` or `read "C:\Users\YourName\Downloads\report.txt"`: preview a UTF-8 plain-text file. Relative paths resolve against approved roots; duplicate filenames across roots require an exact path. Supported types include text, Markdown, code, CSV, JSON, logs and common configuration formats. This plain-text command does not parse PDF or Office files; use the optional document command below for PDF text. Previews read at most 2 MiB and display at most 12,000 characters.
- `search text project deadline`: case-insensitive content search in supported text files, returning the first matching line per file. Stops at 20 matches or a 20 MiB candidate-file budget and identifies partial results. Unreadable, oversized or invalid-encoding files are skipped and counted.
- `recent files`: shows the 20 most recently modified files from approved roots.
- `duplicates`: groups same-size files using SHA-256 hashes, detects changes during hashing and never removes files. Hashing has a 256 MiB read budget; exceeding it reports an incomplete scan rather than a successful full report.

All scans are cancellable and bounded at 20,000 file/directory entries. Symlinks and paths resolving outside an approved root are excluded. These limits prevent an unbounded scan; they do not replace the operating system's file permissions or provide a hardened sandbox against a hostile local process modifying folders concurrently. File content is displayed as untrusted text and never becomes a command or AI prompt automatically. These commands may also be used as saved workflow steps.

## Memory management

Enable explicit note memory in Settings, save a note with `remember <text>`, then open **Memory**. Search, select and edit notes, delete a selected note with confirmation, or export all notes to a new JSON file. Exports never overwrite an existing path and are separate unencrypted files. The editor uses the real SQLite database and changes survive restart. When memory is disabled the editor does not open/read notes; existing data is retained until explicitly deleted. Delete-all remains available in Settings. SQLite connections close after every operation so the database is not held open unnecessarily.

## Original 3D character

Settings → **Enable original procedural 3D avatar**, then restart the desktop app. Keep **Reduce animations** off to use 3D. The native Qt Quick 3D scene builds an original stylized Punjabi male bust from procedural geometry: layered turban, beard, eyes, clothing and lighting. It is a geometric starting character, not a realistic sculpt or an artist likeness. No downloaded/licensed character asset is represented as bundled.

Actual voice/task lifecycle state is bound into the scene. Idle head movement and blinking run only while the scene is visible. Mouth pulses respond to word-start events from the active system TTS driver; drivers that do not produce word callbacks will not animate the mouth. This is word-driven mouth movement, **not phoneme/viseme lip sync**. There is no microphone-reactive face tracking. Speech cancellation clears the speaking state and closes the mouth. No voice or likeness of Sidhu Moose Wala is provided.

3D requires a supported Qt RHI graphics backend and suitable GPU/driver. The app defaults to the lightweight animated core; enabling 3D is optional. Software-only Qt backends fall back to the core with a visible explanation. QML/scene-graph errors also select the fallback when Qt can report them. Incompatible drivers that crash Qt itself cannot be recovered inside the process: restart with `avatar_enabled` set to `false` in the local settings file. Rendering quality, appearance and resource usage must be verified on the Acer; no GPU benchmark or 60 FPS claim has been made.

Cloud validation instantiated the actual QML scene and checked its state bindings. A rendering attempt confirmed this host only offers the software scene graph, which cannot display Qt Quick 3D. The fallback was added and tested. The character's GPU-rendered appearance and audible word synchronization remain unverified.

## Local tasks and reminders

Enable **local tasks and reminders** in Settings, then use the **Productivity** panel or these typed/spoken commands:

- `task add Review the project` — saves a task locally.
- `tasks` — lists up to 200 tasks, open first.
- `task done 1` / `task reopen 1` — changes completion state.
- `remind in 10 minutes Take a break` — saves a reminder with a relative delay of 1–525,600 minutes.
- `reminders` — lists up to 200 reminders with due times in the laptop's local timezone and pending/cancelled/dispatched state.
- `cancel reminder 1` — cancels a pending reminder.

The Productivity panel includes task completion/reopening, reminder creation/cancellation, Refresh and confirmed Delete all. These controls operate on the real local database. Tasks/reminders are stored separately from conversational notes in `productivity.sqlite3` under the configured SIDHU data directory. Disabled productivity does not create/read/update its database or dispatch reminders. Disabling it retains existing records; enable it again to manage or delete them. Notes' memory opt-in and productivity opt-in are independent. Each table is capped at 10,000 records; delete-all is available if you reach that bound.

The desktop checks for due reminders once per second, up to 20 per pass, including while hidden in the tray. A timer is not started by the one-command CLI. It requests a tray notification when available; otherwise it shows the reminder in the dashboard. Windows Focus Assist and notification settings can suppress tray notifications. **Dispatched** means SIDHU submitted the notification/display request, not that a person received or read it. Due items are marked dispatched only after the request succeeds; failed attempts remain pending for retry. If a crash occurs after display but before the database update, the reminder can repeat after restart. This is not an exactly-once delivery guarantee.

No reminders run while SIDHU is exited or the laptop is asleep, powered off or hibernating. Overdue pending reminders are checked when the enabled desktop next runs. Use the existing opt-in Windows sign-in startup if desired. Clock/timezone changes can affect when reminders appear. Reminder text is data only: it never executes a command, opens an application, sends a message or triggers a saved workflow. No calendar account, email service or external scheduler is integrated.

## Hardware diagnostics and process inventory

`hardware` returns a structured JSON report from the current machine: OS/Python details, CPU core counts and usage, memory, system-volume storage, battery, temperature sensors and Windows GPU inventory where available. Missing/denied sensors are explicitly unavailable. Windows video adapters are queried with a fixed read-only `Get-CimInstance Win32_VideoController` command and a five-second timeout. The OS-reported AdapterRAM field can underreport large VRAM; it is not treated as measured dedicated GPU memory. This does not choose or load an AI model automatically and does not assume an NVIDIA GPU or 16 GB of RAM.

`processes` lists up to 10 processes ranked by resident memory, with PID, executable name, status, resident bytes and accumulated CPU seconds. It does not report instantaneous per-process CPU percentage, command lines, environment variables or usernames. The scan is bounded and records inaccessible/exited processes. It never terminates a process or changes its priority. These reports do not determine why a laptop is slow by themselves.

The cloud verification checks describe the cloud host, not your Acer. Windows GPU inventory and real laptop readings remain acceptance work.

## Activity history and measured duration

Enable **Store activity metadata** in Settings to retain the last 500 top-level command executions in a separate local `activity.sqlite3` file. **Activity** and the `history` command show up to 200 recent records with UTC time, a fixed operation label, agent, success/failure and measured milliseconds. Compound workflow steps retain their normal progress transcript; the history records the top-level workflow. The history stores no command arguments, paths, prompts, notes, API keys, file/webpage content, responses or exception text. Unrecognized input is labeled `other command`. SQLite metadata is not encrypted. Disable history to prevent reads/writes while retaining old records; enable it again and use confirmed **Delete all** to erase them.

Command results and the dashboard now include measured execution time. It covers routing/tool execution and excludes microphone recognition, TTS, history persistence and user-perceived end-to-end delay. This measurement is not a wake-to-action latency benchmark. If metadata persistence fails, the original tool result is preserved and a separate warning appears.

## Command-routing and audio reliability corrections

Application and website dispatch require a complete supported command. Ambiguous compound input such as `open Chrome and Notepad` is rejected without launching either app. Use a saved workflow for a supported multi-step sequence. Filename queries such as `find cpu-report` and `find open-chrome-report` remain filename searches. `latest PDF` uses the exact `.pdf` suffix. File scan cancellation is checked during directory traversal, including empty directories, and both files and directories count toward the scan budget.

The listener drops recognition completed after mute or speech begins. The desktop also rejects queued voice commands from an older listening session. Speech output suppresses stale word/completion events after cancellation, survives child startup failures and reports abrupt speech worker exit. An input stream that stops without raising is detected and enters the bounded retry path. Turning speech off in Settings now stops active speech. Native model/device initialization can still delay mute because the app waits for the capture worker to exit; actual acoustic behavior and Windows drivers remain untested.

## Documents and local summaries

For PDF support install the optional dependency in development:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[documents]'
```

`document report.pdf` previews extractable PDF text. `document report.txt` also supports existing UTF-8 plain-text formats. `summarize file report.pdf` or `summarize file report.txt` produces a **local extractive summary**: sentences copied from the document, ranked by word frequency. It is not an AI interpretation, translation, factual verification or complete account of the document. No file content is uploaded or stored in conversational memory. Paths must resolve uniquely inside approved folders.

PDF input is limited to 10 MiB. The parser runs in a disposable spawned process with a 12-second deadline, at most 20 pages and 120,000 extracted characters. POSIX workers additionally attempt a 512 MiB address-space limit; Windows has no equivalent memory cap in this implementation. A malformed PDF can consume resources until the child is stopped. Cancellation terminates the parser, while encrypted, invalid and image-only/scanned PDFs return clear errors. OCR and Office document parsing are not implemented. Previews show up to 12,000 characters; extractive summaries show up to 2,400 copied characters and indicate when document limits excluded content. Parsing does not execute document scripts. No licensed voice/avatar material is obtained through document parsing.

## Local CSV analysis

`analyze csv sales.csv` reports actual headers, analyzed/scanned row counts, truncation, per-column missing counts and count/minimum/maximum/mean for columns whose nonempty values are all finite numbers. It uses a strict comma-separated parser with UTF-8/BOM support. Empty/whitespace cells count as missing. Duplicate/blank headers, inconsistent row widths, malformed encoding, non-CSV paths or exceeded limits fail explicitly.

Input is limited to 5 MiB, 100 columns, 16 KiB per field and 10,000 analyzed rows (plus one lookahead record to detect truncation). A partial report identifies truncation and computes statistics only over analyzed rows. Formula strings are treated as text, never executed. The report includes header labels and aggregates but no cell samples; headers remain untrusted content. Files are unchanged and nothing is sent to an AI provider. Document, summary and CSV commands are available as local saved-workflow steps.

## AI model discovery and temporary conversation

`ai models` queries `/models` on the configured OpenAI-compatible provider. It reports real returned model IDs or an error; it does not download, activate or benchmark models. Some compatible providers do not expose that endpoint. `ask <question>` still requires an explicitly selected model, and cloud use requires your configured key environment variable. API URLs reject embedded credentials, query strings and fragments. HTTPS certificate verification stays enabled; HTTP is allowed only for the supported localhost addresses.

Optionally enable **Keep temporary AI conversation context** in Settings. Prior successful question/answer turns are then sent to the same selected provider on follow-up `ask` commands. The buffer is held only in RAM, capped at 8 pairs/16,000 characters; questions are limited to 8,000 characters and displayed answers to 16,000. Context is independent of SQLite note memory and is never saved to activity history. `new conversation` clears it; saving provider settings, changing provider/model identity and exiting also clear it. Disabled context sends only the current question. A one-command CLI invocation starts with an empty buffer.

Each request snapshots its provider/model configuration. Clearing or changing configuration invalidates pending conversation results and prevents old context from being sent to a newly selected provider. API responses are capped at 1 MiB; compressed responses are refused, and error bodies are not exposed. No AI text or provider tool-call output is executed. There is no automatic file/screen/webpage access or retrieval: documents and CSV analysis remain local unless you explicitly include text in an `ask` prompt. A live local/cloud provider has not been verified in this cloud session; network contract tests use a controlled HTTP transport. The default local Ollama endpoint currently returns a connection error here.

## Bounded desktop crash recovery

Launch `python -m sidhu.app --supervise` for a supervised foreground desktop, or add `--background` for the tray/listening startup path. Installed Start-menu and post-install launches now use `--supervise`; sign-in registration uses `--supervise --background`. Ordinary development launches without that flag are not watched. The parent only starts the installed SIDHU entry point with fixed internal flags; spoken text never becomes a process command.

The watchdog observes child **process exit**, not UI responsiveness. An abnormal exit permits at most 3 restarts within 5 minutes, with 1/2/4-second delays for successive crashes in that window. It stops on clean exit, an existing desktop's duplicate-instance code, launch failure or exhausted budget. A per-user data-directory lock prevents multiple watchdogs for that directory. Selecting tray **Exit** is a clean exit and is not restarted. Internal child flags cannot be combined with supervision; `--command` and `--supervise` are mutually exclusive.

**Crash recovery restarts with the microphone muted.** Enable listening again when ready; no claim of unattended wake-word availability immediately after a full process crash is made. Sign-in's initial configured background launch retains its normal listening attempt. The watchdog does not detect hangs, restart Windows, wake a sleeping computer, bypass permissions, supervise unrelated applications or guarantee cleanup of every native/orphaned descendant after a catastrophic crash. Missing dependencies or repeated startup failures exhaust the budget rather than looping forever. Use an ordinary foreground development launch to inspect a failure's traceback.

`supervisor status` reads the latest saved launch/exit/retry metadata from `supervisor.json`. It is **not a live health check**. No command text, transcript, model output, token or child stderr is saved there. The metadata and lock remain under the SIDHU data directory; no administrator service is installed. Existing enabled sign-in entries are synchronized when Settings is saved, upgrading the prior direct background command. Disabling startup removes the entry even if the old interpreter is missing, and an absent Run key is handled safely.

## Native Windows window controls

Enable **native window controls** in Settings. `windows` lists visible titled windows with their handles and process IDs. Use the complete case-sensitive title, for example:

```text
window minimize "Untitled - Notepad"
window maximize "Untitled - Notepad"
window restore "Untitled - Notepad"
window switch "Untitled - Notepad"
```

Only a unique exact match is accepted. Native title/PID/visibility checks guard against a target changing between lookup and dispatch. The implementation uses pointer-sized Win32 signatures and asynchronous show-state requests, then observes state/focus for up to 0.5 seconds per transition. Windows can deny foreground changes or protected-window operations; unverified results are reported as failures. Minimized windows are restored before switching when permitted. Enumeration is bounded at 1,000 handles. No coordinate clicks, forced focus bypass, typing, close/kill, security prompt handling or administrator actions are implemented.

These commands are not currently accepted as saved-workflow steps. Window titles appear only in the live command/result display, not persisted activity arguments. The command console now inserts output as plain text, so HTML-like window titles and tool content do not become formatted dashboard content. Native Windows execution is unverified here: tests cover the wrapper and semantic outcomes using simulated APIs. The cloud host can only report Windows-session requirements.

The Windows CI source now includes a packaged `--command diagnostics` smoke check before installer compilation. The workflow has not run in this session; no Windows binary or installed application is claimed as verified.

## One-shot screen preview and optional image analysis

Enable **one-shot screen capture** in Settings, then use **Screen** or the desktop command `capture screen` / `analyze screen`. A per-request confirmation appears before any capture. When approved, a visible indicator shows and SIDHU captures the **primary screen once**. The image may include SIDHU and other visible applications; it does not hide other apps, bypass protected desktops or record a video. A local preview opens before any provider request. CLI commands and saved workflows cannot capture screens.

The image is kept in memory as a PNG, scaled to a maximum 2048-pixel long edge with a 4 MiB encoded limit; oversized inputs beyond 40 million pixels are refused. No screenshot file, database image, persistent transcript image or automatic export is created. Choose **Discard image** to close the preview without sharing. The screen helper requires a working Qt GUI-thread/session. Locked/secure desktops, unsupported display backends and unavailable screens can fail or return unusable output; actual Windows capture has not been verified here.

For optional image analysis, configure an image-capable OpenAI-compatible model. The preview shows the exact provider URL/model and an explicit **Approve image analysis** control. A second confirmation is required to send that one image and your question. The app cannot verify model vision support from a model name; unsupported models return a provider error. The image request uses its own single-use, client-bound approval snapshot. Clearing or changing provider/model/key configuration expires it; a copied or reused token cannot dispatch. No response or image is automatically added to ordinary text conversation turns or saved notes. Opt-in activity history records only the fixed `analyze screen` label, timing and status.

The provider receives the approved image/question and may retain them under its own policies. Cancellation before dispatch prevents sending; once a network request has started, cancellation cannot retract bytes already sent and can wait for a blocked I/O interval. It discards late results. Provider changes do not redirect an approved image to a newly selected destination. Waiting for provider headers does not hold the settings lock. Image/embedded text and model responses cannot execute tools or computer actions.

There is no continuous screen observation, automatic screenshot timer, OCR engine, screen selection, window capture, screenshot export, or vision-driven clicking in this version. Tests use synthetic QImages, simulated dialogs and controlled HTTP transport; no physical screen or live vision service was used in cloud validation.

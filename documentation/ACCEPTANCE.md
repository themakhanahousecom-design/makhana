# Actual capability and acceptance status

This is an MVP, not completion of the master development specification. Status **PARTIALLY WORKING** means code exists but a required platform, device, model, or behavior remains unverified. Test outcomes below distinguish host execution from Windows acceptance.

| # | Requested acceptance | Current status / verification needed |
|---|---|---|
| 1 | Starts at Windows sign-in | PARTIALLY WORKING: per-user Run integration implemented; Windows test pending |
| 2 | Main UI not needed | PARTIALLY WORKING: background mode/tray implemented; Windows session test pending |
| 3 | Wake word | REQUIRES CONFIGURATION: Vosk model + mic. Wake gate unit tested; actual acoustic recognition untested |
| 4 | Hindi speech | REQUIRES CONFIGURATION: compatible speech model; text routing tested |
| 5 | Punjabi speech | REQUIRES CONFIGURATION: compatible recognizer/model; availability unverified; text routing tested |
| 6 | English speech | REQUIRES CONFIGURATION: English Vosk model; hardware test pending |
| 7 | Hinglish speech | REQUIRES CONFIGURATION: model accuracy unverified; text routing tested |
| 8 | Opens Chrome | PARTIALLY WORKING: fixed executable lookup; Windows launch test pending |
| 9 | Opens Explorer | PARTIALLY WORKING: Windows launch test pending |
| 10 | Search Downloads | WORKING: approved-folder recursive filename search tested; actual user Downloads untested |
| 11 | Browser navigation | PARTIALLY WORKING: URL dispatch plus Playwright inspection, HTTP response/final URL verification and rendered text extraction implemented. Policy and error handling tested with doubles; real launch blocked by cloud sandbox configuration; Windows test pending |
| 12 | Volume | PARTIALLY WORKING: pycaw setter/readback implemented; Windows audio test pending |
| 13 | Follow-up speech | PARTIALLY WORKING: time window tested; microphone flow untested |
| 14 | Interrupt speech | PARTIALLY WORKING: dashboard interruption terminates isolated TTS worker; tests cover blocked-worker termination, queue clearing and subsequent output. Spoken barge-in not implemented; Windows audio validation pending |
| 15 | Task cancellation | PARTIALLY WORKING: cooperative file cancellation / AI response discard; no rollback; dashboard TTS interruption implemented |
| 16 | Actual execution results | WORKING for tested core; app/browser dispatch explicitly distinguished from completion |
| 17 | Voice/avatar lip sync | PARTIALLY WORKING: native Windows SAPI visemes select live mouth poses; other voices use approximate word events. Event protocol, cancellation and QML bindings tested; actual Windows audible synchronization pending |
| 18 | Real avatar state animations | PARTIALLY WORKING: articulated original procedural 3D scene with breathing, blinking, head/arm motion and lifecycle states; separate animated software portrait. Real app preview works; native GPU appearance and realism pending |
| 19 | Actual system information | WORKING: live psutil readings and functional diagnostics |
| 20 | Dashboard closes, listening persists | PARTIALLY WORKING: tray lifecycle implemented; Windows test pending |
| 21 | Mute stops listening | PARTIALLY WORKING: stop event and stream closure implemented; physical microphone test pending |
| 22 | Recoverable crash restart | PARTIALLY WORKING: audio retries plus opt-in bounded desktop watchdog. Process-exit/retry tests and recovered-muted Qt test pass; actual Windows crash/restart pending. Recovered microphone requires manual re-enable |
| 23 | Memory persistence | WORKING: SQLite reopen test |
| 24 | Disabled memory not written | WORKING: database not created for disabled memory commands |
| 25 | Tool permissions | WORKING: fixed app allowlist; approved roots with symlink containment tests; AI cannot execute tools |
| 26 | Payments/security blocked | WORKING: no payment/authentication/security executor, sensitive command refusals tested; keyword list is not a general security classifier |
| 27 | Local AI | REQUIRES CONFIGURATION: OpenAI-compatible HTTP client tested using mock transport; live Ollama not run |
| 28 | Cloud AI | REQUIRES CONFIGURATION: HTTPS client; no provider credential or live provider tested |
| 29 | Network failures accurate | WORKING: transport-failure test; live provider outage not tested |
| 30 | Practical laptop resource use | BLOCKED BY SYSTEM LIMITATION: Acer hardware not connected to Linux host; no laptop benchmark claimed |
| 31 | Installer | PARTIALLY WORKING: PyInstaller + Inno scripts supplied; Windows build/install not executed |
| 32 | No developer terminal | PARTIALLY WORKING: windowed packaging + pythonw startup; Windows packaged launch test pending |

## Required Windows manual run

1. Run `installer/build.ps1`, build the Inno installer and install as a standard user.
2. Configure a licensed Vosk model and an actual input device; choose a suitable installed TTS voice.
3. Enable listening. Say “Hey Sidhu”, then “open Notepad”. Verify the window yourself and confirm the UI reports dispatch, not verified readiness.
4. Repeat recognition using each desired language with the appropriate model. Record failures, false activations and command latency; no language accuracy claim can be made from typed-command tests.
5. Close the dashboard and repeat from the tray. Mute, speak, confirm no command executes, unmute and retry. Inspect microphone activity in Windows.
6. Test default device removal/reconnection and failure messaging. Verify no audio files are written.
7. Enable sign-in startup, sign out/in and repeat with no terminal open; disable startup and confirm the Run entry is removed.
8. Search a test approved folder; deny Chrome in settings; verify denial. Check volume readback against the Windows mixer.
9. Test enabled/disabled memory after restart; delete notes with confirmation.
10. Configure a real local/cloud model, test a normal answer and an unreachable endpoint. Confirm model output never executes a tool.
11. Measure actual CPU/RAM while hidden, visible and listening on the Acer. Test sleep/resume and locked-session microphone limitations.
12. Uninstall; confirm app binaries and startup entry are removed. Local data is retained unless the user deletes `%LOCALAPPDATA%\SidhuAI`.

## Architecture and remaining phases

- `core.py`: bounded deterministic routing and tool results; no arbitrary shell or AI tool execution.
- `windows.py`: fixed Windows application dispatch, HTTPS browser dispatch, volume, per-user startup.
- `voice.py`: local ASR, wake/follow-up gate, bounded audio queue, retry, isolated cancellable system TTS process supervised by a worker thread.
- `app.py`: Qt UI, tray, bounded single-task worker, nonpersistent transcript, settings.
- `config.py` / `memory.py`: local JSON settings and explicit opt-in SQLite notes.

Next phases require real Windows integration testing, a dedicated trained/verified wake detector, stronger multilingual recognition, spoken barge-in, licensed assets and a production facial rig, then browser form/click workflows, screen tools, scheduling and a bounded planner. No fake agent activity, fabricated tool outcomes, embedded credentials or licensed assets are included.

The cinematic dashboard labels actual muted/loading/listening/recovering/error/processing/speaking state. The former ring core has been replaced by an original animated portrait fallback; the native character is a separate articulated Qt Quick 3D scene. Microphone, speech and task status are separate so finishing a command does not erase an audio error. Windows build automation is committed in `.github/workflows/windows.yml`; its CI outcome has not been verified.

## Browser and workflow continuation

- Saved workflow creation/editing/deletion is implemented with local JSON persistence, supported-step validation, a 10-step bound, sequential progress, stop-on-failure and cooperative cancellation. Tests exercise real routing with test Windows tools. No Windows app dispatch or voice recognition is proven by those tests.
- Browser inspection is off by default and requires Playwright, a compatible installed browser and exact approved hostnames. No existing authenticated profile is used. No browser form input, button clicking, authenticated dashboards, screenshots, downloads or semantic multistep navigation is implemented yet.
- Attempted an actual system Chromium launch on this cloud host. It failed because the sandbox helper is owned by `nobody` rather than root, while user-namespace setup is prevented by the host. Sandboxing was not disabled or repaired with privileged changes. Browser inspection is blocked here; fake navigation tests do not satisfy Windows acceptance #11.
- Windows manual browser check: enable inspection, approve a test hostname, inspect a known HTTPS page and compare its returned title/body/status with the actual page. Test an HTTP 404/503, an unapproved hostname, an off-domain redirect and cancellation. Verify no report of successful inspection on navigation failure.
- Windows manual workflow check: save a sequence opening Notepad then running diagnostics, restart and run it by name; deny Notepad and confirm the second step does not run. Verify cancellation prevents subsequent steps and no recursive or shell workflow can be saved.

## File tools and memory editor continuation

WORKING on the cloud host with real fixture files: approved-root UTF-8 text previews, case-insensitive content search, modified-time ordering and SHA-256 duplicate grouping. Tests cover traversal denial, ambiguous paths, binary/oversized/invalid-encoding rejection, scan budget enforcement, cancellation and symlink escapes. This plain-text tool does not parse PDF/Office; optional PDF text parsing was subsequently added through DocumentTools. Filesystem mutation/automatic cleanup remains unimplemented.

WORKING with real SQLite and an offscreen Qt editor: note search, editing, confirmed per-note deletion and new-file JSON export. The GUI test substitutes user dialog answers and then verifies actual database and exported-file contents; it does not exercise physical user interaction on Windows. Existing memory opt-in behavior remains enforced. These additions do not establish the pending microphone, Acer performance or Windows installation acceptance checks.

## Original avatar continuation

The cinematic redesign supplies original procedural 3D geometry and a separate generated cinematic portrait used by the animated software mode. Both receive actual lifecycle state and mouth events. The native model has articulated arms/hands, headphones, layered black turban and neon jacket trim; it remains a stylized model. The portrait has affine breathing/tilt, blink and mouth overlays; its pictured hand is not independently rigged. No celebrity likeness or voice is bundled.

The native speech worker relays real SAPI viseme IDs when the installed voice emits them, with word callbacks as an approximate fallback. Protocol tests simulate the driver and do not establish actual audible synchronization. The offscreen app renders the portrait, because Qt Quick 3D is unavailable on this software host. QML component creation/state/viseme bindings are tested; native GPU rendering, physical speech timing and Acer resource use remain pending. See [INTERFACE.md](INTERFACE.md) for launch and manual acceptance instructions and [ASSETS.md](ASSETS.md) for provenance.

## Local productivity continuation

WORKING in automated host tests: explicitly enabled local task creation/listing, done/reopen, relative reminders, cancellation, restart persistence, due-time filtering, retry after failed notification dispatch and no database writes while disabled. Reminder content is never executed. The Qt integration test uses actual panel buttons and verifies SQLite changes, then advances a test clock and confirms scheduler output reaches the dashboard with dispatched state. Dialog responses are simulated.

Windows tray notification presentation, behavior under Focus Assist, timer behavior through actual sleep/resume and sign-in startup remain unverified. Notification dispatch is not proof of human receipt. There is no calendar integration, workflow scheduler or wake-from-sleep service. A bounded opt-in process watchdog was subsequently added. On Windows, add a one-minute reminder, hide the dashboard and verify notification behavior; disable notifications and inspect dashboard status, then exit/restart after a due time to test overdue delivery. Tasks/reminders require the separate opt-in productivity setting and are retained when disabled.

## Diagnostics, activity and routing continuation

WORKING on this cloud host: actual structured hardware and process reports, explicit unavailable readings, opt-in metadata-only history with 500-record retention, history viewing/deletion, measured execution durations, strict app/URL whole-command routing and bounded/cancellable filename search. New regression tests cover ambiguous commands, diagnostic/app names embedded in filenames, exact PDF suffix, empty-directory traversal/cancellation and retention/privacy of activity records. The Qt test verifies the activity table/confirmed deletion and drops an older listening session's queued command.

Voice lifecycle tests now cover stale recognition after mute/speech, stale speech callbacks after stop, failed pipe/process startup, abrupt child crash and inactive capture streams. These are simulated lifecycle tests; they do not establish physical microphone mute, actual wake-word accuracy or Windows SAPI behavior. A blocked native model/device initializer may still delay mute acknowledgment. The Windows GPU inventory is tested with simulated responses; no actual Windows hardware was queried.

The cloud CLI hardware and process reports succeeded with actual data. Missing battery/temperature/GPU sensors were reported unavailable. User-level laptop performance, full wake-to-action latency, Windows sign-in startup, audible synchronization, GPU appearance, browser launch and installation remain pending as previously documented.

## Documents, data and AI context continuation

WORKING in actual-file tests and cloud CLI smoke checks: UTF-8/PDF previews, local extractive summaries and bounded CSV aggregates. A generated text-bearing PDF was parsed through the CLI and its summary returned; a CSV CLI report used actual input. PDF errors and limits are explicit. PDF parsing is isolated in a timed child process; POSIX memory limits are additional best-effort protection, while Windows has only the time bound. No OCR, Office parser, generative document reasoning or cloud upload is implied.

Provider model discovery and optional RAM-only context are implemented and tested through a controlled HTTP transport. Tests cover context off/on, clearing, identity changes, stale-generation suppression, provider-change privacy, malformed/tool-only/error responses, endpoint validation, response-byte limits, compression refusal and elapsed-response checks. Actual `ai models` against the default local endpoint failed with an accurate connection error; live Ollama/cloud acceptance #27/#28 remains pending. Context, file contents and output do not enter persisted activity metadata.

A regression test now covers cancellation after GUI submission but before worker dispatch, ensuring that an accepted cancellation is not cleared by worker startup. Windows microphone, browser, GPU-rendering, startup and installer acceptance remain outstanding.

## Desktop watchdog and window-control continuation

WORKING in host tests: watchdog clean/duplicate exit handling, bounded retry/backoff/window expiry, lock exclusion/release, actual controlled child exit, launch/wait failure handling, status observations and invalid flag combinations. The Qt recovery test verifies that a recovered background desktop does not call the microphone start method. Startup registry behavior is simulated, including missing Run keys and stale/missing interpreters. Windows sign-in and installed watchdog behavior remain acceptance work.

Native Windows window listing/minimize/maximize/restore/switch are implemented behind an opt-in setting. Wrapper and semantic tests use fake APIs to verify pointer widths, asynchronous requests, exact-title/identity matching, ambiguity/permission refusal, bounded transitions and readback. They do not prove Win32 execution on the Acer. No app termination or privilege bypass is implemented. Activity records omit title arguments; live output is plain text.

Windows manual checks: enable controls, list actual Notepad's full title, minimize/maximize/restore/switch and verify both state and reported outcome. Try a missing/duplicate title and a denied foreground change. Enable supervised sign-in startup, test an intentional tray Exit, then terminate only the app's test desktop process and confirm one bounded recovery with muted capture. Verify repeated crashes exhaust the budget. Uninstall and confirm startup removal. The installer/CI scripts were updated, but CI and installer execution remain unverified.

## One-shot screen and optional vision continuation

WORKING in automated component and Qt tests: explicit per-capture permission before backend invocation, GUI-thread checks, synthetic-image scaling/PNG bounds, a visible capture indicator, local preview, discard, separate provider-sharing approval, preview cancellation and provider-change rejection. CLI/workflow capture is refused. Provider consent is single-use and tied to client/configuration/generation; forged, foreign, reused and expired approvals do not dispatch. Tests verify no image/question/answer enters text context, notes or activity output.

These tests use generated QImages and controlled HTTP transport. Physical primary-screen capture on Windows and image interpretation by a live vision-capable model remain REQUIRES CONFIGURATION / Windows acceptance items. No continuous observation, window selection, local OCR, automatic actions or screenshot export is implemented. The image remains in local process memory until discarded/request completion; no application screenshot file is created. Approved providers can retain request data under their own policies.

Windows manual check: enable capture, deny once and confirm no image is taken; approve once and inspect the preview; discard and verify no provider request. With a real configured vision model, approve the exact displayed destination, compare the response to visible pixels, cancel/reconfigure in flight and verify late results are discarded. Inspect local data storage for screenshot artifacts. Do not mark physical capture or live vision acceptance as passed from the simulated tests.

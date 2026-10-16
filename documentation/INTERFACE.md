# Cinematic SIDHU AI desktop

The existing PySide6 application now uses a dark workstation composition with cyan lighting, a prominent SIDHU AI title, a central original Punjabi male character, feature navigation, quick commands, a microphone panel and a speech bubble. It remains a local desktop application connected to the existing command engine, settings and permission controls. It does not require a web server or a browser.

Actual window previews: [full desktop](previews/cinematic-desktop.png) and [1366×728 compact desktop](previews/compact-desktop.png), leaving room for the taskbar on a 1366×768 screen. These were captured from the running Qt application on the cloud host using the labelled animated 2D fallback. Native 3D has a separate, more stylized appearance and has not been visually verified on a Windows GPU.

## Character and speech

Artwork provenance is recorded in [ASSETS.md](ASSETS.md). Licensed installed SAPI voices can be selected by ID; external character model import and retargeting are not implemented.

The character is original artwork: a turban, beard, dark clothing and illuminated headphones. The software renderer uses an original generated cinematic portrait with live QPainter animation overlays; a vector portrait is available if that asset is missing. No Sidhu Moose Wala likeness, voice recording, licensed photograph or celebrity voice clone is bundled. Any future licensed asset integration requires the actual assets and appropriate rights; there is no automatic import or voice-cloning feature.

The native character uses Qt Quick 3D with articulated procedural geometry. Idle breathing, blinking, head movement, arm gestures and listening/thinking/speaking states respond to the application lifecycle. Native 3D is enabled by default for new settings; existing saved preferences are preserved. The software character remains visible when native 3D is disabled or unavailable. Its cinematic image has animated eyelids, speech-driven mouth overlays and restrained whole-image breathing/tilting; it is not a rigged 3D character and its pictured hand is not independently articulated. Neither renderer is a scanned or motion-captured human. The interface follows the supplied reference's composition and blue holographic style using original artwork.

On Windows, the speech worker uses SAPI speech output and its native viseme events to drive mouth poses during the actual utterance. This is event-driven mouth-shape animation, not an audio-to-face neural model or full facial performance capture. Other supported speech backends use approximate word-event mouth motion, which is identified separately. Cancelling speech stops the disposable worker and clears queued output; the visual mouth returns to rest. Physical Windows SAPI event timing still requires testing.

Voice quality, language and accent depend on installed Windows voices and the configured voice ID. In Settings, select **Find installed voices**, then choose an available voice from the returned metadata. A blank voice ID prefers an installed Punjabi male voice, then an Indian male voice, then a Punjabi voice when those language/gender attributes are available; otherwise it uses the system default. Those attributes do not establish vocal depth, naturalness or a specific accent. The application cannot turn an English system voice into a natural Punjabi-accented voice, and no guaranteed natural Punjabi male voice is bundled. Speech rate remains configurable. Recognition still requires an extracted Vosk language model and a microphone. Listening is opt-in and pauses while the assistant speaks to prevent self-triggering; spoken interruption during speech is not implemented.

## Run the existing checkout

Windows PowerShell, from the existing project directory:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e '.[desktop,browser,documents,dev]'
$env:SIDHU_DATA_DIR = Join-Path $env:LOCALAPPDATA 'SidhuAI'
& .\.venv\Scripts\python.exe -m sidhu.app
```

Use Settings to configure the Vosk model, installed speech voice, approved folders, optional AI endpoint/model and the existing opt-in capabilities. Native 3D is the default for new profiles. If an existing profile has it disabled, enable the avatar setting and relaunch. A suitable graphics driver is required. Qt normally selects Direct3D on Windows; if diagnosing backend selection, use this process-local override before launch:

```powershell
$env:QSG_RHI_BACKEND = 'd3d11'
& .\.venv\Scripts\python.exe -m sidhu.app
```

Remove the override after troubleshooting with `Remove-Item Env:QSG_RHI_BACKEND`. If the GPU path fails, disable the native avatar setting or launch with `$env:QT_QUICK_BACKEND = 'software'` to use the software character. Enable the lightweight animation setting to reduce motion further. Remove that override with `Remove-Item Env:QT_QUICK_BACKEND` when returning to native rendering. These variables affect only applications launched from that PowerShell session.

On the Linux cloud host, the writable data override is required:

```bash
cd /workspace/makhana
SIDHU_DATA_DIR=/workspace/scratch/sidhu-data .venv/bin/python -m sidhu.app
```

An interactive desktop session is needed for a visible window. The headless smoke mode below instantiates the real UI with listening and speech disabled, writes an optional developer-requested preview and exits:

```bash
cd /workspace/makhana
SIDHU_DATA_DIR=/workspace/scratch/sidhu-preview-data \
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
SIDHU_UI_PREVIEW=/workspace/scratch/sidhu-interface-preview.png \
.venv/bin/python -m sidhu.app --ui-smoke
```

`SIDHU_UI_PREVIEW` captures the SIDHU window in smoke mode; this developer preview path is separate from the permission-gated screen-capture feature. It does not capture other applications. A software-rendered preview verifies the application layout and fallback artwork, not native GPU rendering, actual recognition, audible output or Windows behavior.

## Existing behavior and permissions

Navigation opens real existing application panels or dispatches supported commands. Quick commands route through the same command engine or the existing screen workflow; they do not execute arbitrary generated actions. A command needing configuration can report that configuration is missing. Tool output and AI text remain inert display content.

| Control | Actual behavior |
| --- | --- |
| Voice commands / Enable listening | Enable or mute the existing Vosk listener. |
| Windows automation | Run `windows`; native window controls must be enabled and need Windows. |
| Apps & files | Run the approved-folder `recent files` search. |
| Search the web / Search on Google | Ask for search terms and open a Google search URL through the engine. |
| Chat with AI | Ask for a question and send an `ask` command to the configured provider. |
| Manage tasks | Open the existing tasks/reminders manager. |
| System control | Run `diagnostics`. |
| Notes & memory | Open the existing local memory manager. |
| Saved workflows | Open the existing workflow editor. |
| Open Chrome | Run the allowlisted `open Chrome` action. |
| Write a note | Prompt for a local note and run `remember`; memory must be enabled. |
| Show my files | Run `open Explorer` on Windows. |
| Tell me the time | Run `time`. |
| Open music | Open `https://music.youtube.com`; this does not automatically start playback. |
| Take a screenshot | Start the existing one-shot capture consent and preview workflow. |
| Shutdown unavailable | Disabled. The engine has no power action. |
| Run / Stop | Submit typed commands, or stop speech and request cooperative task cancellation. |
| Show session | Open the actual command transcript and speech synchronization status in a separate session window. |
| Settings / Activity / Capabilities | Open the existing configuration, activity metadata and capability panels. |

The existing settings, local memory, tasks/reminders, activity metadata, workflows, optional model connections, background/tray path and bounded watchdog remain in place. One-shot screen capture still needs an enabled setting and per-request consent, and sending an image to a provider requires separate approval. The new visual treatment does not enable permissions or start a microphone on its own.

The waveform uses normalized RMS measured from actual microphone PCM chunks, forwarded at a bounded update rate. It is flat when silent, muted or speaking; no fake listening amplitude or synthesized speech-output waveform is generated. The orbit around the microphone is decorative state animation, not an audio meter. These levels are not a calibrated sound-pressure measurement, and level samples are not saved. The speech bubble displays current assistant output. Neither waveform nor bubble proves a command succeeded; actual command results and errors remain available through **Show session**.

## Windows build and packaging

From Windows PowerShell:

```powershell
./installer/build.ps1
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" installer\sidhu.iss
```

The build runs the automated tests before producing the portable `dist\SidhuAI\SidhuAI.exe`. Inno Setup 6 produces the unsigned per-user installer under `dist\installer`. Shortcuts retain the existing `--supervise` watchdog launch. No administrator service is installed.

The PyInstaller command explicitly includes the lazy `QtQml`, `QtQuick`, `QtQuickWidgets` and `QtQuick3D` modules plus `comtypes.client`. Its standard Qt hooks collect the required native/QML runtime dependencies; the script does not add a blanket `--collect-all PySide6`. Package data includes the original QML and supported image formats. No downloaded human model, external texture pack, speech model or voice is bundled. Vosk models must still be installed and selected separately; browser inspection still needs a compatible Chromium installation.

The Windows GitHub Actions workflow builds and tests, runs packaged CLI diagnostics, launches `--ui-smoke` with the software backend, checks that its window preview was created, builds the installer and uploads unsigned artifacts. That smoke check does not exercise a physical display, native 3D or SAPI audio. A workflow being present is not evidence of a successful Windows build; inspect the actual workflow result before distributing a binary.

## Performance and manual acceptance

The software character and lightweight mode provide lower-cost options for an approximately 16 GB laptop. Native 3D uses procedural geometry rather than a large external character model. RAM use, GPU frame rate, battery cost and responsiveness on the Acer have not been measured. Large local language models and Vosk models have separate memory costs; selecting a model is a user configuration choice.

Before treating a Windows release as validated, check these on the laptop:

- Launch both source and packaged builds with native 3D enabled. Confirm the character renders, clips correctly on resize, and shows idle, blinking, gesture, listening, thinking and speech animation.
- Compare audible SAPI speech with mouth poses, including punctuation, long utterances and cancel/restart. Verify the installed voice ID and language. Test a missing voice and device error reporting.
- Configure a real Vosk model and microphone. Test enable/mute, wake phrase, follow-up expiry, recognition errors, speech pause/resume, background tray mode and explicit tray Exit.
- Exercise navigation and quick commands with allowed and disabled permissions, plus a real command failure. Confirm AI text cannot dispatch tools.
- Check the local capture preview and separate image-sharing approvals. Verify disabling capture still prevents it.
- Test display scaling at 100%, 125% and 150%, smaller window sizes and the laptop's usual resolution. Compare native and software rendering and lightweight mode while idle and speaking.
- Verify packaged QML loading and SAPI COM/type-library creation from a standard user account. Check startup, bounded crash recovery and install/uninstall. Do not claim these passed from an offscreen Linux preview.

Automated test counts, preview evidence and current acceptance limitations are recorded alongside the repository's validation notes. All simulated audio, network and Windows API checks remain distinct from physical Windows acceptance.

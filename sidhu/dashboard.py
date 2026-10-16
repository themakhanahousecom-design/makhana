"""Cinematic desktop composition; actions stay in the existing Window/Engine."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QWidget, QLineEdit, QPushButton,
    QSizePolicy, QDialog,
)
from .avatar import AvatarView
from .interface import (
    WorkstationBackdrop, GlassPanel, NeonButton, WaveformWidget, SpeechBubble,
    BrandMark,
)


def label(text, name="eyebrow"):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setTextFormat(Qt.PlainText)
    return widget


def build_dashboard(window, settings, log_factory):
    """Build real widgets, keeping the controller's public fields intact."""
    window.setWindowTitle("SIDHU AI · Personal AI Assistant")
    window.resize(1512, 960)
    window.setMinimumSize(1120, 680)
    backdrop = WorkstationBackdrop()
    window.backdrop = backdrop
    backdrop.set_performance(settings.lightweight)
    window.setCentralWidget(backdrop)
    layout = QVBoxLayout(backdrop)
    layout.setContentsMargins(28, 20, 28, 18)
    layout.setSpacing(16)

    header = QHBoxLayout()
    header.setSpacing(20)
    brand = BrandMark()
    brand.setFixedSize(405, 105)
    header.addWidget(brand)
    header.addStretch()
    status_area = QVBoxLayout()
    window.connection = label("LOCAL COMMAND ENGINE", "connectionBadge")
    window.connection.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    window.model_status = label("AI · Model not configured", "mutedLabel")
    window.model_status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    status_area.addWidget(window.connection)
    status_area.addWidget(window.model_status)
    header.addLayout(status_area)
    settings_button = NeonButton("Settings", "settings")
    settings_button.setObjectName("settingsButton")
    settings_button.clicked.connect(window.configure)
    header.addWidget(settings_button)
    layout.addLayout(header)

    body = QHBoxLayout()
    body.setSpacing(20)
    left = QVBoxLayout()
    left.setSpacing(14)
    left_host = QWidget()
    left_host.setObjectName("transparentHost")
    left_host.setLayout(left)
    left.setContentsMargins(0, 0, 0, 0)
    left_host.setFixedWidth(248)

    window.bubble = SpeechBubble()
    window.bubble.set_performance(settings.lightweight)
    window.bubble.set_message("Haan ji. Ready when you are.", "SIDHU AI · READY")
    window.bubble.setMinimumHeight(132)
    window.bubble.setMaximumHeight(182)
    left.addWidget(window.bubble)
    navigation = GlassPanel()
    navigation.body.setContentsMargins(12, 12, 12, 12)
    navigation.body.setSpacing(2)
    navigation.body.addWidget(label("YOUR WORKSPACE"))
    window.nav_buttons = {}
    actions = (
        ("Voice commands", "mic", window.toggle_voice),
        ("Windows automation", "apps", lambda: window.dispatch("windows")),
        ("Apps & files", "folder", lambda: window.dispatch("recent files")),
        ("Search the web", "globe", window.search_web),
        ("Chat with AI", "chat", window.ask_ai),
        ("Manage tasks", "tasks", window.manage_productivity),
        ("System control", "settings", lambda: window.dispatch("diagnostics")),
        ("Notes & memory", "note", window.manage_memory),
        ("Saved workflows", "spark", window.configure_workflows),
    )
    for text, icon, handler in actions:
        button = NeonButton(text, icon)
        button.setProperty("role", "navigation")
        button.setMinimumHeight(34)
        button.clicked.connect(handler)
        navigation.body.addWidget(button)
        window.nav_buttons[text] = button
    navigation.body.addStretch(1)
    tools = QHBoxLayout()
    for text, handler in (("Activity", window.manage_activity), ("Capabilities", window.capabilities)):
        button = QPushButton(text)
        button.setObjectName("quietButton")
        button.clicked.connect(handler)
        tools.addWidget(button)
    navigation.body.addLayout(tools)
    left.addWidget(navigation, 1)
    body.addWidget(left_host)

    stage = QWidget()
    stage.setObjectName("characterStage")
    stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    stage_layout = QVBoxLayout(stage)
    stage_layout.setContentsMargins(0, 0, 0, 0)
    stage_layout.setSpacing(3)
    stage_top = QHBoxLayout()
    stage_top.addWidget(label("PERSONAL AI ASSISTANT", "stageEyebrow"))
    stage_top.addStretch()
    window.render_label = label("", "renderBadge")
    stage_top.addWidget(window.render_label)
    stage_layout.addLayout(stage_top)
    window.visual = AvatarView(enabled=settings.avatar_enabled and not settings.lightweight)
    window.visual.set_performance(settings.lightweight)
    window.visual.setMinimumHeight(320)
    stage_layout.addWidget(window.visual, 1)
    window.render_label.setText("LIVE 3D" if window.visual.fallback is None else "ANIMATED 2D")
    window.visual.mode_changed.connect(lambda mode: window.render_label.setText("LIVE 3D" if mode == "3d" else "ANIMATED 2D"))
    window.render_label.setToolTip("Original Punjabi tribute character. No licensed artist likeness is bundled.")
    window.task_status = label("Task engine idle", "taskStatus")
    window.task_status.setAlignment(Qt.AlignCenter)
    window.task_status.setWordWrap(True)
    stage_layout.addWidget(window.task_status)
    body.addWidget(stage, 1)

    right_host = QWidget()
    right_host.setObjectName("transparentHost")
    right_host.setFixedWidth(264)
    right = QVBoxLayout(right_host)
    right.setContentsMargins(0, 0, 0, 0)
    right.setSpacing(12)
    quick = GlassPanel()
    quick.body.setContentsMargins(12, 12, 12, 12)
    quick.body.setSpacing(4)
    quick.body.addWidget(label("QUICK COMMANDS"))
    window.quick_buttons = {}
    for text, icon, handler in (
        ("Open Chrome", "globe", lambda: window.dispatch("open Chrome")),
        ("Write a note", "note", window.write_note),
        ("Show my files", "folder", lambda: window.dispatch("open Explorer")),
        ("Tell me the time", "clock", lambda: window.dispatch("time")),
        ("Search on Google", "globe", window.search_web),
        ("Open music", "music", lambda: window.dispatch("open https://music.youtube.com")),
        ("Take a screenshot", "camera", lambda: window.dispatch("capture screen")),
    ):
        button = NeonButton(text, icon)
        button.setMinimumHeight(32)
        button.setProperty("role", "quick")
        button.clicked.connect(handler)
        quick.body.addWidget(button)
        window.quick_buttons[text] = button
    # The reference includes shutdown, but the permission-limited engine has no
    # power action. A disabled control truthfully preserves that restriction.
    shutdown = NeonButton("Shutdown unavailable", "power")
    shutdown.setProperty("role", "quick")
    shutdown.setEnabled(False)
    shutdown.setToolTip("Power actions are not supported by the command engine.")
    quick.body.addWidget(shutdown)
    right.addWidget(quick)

    voice = GlassPanel()
    voice.body.setContentsMargins(12, 12, 12, 12)
    voice.body.setSpacing(5)
    voice_title = label("VOICE RECOGNITION")
    voice.body.addWidget(voice_title)
    window.voice_heading = label("Microphone muted", "voiceHeading")
    window.voice_heading.setAlignment(Qt.AlignCenter)
    voice.body.addWidget(window.voice_heading)
    window.waveform = WaveformWidget()
    window.waveform.setMinimumHeight(90)
    window.waveform.setMaximumHeight(120)
    window.waveform.set_performance(settings.lightweight)
    voice.body.addWidget(window.waveform, 1)
    window.status = label("Microphone muted. Enable listening when ready.", "mutedLabel")
    window.status.setWordWrap(True)
    window.status.setAlignment(Qt.AlignCenter)
    window.status.setMaximumHeight(34)
    voice.body.addWidget(window.status)
    window.partial = label("", "transcriptLabel")
    window.partial.setWordWrap(True)
    window.partial.setMaximumHeight(44)
    voice.body.addWidget(window.partial)
    window.mic_button = NeonButton("Enable listening", "mic")
    window.mic_button.clicked.connect(window.toggle_voice)
    voice.body.addWidget(window.mic_button)
    window.speech_status = label("Speech idle", "smallLabel")
    window.speech_status.setWordWrap(True)
    window.speech_status.hide()
    window.sync_status = label("Lip sync · waiting for speech", "smallLabel")
    window.sync_status.setWordWrap(True)
    window.sync_status.hide()
    right.addWidget(voice, 1)
    body.addWidget(right_host)
    layout.addLayout(body, 1)

    console = GlassPanel()
    console.body.setContentsMargins(16, 10, 16, 10)
    console.body.setSpacing(8)
    input_row = QHBoxLayout()
    input_row.setSpacing(10)
    input_row.addWidget(label("COMMAND", "consoleLabel"))
    window.entry = QLineEdit()
    window.entry.setAccessibleName("Assistant command")
    window.entry.setPlaceholderText("Ask a question or try: diagnostics, open Chrome, latest PDF…")
    window.entry.returnPressed.connect(window.submit)
    input_row.addWidget(window.entry, 1)
    send = NeonButton("Run", "send")
    send.clicked.connect(window.submit)
    input_row.addWidget(send)
    stop = NeonButton("Stop", "stop")
    stop.setObjectName("stopButton")
    stop.setToolTip("Stop speech and request cancellation of the current task.")
    stop.clicked.connect(window.cancel)
    input_row.addWidget(stop)
    window.feed_toggle = QPushButton("Show session")
    window.feed_toggle.setObjectName("quietButton")
    window.feed_toggle.setCheckable(True)
    input_row.addWidget(window.feed_toggle)
    console.body.addLayout(input_row)
    window.log = log_factory()
    window.log.setReadOnly(True)
    window.log.setAcceptRichText(False)
    window.log.setMinimumHeight(100)
    window.session_dialog = QDialog(window)
    window.session_dialog.setWindowTitle("SIDHU AI · Current session")
    window.session_dialog.resize(820, 380)
    session_layout = QVBoxLayout(window.session_dialog)
    session_layout.addWidget(window.log, 1)
    session_layout.addWidget(window.speech_status)
    session_layout.addWidget(window.sync_status)
    window.speech_status.show()
    window.sync_status.show()
    close_session = QPushButton("Close")
    close_session.clicked.connect(window.session_dialog.reject)
    session_layout.addWidget(close_session, 0, Qt.AlignRight)
    def toggle_feed(visible):
        window.session_dialog.setVisible(visible)
        if visible:
            window.session_dialog.raise_()
        window.feed_toggle.setText("Hide session" if visible else "Show session")
    window.feed_toggle.toggled.connect(toggle_feed)
    window.session_dialog.finished.connect(lambda: window.feed_toggle.setChecked(False))
    footer = QHBoxLayout()
    window.stats = label("", "smallLabel")
    footer.addWidget(window.stats)
    footer.addStretch()
    window.privacy_status = label("MIC OFF  ·  LOCAL TOOLS", "smallLabel")
    footer.addWidget(window.privacy_status)
    console.body.addLayout(footer)
    layout.addWidget(console)
    # Keep the scene usable on a 1366×768 laptop. Detailed speech diagnostics
    # use a separate session window so opening them cannot push controls offscreen.
    def compact_view(compact):
        brand.setFixedSize(340 if compact else 405, 80 if compact else 105)
        window.bubble.setMinimumHeight(100 if compact else 132)
        window.bubble.setMaximumHeight(120 if compact else 182)
        window.status.setVisible(not compact)
        voice_title.setVisible(not compact)
        window.waveform.setMinimumHeight(72 if compact else 90)
        window.waveform.setMaximumHeight(88 if compact else 120)
        for panel in (quick, voice):
            panel.body.setContentsMargins(*((10, 8, 10, 8) if compact else (12, 12, 12, 12)))
            panel.body.setSpacing(3 if compact else 5)
        for button in (*window.quick_buttons.values(), shutdown):
            button.setProperty("role", "quickCompact" if compact else "quick")
            button.setMinimumHeight(26 if compact else 32)
            button.style().unpolish(button)
            button.style().polish(button)
        layout.setSpacing(10 if compact else 16)
        for button in window.nav_buttons.values():
            button.setMinimumHeight(30 if compact else 34)
        window._compact = compact
    window.apply_compact_view = compact_view
    compact_view(False)

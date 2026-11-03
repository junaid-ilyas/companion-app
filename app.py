#!/usr/bin/env python3
"""
Sesame Robot Companion App — Production Desktop Edition
PyWebView native window with modern HTML/CSS/JS frontend.
"""

import os
import sys
import json
import time
import threading
import traceback
import webview

try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    print("[WARNING] python-dotenv not installed. .env file will be ignored.")

from sesame_companion import SesameCompanionApp, SesameRobotController, AVAILABLE_COMMANDS, AVAILABLE_FACES
from local_fallback import get_local_response


class Api:
    """
    Bridge exposed to the JavaScript frontend via pywebview.
    All internal state and helper methods MUST start with an underscore
    so pywebview reflection does not attempt to expose them or inspect
    native WinForms / COM objects.
    """

    def __init__(self):
        self._app = None
        self._window = None
        self._robot_ip = os.getenv("SESAME_ROBOT_IP", "192.168.1.1")
        self._gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self._voice_enabled = os.getenv("VOICE_ENABLED", "true").lower() == "true"
        self._tts_engine = os.getenv("TTS_ENGINE", "pyttsx3")
        self._wake_word = os.getenv("WAKE_WORD", "hey sesame")
        self._wake_word_mode = os.getenv("WAKE_WORD_MODE", "false").lower() == "true"
        self._personality = "silly"

    def _set_window(self, window):
        self._window = window

    def _js(self, code):
        """Safely evaluate JS in the frontend."""
        try:
            if self._window:
                self._window.evaluate_js(code)
        except Exception:
            pass

    # ── Initialization (called from background thread) ──────
    def _initialize_backend(self):
        """Initialize the companion app backend."""
        try:
            self._app = SesameCompanionApp(
                self._robot_ip,
                self._gemini_api_key,
                self._voice_enabled,
                self._tts_engine,
                self._wake_word,
                self._wake_word_mode,
            )

            # Report AI status
            status = self._app.get_runtime_status()
            if status.get("groq_api_key") == "missing":
                ai_label = "AI: Groq key missing"
            else:
                ai_label = "AI: Groq ready"

            self._js(f"applyAiStatus('{ai_label}')")
            self._js("addMessage('system', '[OK] Backend initialized')")

            config_msg = f"mode={status.get('mode')} model={status.get('groq_model')}"
            self._js(f"addMessage('system', '[Config] {config_msg}')")

            warning = status.get("warning", "")
            if warning and warning != "No configuration warning.":
                self._js(f"addMessage('system', '[Warning] {self._escape_js(warning)}')")

            # Check robot connection
            self._check_connection()

            # Start background status polling
            self._start_status_poller()

        except Exception as e:
            print(f"[ERROR] Backend initialization failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            self._js(f"addMessage('error', 'Failed to initialize: {self._escape_js(str(e))}')")

    def _check_connection(self):
        """Check robot connection and push status to frontend."""
        if not self._app:
            return
        try:
            robot_status = self._app.robot.get_status()
            if "error" in robot_status:
                self._js("applyStatus({connected: false})")
            else:
                face = robot_status.get("currentFace", "default")
                cmd = robot_status.get("currentCommand", "none") or "none"
                self._js(f"applyStatus({{connected: true, face: '{face}', command: '{cmd}'}})")
        except Exception:
            self._js("applyStatus({connected: false})")

    def _start_status_poller(self):
        """Poll robot status every 5 seconds in background."""
        def poll():
            while True:
                time.sleep(5)
                try:
                    if self._app:
                        self._check_connection()
                except Exception as e:
                    print(f"[WARNING] Status poll failed: {type(e).__name__}: {e}")
        t = threading.Thread(target=poll, daemon=True)
        t.start()

    def _escape_js(self, text):
        """Escape text for safe JS string insertion."""
        return text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

    # ── API Methods (called from JS via window.pywebview.api) ──

    def get_initial_state(self):
        """Return initial app state for the frontend to sync UI."""
        return {
            "ip": self._robot_ip,
            "voice_enabled": self._voice_enabled,
            "wake_word_mode": self._wake_word_mode,
            "tts_engine": self._tts_engine,
            "personality": self._personality,
            "ai_status": "AI: checking...",
            "status": {"connected": False, "face": "default", "command": "none"},
        }

    def send_message(self, text):
        """Process a chat message through the AI backend."""
        if not self._app:
            return {"error": "Backend not initialized yet. Please wait."}

        try:
            response, interpretation = self._app.process_input(text)
            source = interpretation.get("source", "unknown")
            ai_response = interpretation.get("response", response)
            face = interpretation.get("face")
            command = interpretation.get("command")

            result = {
                "response": ai_response,
                "source": source,
                "face": face,
                "command": command,
            }

            # Speak if voice enabled
            if self._voice_enabled and "response" in interpretation:
                speak_face = face if not command else None
                self._speak_async(interpretation["response"], speak_face)

            return result

        except Exception as e:
            # Fallback
            fallback = get_local_response(text, self._personality)
            return {
                "response": fallback.get("response", "Beep boop... error."),
                "source": "local_fallback",
                "face": fallback.get("face"),
                "command": fallback.get("command"),
                "error": str(e),
            }

    def _speak_async(self, text, face):
        """Speak text in a background thread with face animation."""
        def do_speak():
            self._js(f"setSpeakingState(true, {json.dumps(face)})")
            try:
                self._app.voice.speak(
                    text,
                    async_mode=False,
                    face=face,
                    robot_controller=self._app.robot,
                )
            finally:
                self._js("setSpeakingState(false, null)")
        threading.Thread(target=do_speak, daemon=True).start()

    def send_command(self, command):
        """Execute a quick command on the robot."""
        if not self._app:
            return {"error": "Backend not initialized yet."}

        try:
            result = self._app.robot.send_command(command)
            if "error" in result:
                return {"error": result["error"]}
            else:
                # Refresh status after command
                try:
                    status = self._app.robot.get_status()
                    return {
                        "success": True,
                        "face": status.get("currentFace"),
                        "command": status.get("currentCommand"),
                    }
                except Exception:
                    return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def run_demo(self):
        """Run the demo sequence."""
        if not self._app:
            return {"error": "Backend not initialized yet."}

        sequence = [
            ("wave", "happy"),
            ("dance", "excited"),
            ("cute", "love"),
            ("bow", "love"),
            ("rest", "default"),
        ]
        try:
            for cmd, face in sequence:
                self._app.robot.send_command(cmd, None)
                self._js(f"applyStatus({{connected: true, face: '{face}', command: '{cmd}'}})")
                time.sleep(3)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self):
        """Get current robot status."""
        if not self._app:
            return {"connected": False}

        try:
            status = self._app.robot.get_status()
            if "error" in status:
                return {"connected": False}
            return {
                "connected": True,
                "face": status.get("currentFace", "default"),
                "command": status.get("currentCommand", "none") or "none",
            }
        except Exception:
            return {"connected": False}

    def toggle_listening(self):
        """Start voice recognition and return transcribed text."""
        if not self._app:
            return {"error": "Backend not initialized."}
        if not self._voice_enabled:
            return {"error": "Voice mode is disabled. Enable in settings."}

        try:
            text = self._app.voice.listen()
            if text:
                return {"text": text}
            else:
                return {"error": "No speech detected"}
        except Exception as e:
            return {"error": f"Voice error: {e}"}

    def update_setting(self, key, value):
        """Update a setting and propagate to backend."""
        messages = {
            "voice": lambda v: self._set_voice(v),
            "wake_word": lambda v: self._set_wake_word(v),
            "tts": lambda v: self._set_tts(v),
            "personality": lambda v: self._set_personality(v),
        }

        handler = messages.get(key)
        if handler:
            return handler(value)
        return {"error": f"Unknown setting: {key}"}

    def _set_voice(self, enabled):
        self._voice_enabled = enabled
        if self._app:
            self._app.voice_mode = enabled
            self._app.voice.voice_enabled = enabled
        status = "enabled" if enabled else "disabled"
        return {"message": f"Voice mode {status}"}

    def _set_wake_word(self, enabled):
        self._wake_word_mode = enabled
        if self._app:
            self._app.wake_word_mode = enabled
        status = "enabled" if enabled else "disabled"
        return {"message": f"Wake word mode {status}"}

    def _set_tts(self, engine):
        self._tts_engine = engine
        if self._app:
            self._app.voice.tts_engine_type = engine
            self._app.tts_engine = engine
        return {"message": f"TTS engine: {engine}"}

    def _set_personality(self, personality):
        self._personality = personality
        if self._app and hasattr(self._app, 'ai') and hasattr(self._app.ai, 'personality'):
            self._app.ai.personality = personality
        return {"message": f"Personality set to: {personality}"}


def main():
    print("[INFO] Starting Sesame Robot Companion")
    api = Api()

    # Resolve path to static files
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    index_path = os.path.join(static_dir, "index.html")

    if not os.path.exists(index_path):
        print(f"[ERROR] Cannot find {index_path}")
        sys.exit(1)

    # Create the native window
    window = webview.create_window(
        title="Sesame Robot Companion",
        url=index_path,
        js_api=api,
        width=1200,
        height=820,
        min_size=(1000, 700),
        background_color="#050810",
        text_select=False,
    )

    api._set_window(window)

    def on_loaded():
        """Called when the webview window is ready."""
        print("[INFO] Webview loaded; initializing backend")
        # Initialize backend in background thread
        threading.Thread(target=api._initialize_backend, daemon=True).start()

    def on_closed():
        print("[INFO] Webview closed")

    window.events.loaded += on_loaded
    window.events.closed += on_closed

    # Start the window (blocks until closed)
    try:
        webview.start(debug=False)
    finally:
        print("[INFO] webview.start returned; application is exiting")


if __name__ == "__main__":
    main()

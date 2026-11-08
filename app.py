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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH, override=True)
except ImportError:
    print("[WARNING] python-dotenv not installed. .env file will be ignored.")

from sesame_companion import SesameCompanionApp, SesameRobotController, VoiceInterface, AVAILABLE_COMMANDS, AVAILABLE_FACES
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
        self._tts_engine = os.getenv("TTS_ENGINE", "piper")
        self._voice_style = (os.getenv("PIPER_VOICE_STYLE", "cute").strip().lower() or "cute")
        self._mic_device = os.getenv("MIC_DEVICE_INDEX", "").strip()
        self._wake_word = os.getenv("WAKE_WORD", "hey sesame")
        self._wake_word_mode = os.getenv("WAKE_WORD_MODE", "false").lower() == "true"
        self._ai_mode = (os.getenv("AI_PROVIDER", "auto").strip().lower() or "auto")
        self._ollama_model = (os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b").strip() or "qwen2.5:0.5b")
        self._personality = "silly"
        self._wake_thread_started = False
        self._closing = False

    def _set_window(self, window):
        self._window = window

    def _js(self, code):
        """Safely evaluate JS in the frontend."""
        try:
            if self._window:
                self._window.evaluate_js(code)
        except Exception:
            pass

    @staticmethod
    def _format_ai_label(status):
        mode = status.get("mode", "auto")
        groq_ok = status.get("groq_api_key") == "configured"
        ollama_ok = str(status.get("ollama_status", "")).startswith("ready")
        ollama_model = status.get("ollama_model", "qwen2.5:0.5b")

        if mode == "ollama":
            return f"Local Ready ({ollama_model})" if ollama_ok else "Ollama missing model"
        if mode == "groq":
            return "Groq Cloud Ready" if groq_ok else "Groq key missing"
        # auto mode
        if groq_ok and ollama_ok:
            return f"Auto Ready (Cloud + {ollama_model})"
        if ollama_ok:
            return f"Auto Ready (Local {ollama_model})"
        if groq_ok:
            return "Auto Ready (Groq Cloud)"
        return "Keyword Fallback"

    def _warmup_ollama_async(self):
        """Pre-load compact local Ollama model into RAM without blocking window startup."""
        def run():
            if not self._app or not hasattr(self._app.ai, "ollama"):
                return
            health = self._app.ai.ollama.warmup()
            status = self._app.validate_runtime_config()
            ai_label = self._format_ai_label(status)
            self._js(f"applyAiStatus('{self._escape_js(ai_label)}')")
            if health.get("ready"):
                self._js(
                    f"addMessage('system', '[Config] Local Ollama warm ({self._escape_js(str(health.get('active_model')))})')"
                )
        threading.Thread(target=run, daemon=True).start()

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
            status = self._app.get_runtime_config() if hasattr(self._app, "get_runtime_config") else self._app.get_runtime_status()
            ai_label = self._format_ai_label(status)

            self._js(f"applyAiStatus('{self._escape_js(ai_label)}')")
            self._js("addMessage('system', '[OK] Backend initialized')")

            config_msg = (
                f"mode={status.get('mode')} groq={status.get('groq_model')} "
                f"ollama={status.get('ollama_status')}"
            )
            self._js(f"addMessage('system', '[Config] {self._escape_js(config_msg)}')")

            warning = status.get("warning", "")
            if warning and warning != "No configuration warning.":
                self._js(f"addMessage('system', '[Config] {self._escape_js(warning)}')")

            # Warm up local Whisper STT + Piper neural TTS + mic noise floor once
            voice_info = self._app.voice.warmup()
            if voice_info.get("stt_ready"):
                voice_msg = (
                    f"[Voice] Local Whisper ({voice_info.get('stt_model')}) + "
                    f"{self._tts_engine} TTS ready"
                )
                self._js(f"addMessage('system', '{self._escape_js(voice_msg)}')")
            elif voice_info.get("stt_error"):
                err_msg = f"[Warning] Local STT init issue: {voice_info['stt_error']}"
                self._js(f"addMessage('system', '{self._escape_js(err_msg)}')")

            # Warm up compact local Ollama model in background if enabled
            if self._ai_mode in {"auto", "ollama"}:
                self._warmup_ollama_async()

            # Check robot connection
            self._check_connection()

            # Start background status polling & wake-word listener
            self._start_status_poller()
            self._start_wake_word_loop()

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
            while not self._closing:
                time.sleep(5)
                try:
                    if self._app and not self._closing:
                        self._check_connection()
                except Exception as e:
                    print(f"[WARNING] Status poll failed: {type(e).__name__}: {e}")
        t = threading.Thread(target=poll, daemon=True)
        t.start()

    def _start_wake_word_loop(self):
        """Listen for the wake word in the background when Wake Word Mode is enabled."""
        if self._wake_thread_started:
            return
        self._wake_thread_started = True

        def wake_loop():
            while not self._closing:
                if (
                    not self._app
                    or not self._voice_enabled
                    or not self._wake_word_mode
                    or self._app.voice.is_listening_manual
                    or self._app.voice.is_speaking
                ):
                    time.sleep(0.25)
                    continue

                try:
                    remainder = self._app.voice.listen_for_wake_phrase(timeout=2.2)
                    if (
                        remainder is None
                        or self._closing
                        or not self._wake_word_mode
                        or self._app.voice.is_listening_manual
                    ):
                        time.sleep(0.05)
                        continue

                    if remainder:
                        self._js(f"onWakeWordTranscript({json.dumps(remainder)})")
                        time.sleep(1.5)
                    else:
                        self._js("addMessage('system', 'Wake word heard — speak now...')")
                        followup = self._app.voice.listen(timeout=5)
                        if followup:
                            self._js(f"onWakeWordTranscript({json.dumps(followup)})")
                            time.sleep(1.5)
                        else:
                            self._js("addMessage('system', 'No command heard after wake word')")
                except Exception as e:
                    print(f"[WARNING] Wake word loop error: {e}")
                    time.sleep(0.5)

        threading.Thread(target=wake_loop, daemon=True).start()

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
            "voice_style": self._voice_style,
            "mic_device": self._mic_device,
            "mic_devices": VoiceInterface.list_input_devices(),
            "ai_mode": self._ai_mode,
            "personality": self._personality,
            "ai_status": "Checking...",
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
        if self._app and self._app.voice:
            self._app.voice.is_speaking = True
            self._app.voice._mute_until = time.monotonic() + 2.0

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

            status = self._app.robot.get_status()
            if "error" in status:
                return {"error": f"Command sent, but status verification failed: {status['error']}"}
            return {
                "success": True,
                "face": status.get("currentFace"),
                "command": status.get("currentCommand") or command,
                "robot_response": result,
            }
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
                result = self._app.robot.send_command(cmd, None)
                if "error" in result:
                    return {"error": f"{cmd}: {result['error']}"}
                self._js(f"applyStatus({{connected: true, face: '{face}', command: '{cmd}'}})")
                time.sleep(3)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self):
        """Get current robot status and refresh AI health."""
        if not self._app:
            return {"connected": False}

        try:
            if hasattr(self._app, "validate_runtime_config"):
                ai_cfg = self._app.validate_runtime_config()
                self._js(f"applyAiStatus('{self._escape_js(self._format_ai_label(ai_cfg))}')")
        except Exception:
            pass

        try:
            status = self._app.robot.get_status()
            if "error" in status:
                return {"connected": False, "mic_devices": VoiceInterface.list_input_devices()}
            return {
                "connected": True,
                "face": status.get("currentFace", "default"),
                "command": status.get("currentCommand", "none") or "none",
                "mic_devices": VoiceInterface.list_input_devices(),
            }
        except Exception:
            return {"connected": False, "mic_devices": VoiceInterface.list_input_devices()}

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
                return {
                    "error": self._app.voice.last_listen_error
                    or "No speech detected"
                }
        except Exception as e:
            return {"error": f"Voice error: {e}"}

    def stop_listening(self):
        """Finish an active manual voice recording immediately."""
        if self._app and self._app.voice:
            self._app.voice.stop_listening()
        return {"stopped": True}

    def update_setting(self, key, value):
        """Update a setting and propagate to backend."""
        messages = {
            "voice": lambda v: self._set_voice(v),
            "wake_word": lambda v: self._set_wake_word(v),
            "tts": lambda v: self._set_tts(v),
            "voice_style": lambda v: self._set_voice_style(v),
            "mic_device": lambda v: self._set_mic_device(v),
            "personality": lambda v: self._set_personality(v),
            "ai_mode": lambda v: self._set_ai_mode(v),
            "robot_ip": lambda v: self._set_robot_ip(v),
        }

        handler = messages.get(key)
        if handler:
            return handler(value)
        return {"error": f"Unknown setting: {key}"}

    @staticmethod
    def _save_env_key(env_key, env_value):
        """Persist a single key=value into .env without disturbing existing keys or comments."""
        try:
            lines = []
            if os.path.exists(ENV_PATH):
                with open(ENV_PATH, "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()

            updated = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("#") and "=" in stripped:
                    k = stripped.split("=", 1)[0].strip()
                    if k == env_key:
                        new_lines.append(f"{env_key}={env_value}")
                        updated = True
                        continue
                new_lines.append(line)

            if not updated:
                new_lines.append(f"{env_key}={env_value}")

            with open(ENV_PATH, "w", encoding="utf-8") as fh:
                fh.write("\n".join(new_lines) + "\n")
        except Exception as exc:
            print(f"[WARNING] Could not persist {env_key} to .env: {exc}")

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

    def _set_voice_style(self, style):
        clean_style = str(style or "cute").strip().lower()
        if clean_style not in {"cute", "silly", "natural"}:
            return {"error": f"Unsupported voice style: {clean_style}"}
        self._voice_style = clean_style
        os.environ["PIPER_VOICE_STYLE"] = clean_style
        self._save_env_key("PIPER_VOICE_STYLE", clean_style)
        if self._app and self._app.voice:
            self._app.voice.voice_style = clean_style
            if self._voice_enabled and self._tts_engine == "piper":
                self._speak_async("Hi friend! Ready to hang out?", "happy")
        return {"message": f"Voice character: {clean_style}"}

    def _set_mic_device(self, raw_idx):
        val = str(raw_idx if raw_idx is not None else "").strip()
        if val == "" or val.lower() == "default":
            self._mic_device = ""
            os.environ.pop("MIC_DEVICE_INDEX", None)
            if self._app and self._app.voice:
                self._app.voice.microphone_device_index = None
                self._app.voice._ambient_rms = 35.0
            return {"message": "Microphone: Windows System Default"}
        try:
            idx = int(val)
        except ValueError:
            return {"error": f"Invalid microphone index: {val}"}
        self._mic_device = str(idx)
        os.environ["MIC_DEVICE_INDEX"] = str(idx)
        if self._app and self._app.voice:
            self._app.voice.microphone_device_index = idx
            self._app.voice._ambient_rms = 35.0
        return {"message": f"Microphone switched to device #{idx}"}

    def _set_personality(self, personality):
        self._personality = personality
        if self._app and hasattr(self._app, 'ai') and hasattr(self._app.ai, 'personality'):
            self._app.ai.personality = personality
        return {"message": f"Personality set to: {personality}"}

    def _set_ai_mode(self, mode):
        clean_mode = str(mode or "auto").strip().lower()
        if clean_mode not in {"auto", "ollama", "groq"}:
            return {"error": f"Unsupported AI mode: {clean_mode}"}

        self._ai_mode = clean_mode
        os.environ["AI_PROVIDER"] = clean_mode
        self._save_env_key("AI_PROVIDER", clean_mode)

        ai_label = f"Mode: {clean_mode}"
        if self._app and hasattr(self._app, "ai"):
            self._app.ai.mode = clean_mode
            if hasattr(self._app, "validate_runtime_config"):
                status = self._app.validate_runtime_config()
                ai_label = self._format_ai_label(status)
                self._js(f"applyAiStatus('{self._escape_js(ai_label)}')")
            if clean_mode in {"auto", "ollama"}:
                self._warmup_ollama_async()

        return {"message": f"AI brain mode: {clean_mode} ({ai_label})", "ai_status": ai_label}

    def _set_robot_ip(self, raw_ip):
        clean_ip = str(raw_ip or "").strip()
        clean_ip = clean_ip.replace("http://", "").replace("https://", "").strip().rstrip("/")
        if not clean_ip:
            return {"error": "Robot IP cannot be empty"}

        self._robot_ip = clean_ip
        os.environ["SESAME_ROBOT_IP"] = clean_ip
        self._save_env_key("SESAME_ROBOT_IP", clean_ip)

        if self._app:
            self._app.robot = SesameRobotController(clean_ip)
            threading.Thread(target=self._check_connection, daemon=True).start()

        self._js(f"applyIpAddress('{self._escape_js(clean_ip)}')")
        return {"message": f"Robot IP updated to {clean_ip} (saved to .env)", "ip": clean_ip}


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
        background_color="#FAF7F2",
        text_select=False,
    )

    api._set_window(window)

    def on_loaded():
        """Called when the webview window is ready."""
        print("[INFO] Webview loaded; initializing backend")
        # Initialize backend in background thread
        threading.Thread(target=api._initialize_backend, daemon=True).start()

    def on_closed():
        api._closing = True
        if api._app and api._app.voice:
            api._app.voice.stop_listening()
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

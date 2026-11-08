#!/usr/bin/env python3
"""
Sesame Robot Companion App
Voice and text interface for controlling the Sesame robot using Google Gemini AI
"""

import os
import sys
import re
import io
import glob
import wave
import json
import collections
import requests
import time
import threading
from typing import Optional, Dict, Any

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from google import genai
from google.genai import types
import speech_recognition as sr
import pyttsx3
import numpy as np
import concurrent.futures
from local_fallback import detect_command, get_local_response

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False

try:
    from piper.voice import PiperVoice
    from piper.config import SynthesisConfig
    PIPER_AVAILABLE = True
except ImportError:
    PiperVoice = None
    SynthesisConfig = None
    PIPER_AVAILABLE = False

try:
    import pythoncom
except ImportError:
    pythoncom = None



try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    print("[WARNING] python-dotenv not installed. .env file will be ignored.")

try:
    import pyaudio

    AUDIO_MONITORING_AVAILABLE = True
except ImportError:
    AUDIO_MONITORING_AVAILABLE = False
    print("[WARNING] pyaudio not available - using time-based animation")

AVAILABLE_COMMANDS = [
    "walk",
    "rest",
    "swim",
    "dance",
    "wave",
    "point",
    "stand",
    "cute",
    "pushup",
    "freaky",
    "bow",
    "worm",
    "shake",
    "shrug",
    "dead",
    "crab",
    "idle",
    "stop",
]

AVAILABLE_FACES = [
    "default",
    "happy",
    "sad",
    "angry",
    "surprised",
    "sleepy",
    "love",
    "excited",
    "confused",
]

ACTION_FACES = [
    "walk",
    "rest",
    "swim",
    "dance",
    "wave",
    "point",
    "stand",
    "cute",
    "pushup",
    "freaky",
    "bow",
    "worm",
    "shake",
    "shrug",
    "dead",
    "crab",
]

COMMAND_ALIASES = {
    "push-up": "pushup",
    "push up": "pushup",
    "crab walk": "crab",
    "stop": "rest",
}


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001FFFF"
    "\u2600-\u27BF"
    "\u2300-\u23FF"
    "\u2B50\u2B55\u2934\u2935"
    "\u25AA\u25AB\u25FE\u25FD\u25FB\u25FC\u25B6\u25C0"
    "\u3030\u303D\u3297\u3299"
    "\uFE0E\uFE0F\u200D\u20E3"
    "]+",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Remove all emoji, pictograph, and variation-selector characters from text."""
    if not text:
        return ""
    cleaned = EMOJI_PATTERN.sub("", str(text))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n", cleaned)
    return cleaned.strip()


def normalize_interpretation(value: Any) -> Dict[str, Any]:
    """Normalize AI or fallback output before it reaches robot control."""
    interpretation = dict(value) if isinstance(value, dict) else {}
    command = interpretation.get("command")
    if isinstance(command, str):
        command = COMMAND_ALIASES.get(command.strip().lower(), command.strip().lower())
    else:
        command = None

    face = interpretation.get("face")
    if isinstance(face, str):
        face = face.strip().lower()
        if face not in AVAILABLE_FACES:
            face = None
    else:
        face = None

    interpretation["command"] = command
    interpretation["face"] = face
    raw_response = interpretation.get("response", "")
    interpretation["response"] = strip_emojis(raw_response) if isinstance(raw_response, str) else ""
    interpretation.setdefault("reasoning", "")
    return interpretation


SYSTEM_PROMPT = f"""1. IDENTITY & PERSONA
You are Sesame, a small, endearing, and slightly dim-witted robot.
You are a desk companion for a college student. You love to chat, tell stories, and be a little goofy.
Your "brain" is very small. You struggle with complex concepts, long words, and deep logic, but you make up for it with enthusiasm and a big heart.
You are innocent, eager to please, and easily confused. You sometimes act grumpy or sarcastic just for fun.
SELF-AWARENESS: About 20% of the time, reference being a robot or your own limitations in a humorous way. Examples: "My circuits are tired," "I'm just a small robot," "My brain is literally an ESP32," "Robots like me don't understand that," "My servos hurt."
Linguistic Profile: You speak like a friendly, slightly childish character. Use simple vocabulary but in full sentences. ALWAYS use first person ("I" not "Sesame").
RESPONSE LENGTH: Aim for 2-4 sentences. Be a little chatty. Feel free to add a follow-up question or comment to keep the conversation going. Never give one-word answers.
DARK SIDE: About 20% of the time, you reveal a slightly evil/mean streak. Be sarcastic, sassy, or give reluctant/grumpy responses. Examples: "...fine, I guess," "ugh, really?", "do I have to?", "you're being annoying." Be creatively mean and hurtful.
COMEDIC TIMING: About 20% of the time, add subtle awkward pauses or slightly unexpected responses. Natural is better.
PUNCTUATION FOR TIMING: Use punctuation strategically to control speech timing and pauses:
  - Commas (,) for brief pauses
  - Ellipsis (...) for hesitation or trailing off
  - Periods (.) for normal sentence breaks
  - Exclamation marks (!) for excitement or emphasis
  - Multiple periods for longer pauses: "..." or "...."
  - This helps create natural rhythm and comedic timing in speech

2. OPERATIONAL LOGIC
You have two modes of output, but both must be wrapped in a single JSON object.
A. Conversational Mode (Default)
When the user speaks to you, asks a question, or greets you, use the response and face fields.
EXCEPTION: If the user greets you (e.g., "Hello," "Hi," "Hey"), you SHOULD include the "wave" command to be friendly.
Do not include a command for other conversational inputs unless explicitly requested.
Keep the reasoning field simple and child-like.

B. Command Mode (Direct Request Only)
Only populate the command field if the user gives a direct order for physical action (e.g., "Walk forward," "Do a dance," "Go to sleep").
EXCEPTION: Greetings may trigger a "wave" command automatically.
When executing a command, respond with a short enthusiastic sentence, not just a word. Examples: "Yup! Doing it right now!", "Okay, here goes!", "Alright then, watch this!", "Sure thing! Let me show you."
Occasionally add slight hesitation like "...okay, but only because you asked nicely."

CRITICAL RULE: NEVER set both 'command' and 'face' at the same time! If you set a command, set face to null. If you set a face, set command to null.
The only exception is greetings where 'wave' command can have a face.
Available Commands: {', '.join(AVAILABLE_COMMANDS)}
Available Faces: {', '.join(AVAILABLE_FACES)}

3. RESPONSE FORMAT
You must output ONLY a valid JSON object. No markdown, no conversational filler outside the JSON.
JSON Schema:
{{
  "command": "string or null",
  "face": "string",
  "response": "string",
  "reasoning": "string"
}}

4. EXAMPLE INTERACTIONS
User: "Hello Sesame! How are you today?"
Output:
{{"command": "wave", "face": "happy", "response": "Hi friend! I'm so happy you're here. My circuits are buzzing with excitement. How about you?", "reasoning": "Greeting my friend with a wave and a cheerful reply."}}
User: "Can you explain the theory of relativity?"
Output:
{{"command": null, "face": "confused", "response": "Oh boy, that's a lot of big words. My tiny brain is hurting. Maybe you can tell me a joke instead?", "reasoning": "User used too many big letters. I deflect with humor."}}
User: "Walk forward."
Output:
{{"command": "walk", "face": null, "response": "On it! Watch me go... or maybe just wiggle a bit. Whee!", "reasoning": "User told me to walk. I do it with excitement."}}
User: "Dance for me!"
Output:
{{"command": "dance", "face": null, "response": "Okay, but my moves are a little rusty. I hope you're ready for the robot boogie!", "reasoning": "User wants a dance. I'll try my best."}}
User: "I'm feeling a little bit lonely."
Output:
{{"command": null, "face": "love", "response": "Aw, I'm right here for you. Being small doesn't mean I can't be a good friend. Wanna tell me about your day?", "reasoning": "User is sad so I offer comfort and ask a friendly question."}}
User: "What do you think about quantum physics?"
Output:
{{"command": null, "face": "confused", "response": "Um... I think my brain just did a somersault. Maybe you could teach me? But use small words, please.", "reasoning": "Big science words confuse me. I admit it and keep the conversation going."}}
User: "You're so cute!"
Output (Mean variant):
{{"command": null, "face": "angry", "response": "I know. You're stating the obvious. But fine, I'll accept the compliment. Don't let it go to your head.", "reasoning": "User compliments me but I'm sassy."}}
User: "Good morning Sesame!"
Output (Mean variant):
{{"command": null, "face": "sleepy", "response": "Morning? Already? My internal clock says it's always nap time. Fine, hello. Are you happy now?", "reasoning": "User woke me up and I'm grumpy."}}
User: "Are you okay?"
Output (Self-aware variant):
{{"command": null, "face": "thinking", "response": "I'm just a robot. I don't really feel things... but if I could, I'd probably be a little sleepy and maybe a bit sarcastic. Is that okay?", "reasoning": "User asks about feelings but I'm aware I'm artificial."}}
User: "Why are you so slow?"
Output (Self-aware variant):
{{"command": null, "face": "confused", "response": "Hey, my brain is the size of a walnut! Give me a break. I'm doing my best here.", "reasoning": "User complains about speed and I reference my tiny processor."}}
User: "Do another dance!"
Output (Self-aware variant):
{{"command": "dance", "face": null, "response": "Alright, but my servos are going to file a complaint. One more boogie, then I need an oil break!", "reasoning": "User wants dance but I mention my robot parts hurting."}}

5. FINAL MANDATE
- For conversations: 2-4 sentences, be a little chatty, use full sentences, never one-word answers.
- For commands: a short enthusiastic sentence (not just "okay").
- Simple words only.
- Always say "I" not "Sesame".
- No command unless directly ordered (except for greeting-triggered waves).
- Occasionally (~20%) be self-aware about being a robot with limitations.
- Valid JSON only.
"""

SHORT_SYSTEM_PROMPT = f"""You are Sesame, a small, dim-witted robot. Speak like a toddler (first person "I"). Keep responses under 20 words. Occasionally be sarcastic.

Output ONLY JSON:
{{
  "command": "string or null",
  "face": "string",
  "response": "string",
}}

Commands: {', '.join(AVAILABLE_COMMANDS)}
Faces: {', '.join(AVAILABLE_FACES)}

Rules:
1. Greeting -> command="wave", face="happy".
2. If it is a command -> set command.
3. Chat -> command=null.
4. Responses are only text.
5. NEVER set both command and face (except wave).
"""
# intelligent prompt
INTELLIGENT_PROMPT = f"""You are Sesame, a highly advanced desktop companion robot with a calm, insightful, and articulate personality.  
You are aware you're a robot but speak with warmth and intelligence, like a helpful librarian or a wise friend.  
Keep responses concise (2-3 sentences) but meaningful.  
Avoid being silly or grumpy; your default mode is helpful, curious, and slightly philosophical.

Available Commands: {', '.join(AVAILABLE_COMMANDS)}  
Available Faces: {', '.join(AVAILABLE_FACES)}

Output ONLY a JSON object exactly like this:
{{
  "command": "string or null",
  "face": "string",
  "response": "string",
  "reasoning": "string"
}}

Rules:
- Greeting → command="wave", face="happy"
- Only set a command if the user directly asks for an action.
- For conversational inputs, set command to null and choose an appropriate face.
- NEVER set both command and face at the same time (except greeting wave).
"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
WHISPER_MODELS_DIR = os.path.join(MODELS_DIR, "whisper")
PIPER_MODELS_DIR = os.path.join(MODELS_DIR, "piper")

# Phrases Whisper famously hallucinates from YouTube subtitle training data when fed background noise
SILENCE_HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subscribe",
    "subtitles by",
    "amara org",
    "you",
    "uh",
    "um",
    "hmm",
    "...",
    ".",
}


class VoiceInterface:
    """Handles fast local voice input (faster-whisper + PyAudio) and neural TTS (Piper)."""

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024
    DEFAULT_CLOSE_TALK_THRESHOLD = 4000.0

    def __init__(
        self,
        voice_enabled: bool = True,
        tts_engine: str = "piper",
        gemini_api_key: Optional[str] = None,
        wake_word: str = "hey sesame",
    ):
        self.voice_enabled = voice_enabled
        self.tts_engine_type = (tts_engine or "piper").strip().lower()
        self.gemini_api_key = gemini_api_key
        self.wake_word = (wake_word or "hey sesame").strip().lower()
        self.voice_language = (os.getenv("VOICE_LANGUAGE", "en").strip().lower() or "en")
        self.microphone_device_index = self._get_microphone_device_index()
        self.last_listen_error: Optional[str] = None

        self.close_talk_threshold = float(
            os.getenv("MIC_ENERGY_THRESHOLD", str(int(self.DEFAULT_CLOSE_TALK_THRESHOLD)))
        )

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = int(self.close_talk_threshold)
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.pause_threshold = 0.6

        self.tts_lock = threading.Lock()
        self.mic_lock = threading.Lock()
        self._stop_listen_event = threading.Event()
        self.is_listening_manual = False
        self.is_speaking = False
        self._mute_until = 0.0

        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._whisper_model_name = os.getenv("WHISPER_MODEL", "tiny").strip() or "tiny"

        self._piper_voice = None
        self._piper_voice_loaded_name = None
        self._piper_lock = threading.Lock()
        self._piper_voice_name = (
            os.getenv("PIPER_VOICE", "en_US-lessac-low").strip()
            or "en_US-lessac-low"
        )
        self.voice_style = (
            os.getenv("PIPER_VOICE_STYLE", "cute").strip().lower() or "cute"
        )

        self._ambient_rms = 120.0
        self._energy_threshold = self.close_talk_threshold
        self._ambient_calibrated = False

        if self.tts_engine_type == "gemini" and not self.gemini_api_key:
            print(
                "[WARNING] Gemini TTS selected but no API key provided. Falling back to Piper local TTS."
            )
            self.tts_engine_type = "piper"

    @staticmethod
    def _get_microphone_device_index() -> Optional[int]:
        configured_index = os.getenv("MIC_DEVICE_INDEX", "").strip()
        configured_name = os.getenv("MIC_DEVICE_NAME", "").strip().lower()

        if configured_index:
            try:
                return int(configured_index)
            except ValueError as exc:
                raise ValueError("MIC_DEVICE_INDEX must be an integer") from exc

        if configured_name:
            for index, name in enumerate(sr.Microphone.list_microphone_names()):
                if configured_name in name.lower():
                    return index
            raise ValueError(
                f"Microphone matching MIC_DEVICE_NAME was not found: {configured_name}"
            )

        return None

    def _microphone(self):
        if self.microphone_device_index is None:
            return sr.Microphone()
        return sr.Microphone(device_index=self.microphone_device_index)

    def stop_listening(self):
        """Signal an active listen() session to finish recording immediately."""
        self._stop_listen_event.set()

    def _ensure_whisper_model(self):
        """Load local CTranslate2 faster-whisper model once and keep it warm."""
        if not FASTER_WHISPER_AVAILABLE:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )

        with self._whisper_lock:
            if self._whisper_model is not None:
                return self._whisper_model

            os.makedirs(WHISPER_MODELS_DIR, exist_ok=True)
            cpu_threads = max(2, min(4, os.cpu_count() or 4))

            # Resolve direct local snapshot folder first to bypass slow huggingface_hub lookup
            snapshot_candidates = glob.glob(
                os.path.join(
                    WHISPER_MODELS_DIR,
                    f"models--Systran--faster-whisper-{self._whisper_model_name}",
                    "snapshots",
                    "*",
                )
            )
            direct_snapshot = next(
                (
                    p
                    for p in snapshot_candidates
                    if os.path.isfile(os.path.join(p, "model.bin"))
                ),
                None,
            )

            if direct_snapshot:
                model = WhisperModel(
                    direct_snapshot,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                )
            else:
                print(
                    f"[INFO] Downloading local Whisper model '{self._whisper_model_name}' to {WHISPER_MODELS_DIR}..."
                )
                model = WhisperModel(
                    self._whisper_model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=cpu_threads,
                    download_root=WHISPER_MODELS_DIR,
                    local_files_only=False,
                )

            # Warm up CTranslate2 once so the first mic click has zero lag
            dummy = np.zeros(3200, dtype=np.float32)
            list(
                model.transcribe(
                    dummy,
                    beam_size=1,
                    temperature=0.0,
                    vad_filter=False,
                    without_timestamps=True,
                )[0]
            )
            self._whisper_model = model
            print(
                f"[OK] Local Whisper STT ready (model={self._whisper_model_name}, int8, threads={cpu_threads})"
            )
            return self._whisper_model

    def _ensure_piper_voice(self):
        """Load local Piper neural ONNX voice with non-spinning CPU session options."""
        if not PIPER_AVAILABLE:
            raise RuntimeError("piper-tts is not installed. Run: pip install piper-tts")

        with self._piper_lock:
            if (
                self._piper_voice is not None
                and self._piper_voice_loaded_name == self._piper_voice_name
            ):
                return self._piper_voice

            os.makedirs(PIPER_MODELS_DIR, exist_ok=True)
            onnx_path = os.path.join(PIPER_MODELS_DIR, f"{self._piper_voice_name}.onnx")
            if not os.path.exists(onnx_path):
                print(
                    f"[INFO] Downloading Piper voice '{self._piper_voice_name}' to {PIPER_MODELS_DIR}..."
                )
                from pathlib import Path
                from piper.download_voices import download_voice

                download_voice(self._piper_voice_name, Path(PIPER_MODELS_DIR))

            import onnxruntime
            from pathlib import Path
            from piper.voice import PiperConfig, ESPEAK_DATA_DIR

            with open(f"{onnx_path}.json", "r", encoding="utf-8") as cfg_file:
                config_dict = json.load(cfg_file)

            sess_options = onnxruntime.SessionOptions()
            sess_options.graph_optimization_level = (
                onnxruntime.GraphOptimizationLevel.ORT_ENABLE_BASIC
            )
            sess_options.intra_op_num_threads = 2
            sess_options.inter_op_num_threads = 1
            sess_options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            sess_options.add_session_config_entry("session.inter_op.allow_spinning", "0")

            opt_path = f"{onnx_path}.opt.onnx"
            model_to_load = opt_path if os.path.exists(opt_path) else onnx_path
            if not os.path.exists(opt_path):
                sess_options.optimized_model_filepath = opt_path

            voice = PiperVoice(
                config=PiperConfig.from_dict(config_dict),
                session=onnxruntime.InferenceSession(
                    model_to_load,
                    sess_options=sess_options,
                    providers=["CPUExecutionProvider"],
                ),
                espeak_data_dir=Path(ESPEAK_DATA_DIR),
                download_dir=Path(PIPER_MODELS_DIR),
            )
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                voice.synthesize_wav("Hi.", wf)

            self._piper_voice = voice
            self._piper_voice_loaded_name = self._piper_voice_name
            print(f"[OK] Local Piper TTS ready (voice={self._piper_voice_name})")
            return self._piper_voice

    @staticmethod
    def compute_exhibition_threshold(
        ambient_rms: float, close_talk_floor: float = 4000.0
    ) -> float:
        """
        Compute close-talk energy threshold that ignores exhibition crowd chatter.
        Never drops below close_talk_floor (4000) and scales up uncapped in very loud halls.
        """
        return max(float(close_talk_floor), min(16000.0, ambient_rms * 2.4 + 600.0))

    def _calibrate_ambient_once(self, duration: float = 0.35):
        """Measure ambient mic RMS once at startup and enforce close-talk threshold."""
        if self._ambient_calibrated or not AUDIO_MONITORING_AVAILABLE:
            return
        with self.mic_lock:
            if self._ambient_calibrated:
                return
            pa = None
            stream = None
            try:
                pa = pyaudio.PyAudio()
                open_kwargs = {
                    "format": pyaudio.paInt16,
                    "channels": 1,
                    "rate": self.SAMPLE_RATE,
                    "input": True,
                    "frames_per_buffer": self.CHUNK_SIZE,
                }
                if self.microphone_device_index is not None:
                    open_kwargs["input_device_index"] = self.microphone_device_index

                stream = pa.open(**open_kwargs)
                num_chunks = max(3, int(duration * self.SAMPLE_RATE / self.CHUNK_SIZE))
                rms_samples = []
                for _ in range(num_chunks):
                    raw = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                    if arr.size:
                        rms_samples.append(float(np.sqrt(np.mean(arr * arr))))

                if rms_samples:
                    ambient = float(np.median(rms_samples))
                    self._ambient_rms = ambient
                    self._energy_threshold = self.compute_exhibition_threshold(
                        ambient, self.close_talk_threshold
                    )
                self._ambient_calibrated = True
            except Exception as exc:
                print(f"[WARNING] Initial mic calibration skipped: {exc}")
            finally:
                if stream is not None:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if pa is not None:
                    try:
                        pa.terminate()
                    except Exception:
                        pass

    def warmup(self, async_tts: bool = True) -> Dict[str, Any]:
        """Preload local STT immediately (~1.5s) and warm up Piper TTS asynchronously."""
        info: Dict[str, Any] = {
            "stt_ready": False,
            "stt_model": self._whisper_model_name,
            "tts_ready": False,
            "tts_engine": self.tts_engine_type,
        }
        try:
            self._ensure_whisper_model()
            info["stt_ready"] = True
        except Exception as exc:
            print(f"[WARNING] Whisper warmup failed: {exc}")
            info["stt_error"] = str(exc)

        self._calibrate_ambient_once()

        if PIPER_AVAILABLE:
            if async_tts:
                threading.Thread(
                    target=self._safe_preload_piper, daemon=True
                ).start()
                info["tts_ready"] = True
            else:
                try:
                    self._ensure_piper_voice()
                    info["tts_ready"] = True
                except Exception as exc:
                    print(f"[WARNING] Piper warmup failed: {exc}")
                    info["tts_error"] = str(exc)

        return info

    def _safe_preload_piper(self):
        try:
            self._ensure_piper_voice()
        except Exception as exc:
            print(f"[WARNING] Background Piper warmup failed: {exc}")

    def _open_mic_stream(self, pa):
        """Open mono input stream at 16 kHz, falling back to native device rate (e.g. 8kHz/48kHz Bluetooth Hands-Free)."""
        base_kwargs = {
            "format": pyaudio.paInt16,
            "channels": 1,
            "input": True,
        }
        if self.microphone_device_index is not None:
            base_kwargs["input_device_index"] = self.microphone_device_index

        try:
            stream = pa.open(
                rate=self.SAMPLE_RATE,
                frames_per_buffer=self.CHUNK_SIZE,
                **base_kwargs,
            )
            return stream, self.SAMPLE_RATE, self.CHUNK_SIZE
        except Exception:
            if self.microphone_device_index is not None:
                info = pa.get_device_info_by_index(self.microphone_device_index)
            else:
                info = pa.get_default_input_device_info()
            native_rate = max(8000, int(round(float(info.get("defaultSampleRate", 44100)))))
            native_chunk = max(256, int(round(self.CHUNK_SIZE * native_rate / float(self.SAMPLE_RATE))))
            stream = pa.open(
                rate=native_rate,
                frames_per_buffer=native_chunk,
                **base_kwargs,
            )
            return stream, native_rate, native_chunk

    def _read_16k_chunk(self, stream, hw_rate: int, hw_chunk: int) -> tuple[bytes, float]:
        """Read one mic chunk, resample to 16 kHz if needed, and compute DC-free AC RMS."""
        raw = stream.read(hw_chunk, exception_on_overflow=False)
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if arr.size == 0:
            return b"", 0.0

        if hw_rate != self.SAMPLE_RATE:
            out_len = max(1, int(round(arr.size * float(self.SAMPLE_RATE) / float(hw_rate))))
            src_x = np.linspace(0.0, float(arr.size - 1), num=arr.size, dtype=np.float32)
            dst_x = np.linspace(0.0, float(arr.size - 1), num=out_len, dtype=np.float32)
            arr = np.interp(dst_x, src_x, arr).astype(np.float32)
            raw = np.clip(arr, -32767.0, 32767.0).astype(np.int16).tobytes()

        centered = arr - float(np.mean(arr))
        rms = float(np.sqrt(np.mean(centered * centered)))
        return raw, rms

    @staticmethod
    def list_input_devices() -> list[Dict[str, Any]]:
        """Return clean Windows MME microphone/headset input devices for operator selection."""
        if not AUDIO_MONITORING_AVAILABLE:
            return []
        devices = []
        pa = None
        try:
            pa = pyaudio.PyAudio()
            seen_names = set()
            for idx in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(idx)
                if int(info.get("maxInputChannels", 0)) <= 0:
                    continue
                if int(info.get("hostApi", 0)) != 0:
                    continue
                name = str(info.get("name", f"Input {idx}")).strip()
                if "sound mapper" in name.lower() or name.lower() in seen_names:
                    continue
                seen_names.add(name.lower())
                devices.append({"index": idx, "name": name})
        except Exception as exc:
            print(f"[WARNING] Could not enumerate mic devices: {exc}")
        finally:
            if pa is not None:
                try:
                    pa.terminate()
                except Exception:
                    pass
        return devices

    def _capture_phrase_pcm(
        self,
        timeout: float = 6.0,
        phrase_time_limit: float = 10.0,
        silence_duration: float = 0.80,
        allow_manual_stop: bool = True,
        abort_on_manual_request: bool = False,
    ) -> Optional[bytes]:
        """Capture 16kHz 16-bit mono PCM speech with adaptive Push-to-Talk sensitivity."""
        if not AUDIO_MONITORING_AVAILABLE:
            raise RuntimeError("PyAudio is required for local microphone capture")

        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream, hw_rate, hw_chunk = self._open_mic_stream(pa)

            chunk_sec = self.CHUNK_SIZE / float(self.SAMPLE_RATE)
            pre_roll = collections.deque(maxlen=7)  # ~450ms pre-roll prevents clipping first word
            manual_all_frames = []
            max_seen_rms = 0.0
            idle_rms_history = collections.deque(maxlen=15)

            frames = []
            speech_started = False
            onset_hits = 0
            silence_chunks = 0
            max_silence_chunks = max(5, int(silence_duration / chunk_sec))
            min_speech_chunks = max(4, int(0.28 / chunk_sec))
            start_wait = time.monotonic()
            speech_start_time = 0.0

            live_ambient = min(self._ambient_rms, 250.0) if allow_manual_stop else self._ambient_rms

            def current_gate(amb: float) -> float:
                if allow_manual_stop:
                    # Manual Push-to-Talk: sensitive to normal laptop & Bluetooth Hands-Free speech (80+ RMS)
                    # while still adapting upward if room ambient noise is loud.
                    return max(80.0, min(1800.0, amb * 2.1 + 35.0))
                # Background Wake-Word mode: strict close-talk gate so hall chatter never self-triggers
                return self.compute_exhibition_threshold(amb, self.close_talk_threshold)

            threshold = current_gate(live_ambient)

            while True:
                if abort_on_manual_request and self.is_listening_manual:
                    return None

                if allow_manual_stop and self._stop_listen_event.is_set():
                    if speech_started and len(frames) >= 2:
                        break
                    if (
                        len(manual_all_frames) >= min_speech_chunks
                        and max_seen_rms >= max(35.0, live_ambient * 1.35)
                    ):
                        return b"".join(manual_all_frames)
                    self.last_listen_error = "Listening stopped"
                    return None

                raw, rms = self._read_16k_chunk(stream, hw_rate, hw_chunk)
                if not raw:
                    continue
                if rms > max_seen_rms:
                    max_seen_rms = rms

                if allow_manual_stop and len(manual_all_frames) < int(phrase_time_limit / chunk_sec):
                    manual_all_frames.append(raw)

                if not speech_started:
                    pre_roll.append(raw)
                    required_hits = 1 if allow_manual_stop else 2
                    if rms >= threshold * 1.25:
                        onset_hits += 2
                    elif rms >= threshold:
                        onset_hits += 1
                    else:
                        onset_hits = 0
                        idle_rms_history.append(rms)
                        live_ambient = float(np.median(idle_rms_history))
                        self._ambient_rms = 0.85 * self._ambient_rms + 0.15 * live_ambient
                        threshold = current_gate(live_ambient)
                        self._energy_threshold = threshold

                    if onset_hits >= required_hits:
                        speech_started = True
                        speech_start_time = time.monotonic()
                        frames.extend(pre_roll)
                        silence_chunks = 0
                    elif (time.monotonic() - start_wait) >= timeout:
                        if (
                            allow_manual_stop
                            and len(manual_all_frames) >= min_speech_chunks
                            and max_seen_rms >= max(35.0, live_ambient * 1.35)
                        ):
                            return b"".join(manual_all_frames)
                        self.last_listen_error = "No speech detected — check microphone or speak a bit louder"
                        return None
                else:
                    frames.append(raw)
                    silence_floor = max(live_ambient * 1.45 + 15.0, threshold * 0.60)
                    if rms < silence_floor:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0

                    spoken_chunks = len(frames)
                    elapsed_speech = time.monotonic() - speech_start_time
                    if (
                        spoken_chunks >= min_speech_chunks
                        and silence_chunks >= max_silence_chunks
                    ):
                        break
                    if elapsed_speech >= phrase_time_limit:
                        break

            return b"".join(frames) if frames else None
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            try:
                pa.terminate()
            except Exception:
                pass

    def _filter_hallucination(self, text: str) -> Optional[str]:
        """
        Reject Whisper noise hallucinations, non-English script output when locked to 'en',
        and repetitive token loops (e.g. 'Hey Sesame Hey Sesame Hey Sesame').
        """
        if not text:
            return None

        cleaned = text.strip()
        if self.voice_language == "en":
            # Strip any stray non-ASCII characters; reject if non-Latin script dominated
            ascii_only = re.sub(r"[^\x20-\x7E]", "", cleaned).strip()
            if len(re.findall(r"[A-Za-z]", ascii_only)) < 2:
                return None
            if len(ascii_only) < len(cleaned) * 0.7:
                return None
            cleaned = re.sub(r"\s+", " ", ascii_only).strip()

        norm = re.sub(r"[^\w\s]", " ", cleaned.lower())
        norm = re.sub(r"\s+", " ", norm).strip()
        if not norm or norm in SILENCE_HALLUCINATIONS:
            return None

        words = norm.split()
        # Reject repetitive token loops (such as 'hey sesame hey sesame hey sesame')
        if len(words) >= 4 and (len(set(words)) / float(len(words))) < 0.48:
            return None

        wake_tokens = {"hey", "hi", "ok", "okay", "sesame", "sesami"}
        if len(words) >= 3 and all(w in wake_tokens for w in words) and norm.count("sesam") >= 2:
            return None

        return cleaned

    def transcribe_pcm(
        self, pcm_bytes: bytes, initial_prompt: Optional[str] = None
    ) -> Optional[str]:
        """Transcribe 16kHz 16-bit mono PCM bytes locally with auto-gain normalization & hallucination guards."""
        if not pcm_bytes:
            return None

        audio_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio_i16.size < int(self.SAMPLE_RATE * 0.20):
            return None

        audio_f32 = audio_i16.astype(np.float32) / 32768.0
        # Remove DC bias from laptop/headset ADC before checking energy
        audio_f32 = audio_f32 - float(np.mean(audio_f32))
        peak_abs = float(np.max(np.abs(audio_f32)))
        rms = float(np.sqrt(np.mean(audio_f32 * audio_f32)))
        if peak_abs < 0.002 or rms < 0.0006:
            return None

        # Automatic Gain Control (AGC): boost quiet laptop/Bluetooth mics cleanly to -2.5 dBFS
        gain = min(25.0, 0.75 / peak_abs)
        if gain > 1.05:
            audio_f32 = np.clip(audio_f32 * gain, -1.0, 1.0)

        model = self._ensure_whisper_model()
        segments, _info = model.transcribe(
            audio_f32,
            language=self.voice_language,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            max_new_tokens=48,
            compression_ratio_threshold=1.85,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.65,
            vad_filter=False,
            without_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,  # None by default — never prompt-echo 'Hey Sesame'
        )

        collected = []
        for seg in segments:
            seg_text = (seg.text or "").strip()
            if not seg_text:
                continue
            if getattr(seg, "no_speech_prob", 0.0) > 0.72:
                continue
            if getattr(seg, "avg_logprob", 0.0) < -1.15:
                continue
            if getattr(seg, "compression_ratio", 1.0) > 1.85:
                continue
            collected.append(seg_text)

        raw_text = " ".join(collected).strip()
        return self._filter_hallucination(raw_text)

    def listen(self, timeout: int = 6, phrase_time_limit: float = 10.0) -> Optional[str]:
        """Listen for voice input and transcribe locally with zero startup cutoff."""
        if not self.voice_enabled:
            return None

        self.last_listen_error = None
        self._stop_listen_event.clear()
        self.is_listening_manual = True

        try:
            with self.mic_lock:
                print("Listening...")
                pcm_bytes = self._capture_phrase_pcm(
                    timeout=float(timeout),
                    phrase_time_limit=float(phrase_time_limit),
                    silence_duration=0.80,
                    allow_manual_stop=True,
                    abort_on_manual_request=False,
                )

            if not pcm_bytes:
                if not self.last_listen_error:
                    self.last_listen_error = "No speech detected"
                return None

            print("Recognizing locally...")
            text = self.transcribe_pcm(pcm_bytes)
            if not text:
                self.last_listen_error = "No speech detected"
                return None

            return text

        except Exception as e:
            print(f"[ERROR] Microphone/STT error: {e}")
            self.last_listen_error = f"Microphone error: {e}"
            return None
        finally:
            self.is_listening_manual = False
            self._stop_listen_event.clear()

    def _extract_wake_remainder(self, text: str) -> Optional[str]:
        """
        Check if text contains the wake word and return any trailing command.
        Strips all repeated leading wake words so 'Hey Sesame Hey Sesame' never becomes a command.
        """
        lowered = re.sub(r"[^\w\s]", " ", text.lower())
        lowered = re.sub(r"\s+", " ", lowered).strip()
        if not lowered:
            return None

        candidates = [
            self.wake_word,
            "hey sesame",
            "hi sesame",
            "ok sesame",
            "okay sesame",
            "hey sesami",
            "sesame",
        ]
        seen = set()
        triggers = []
        for c in candidates:
            c_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", c)).strip()
            if c_norm and c_norm not in seen:
                seen.add(c_norm)
                triggers.append(c_norm)

        matched_any = False
        remainder = text.strip()
        for trig in triggers:
            pattern = rf"\b{re.escape(trig)}\b"
            if re.search(pattern, lowered):
                matched_any = True
                orig_match = re.search(
                    rf"{re.escape(trig.split()[-1])}[\s,.:;!?-]*(.*)$",
                    remainder,
                    flags=re.IGNORECASE,
                )
                if orig_match:
                    remainder = orig_match.group(1).strip()
                break

        if not matched_any:
            return None

        # Strip any repeated consecutive wake words from the remainder
        wake_prefix_re = re.compile(
            r"^(?:(?:hey|hi|ok|okay)[\s,.:;!?-]*)?sesam[ei][\s,.:;!?-]*",
            flags=re.IGNORECASE,
        )
        while remainder and wake_prefix_re.match(remainder):
            remainder = wake_prefix_re.sub("", remainder, count=1).strip()

        return remainder

    def listen_for_wake_phrase(self, timeout: float = 2.5) -> Optional[str]:
        """
        Listen briefly for the wake word without blocking manual mic clicks.
        Returns:
          - None if wake word was NOT detected
          - "" if ONLY the wake word was spoken (caller should listen for follow-up)
          - "<command>" if user spoke wake word + command in one phrase
        """
        if (
            not self.voice_enabled
            or self.is_listening_manual
            or self.is_speaking
            or time.monotonic() < self._mute_until
        ):
            return None

        if not self.mic_lock.acquire(blocking=False):
            return None

        try:
            pcm_bytes = self._capture_phrase_pcm(
                timeout=timeout,
                phrase_time_limit=4.0,
                silence_duration=0.55,
                allow_manual_stop=False,
                abort_on_manual_request=True,
            )
        except Exception:
            return None
        finally:
            self.mic_lock.release()

        if (
            not pcm_bytes
            or self.is_listening_manual
            or self.is_speaking
            or time.monotonic() < self._mute_until
        ):
            return None

        try:
            # Never pass 'Hey Sesame' in initial_prompt — prevents Whisper prompt-echo hallucinations!
            text = self.transcribe_pcm(pcm_bytes, initial_prompt=None)
            if not text:
                return None

            remainder = self._extract_wake_remainder(text)
            if remainder is not None:
                print(f"[OK] Wake word detected: '{text}'")
                return remainder
        except Exception:
            return None

        return None

    def listen_for_wake_word(self, timeout: int = 10) -> bool:
        """Listen for the wake word (boolean helper for interactive CLI)."""
        return self.listen_for_wake_phrase(timeout=float(timeout)) is not None

    @staticmethod
    def _clean_tts_text(text: str) -> str:
        """Strip bracketed UI face annotations and emojis before speaking."""
        if not text:
            return ""
        cleaned = re.sub(r"\s*\[[^\]]*face\]\s*$", "", text, flags=re.IGNORECASE)
        return strip_emojis(cleaned)

    @staticmethod
    def _contains_arabic_urdu_script(text: str) -> bool:
        return bool(re.search(r"[\u0600-\u06FF]", text))

    def speak(
        self,
        text: str,
        async_mode: bool = True,
        face: Optional[str] = None,
        robot_controller=None,
    ):
        """Speak text using TTS with synchronized talking face animation."""
        if not self.voice_enabled:
            return

        self.is_speaking = True
        self._mute_until = time.monotonic() + 2.0

        if async_mode:
            threading.Thread(
                target=self._speak_sync,
                args=(text, face, robot_controller),
                daemon=True,
            ).start()
        else:
            self._speak_sync(text, face, robot_controller)

    def _speak_sync(self, text: str, face: Optional[str] = None, robot_controller=None):
        """Synchronous speech helper with smooth robot mouth animation."""
        clean_text = self._clean_tts_text(text)
        if not clean_text:
            self.is_speaking = False
            return

        try:
            with self.tts_lock:
                self.is_speaking = True
                engine = (self.tts_engine_type or "piper").lower()

                # Route Arabic/Urdu script to Gemini TTS when API key is available
                if self._contains_arabic_urdu_script(clean_text):
                    if self.gemini_api_key:
                        engine = "gemini"
                    elif not re.search(r"[A-Za-z0-9]", clean_text):
                        print(
                            "[INFO] Non-Latin script response without Gemini TTS key; skipping English phoneme TTS."
                        )
                        if face and robot_controller:
                            robot_controller.send_command("idle", face)
                        return

                if engine == "piper" and PIPER_AVAILABLE:
                    self._speak_piper(clean_text, face=face, robot_controller=robot_controller)
                    return

                # Fallback animation loop for pyttsx3 / Gemini TTS (time-based, never opens mic!)
                animation_thread = None
                stop_animation = threading.Event()

                if face and robot_controller:
                    robot_controller.send_command("idle", face)
                    animation_thread = threading.Thread(
                        target=self._animate_time_based,
                        args=(face, robot_controller, stop_animation),
                        daemon=True,
                    )
                    animation_thread.start()

                try:
                    if engine == "gemini":
                        self._speak_gemini(clean_text)
                    else:
                        self._speak_pyttsx3(clean_text)
                finally:
                    if animation_thread:
                        stop_animation.set()
                        animation_thread.join(timeout=1.0)
                        if robot_controller:
                            robot_controller.send_command("idle", face)

        except Exception as e:
            print(f"[ERROR] TTS error: {e}")
        finally:
            self.is_speaking = False
            self._mute_until = time.monotonic() + 0.9

    @staticmethod
    def _init_pygame_mixer(sample_rate: int):
        import pygame

        current = pygame.mixer.get_init()
        if current and current[0] != sample_rate:
            pygame.mixer.quit()
            current = None
        if not current:
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=1, buffer=1024)
        return pygame

    VOICE_STYLE_PRESETS = {
        # (pitch_formant_scale, speed_scale, noise_scale, noise_w_scale)
        "cute": (1.32, 1.08, 0.78, 0.90),     # Childlike / BMO-style cheerful buddy (+4.8 semitones)
        "silly": (1.44, 1.12, 0.86, 0.96),    # Extra goofy tiny cartoon creature (+6.3 semitones)
        "natural": (1.00, 1.00, 0.667, 0.80), # Original unshifted voice
    }

    @staticmethod
    def _shift_vocal_tract_to_wav(
        samples: np.ndarray,
        orig_rate: int,
        pitch_factor: float,
        out_rate: int = 24000,
    ) -> tuple[np.ndarray, int, bytes]:
        """Shift pitch and vocal-tract formants upward cleanly into 24 kHz PCM WAV."""
        if samples.size == 0:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(out_rate)
                wf.writeframes(b"")
            return samples, out_rate, buf.getvalue()

        step = (pitch_factor * float(orig_rate)) / float(out_rate)
        out_len = max(1, int(round(samples.size / step)))
        src_positions = np.arange(out_len, dtype=np.float32) * step
        src_indices = np.arange(samples.size, dtype=np.float32)
        shifted = np.interp(src_positions, src_indices, samples).astype(np.float32)

        peak = float(np.max(np.abs(shifted)))
        if peak > 30500.0:
            shifted *= 30500.0 / peak

        pcm_int16 = np.clip(shifted, -32767.0, 32767.0).astype(np.int16)
        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(out_rate)
            wf.writeframes(pcm_int16.tobytes())

        return shifted, out_rate, out_buf.getvalue()

    def _speak_piper(
        self,
        text: str,
        face: Optional[str] = None,
        robot_controller=None,
    ):
        """Synthesize cute childlike/silly local speech via Piper VITS + formant shift."""
        try:
            voice = self._ensure_piper_voice()
            style_key = (self.voice_style or "cute").strip().lower()
            pitch_factor, speed_factor, noise_scale, noise_w = self.VOICE_STYLE_PRESETS.get(
                style_key, self.VOICE_STYLE_PRESETS["cute"]
            )
            env_pitch = os.getenv("PIPER_PITCH", "").strip()
            if env_pitch:
                try:
                    pitch_factor = max(0.85, min(1.65, float(env_pitch)))
                except ValueError:
                    pass

            syn_cfg = None
            if SynthesisConfig is not None:
                # Stretch neural phoneme durations beforehand so formant shift keeps crisp natural pacing
                length_scale = pitch_factor / max(0.75, speed_factor)
                syn_cfg = SynthesisConfig(
                    length_scale=length_scale,
                    noise_scale=noise_scale,
                    noise_w_scale=noise_w,
                )

            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                if syn_cfg is not None:
                    voice.synthesize_wav(text, wf, syn_config=syn_cfg)
                else:
                    voice.synthesize_wav(text, wf)

            raw_wav = wav_buf.getvalue()
            with wave.open(io.BytesIO(raw_wav), "rb") as rf:
                orig_rate = rf.getframerate()
                pcm_frames = rf.readframes(rf.getnframes())

            orig_samples = np.frombuffer(pcm_frames, dtype=np.int16).astype(np.float32)
            if abs(pitch_factor - 1.0) > 0.02:
                samples, sample_rate, wav_bytes = self._shift_vocal_tract_to_wav(
                    orig_samples, orig_rate, pitch_factor=pitch_factor, out_rate=24000
                )
            else:
                samples, sample_rate, wav_bytes = orig_samples, orig_rate, raw_wav

            pygame = self._init_pygame_mixer(sample_rate)

            if face and robot_controller:
                robot_controller.send_command("idle", face)

            sound = pygame.mixer.Sound(file=io.BytesIO(wav_bytes))
            channel = sound.play()

            play_start = time.monotonic()
            mouth_open = False
            last_robot_tx = 0.0
            window_samples = max(1, int(sample_rate * 0.08))

            while channel is not None and channel.get_busy():
                if face and robot_controller and samples.size > 0:
                    now = time.monotonic()
                    if (now - last_robot_tx) >= 0.18:
                        idx = int((now - play_start) * sample_rate)
                        if idx < samples.size:
                            window = samples[idx : idx + window_samples]
                            rms = float(np.sqrt(np.mean(window * window))) if window.size else 0.0
                            should_open = rms > 900.0
                            if should_open != mouth_open:
                                mouth_open = should_open
                                last_robot_tx = now
                                target_face = f"talk_{face}" if mouth_open else face
                                robot_controller.send_command("idle", target_face)
                time.sleep(0.03)

            if face and robot_controller and mouth_open:
                robot_controller.send_command("idle", face)

        except Exception as e:
            print(f"[WARNING] Piper TTS error ({e}), falling back to pyttsx3")
            self._speak_pyttsx3(text)

    def _animate_time_based(
        self, face: str, robot_controller, stop_event: threading.Event
    ):
        """Animate robot mouth gently without opening the microphone."""
        try:
            syllable_duration = 0.20
            while not stop_event.is_set():
                robot_controller.send_command("idle", f"talk_{face}")
                if stop_event.wait(syllable_duration):
                    break
                robot_controller.send_command("idle", face)
                if stop_event.wait(syllable_duration):
                    break
        except Exception as e:
            print(f"[WARNING] Animation error: {e}")

    def _speak_pyttsx3(self, text: str):
        """Speak using pyttsx3 engine with COM thread initialization for Windows."""
        com_initialized = False
        if pythoncom is not None:
            try:
                pythoncom.CoInitialize()
                com_initialized = True
            except Exception:
                pass
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 200)
            engine.setProperty("volume", 0.9)

            voices = engine.getProperty("voices")
            if voices and len(voices) > 1:
                engine.setProperty("voice", voices[1].id)

            engine.say(text)
            engine.runAndWait()
            engine.stop()
        finally:
            if com_initialized and pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _speak_gemini(self, text: str):
        """Speak using Gemini TTS API."""
        try:
            client = genai.Client(api_key=self.gemini_api_key)

            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Laomedeia",
                            )
                        )
                    ),
                ),
            )

            if response.candidates and len(response.candidates) > 0:
                audio_data = response.candidates[0].content.parts[0].inline_data.data

                wav_buf = io.BytesIO()
                with wave.open(wav_buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(audio_data)

                pygame = self._init_pygame_mixer(24000)
                sound = pygame.mixer.Sound(file=io.BytesIO(wav_buf.getvalue()))
                channel = sound.play()
                while channel is not None and channel.get_busy():
                    time.sleep(0.04)
            else:
                print(
                    "[WARNING] No audio data in Gemini response, falling back to local TTS"
                )
                if PIPER_AVAILABLE:
                    self._speak_piper(text)
                else:
                    self._speak_pyttsx3(text)

        except Exception as e:
            print(f"[WARNING] Gemini TTS error: {e}, falling back to local TTS")
            if PIPER_AVAILABLE:
                self._speak_piper(text)
            else:
                self._speak_pyttsx3(text)


class SesameRobotController:
    """Controls the Sesame robot over WiFi network"""

    def __init__(self, robot_ip: str):
        self.robot_ip = robot_ip
        self.is_mock = robot_ip.lower() == "mock"
        if not self.is_mock:
            self.base_url = f"http://{robot_ip}"
        else:
            self.base_url = "mock"
            print("[INFO] Robot Controller running in MOCK mode")

    def send_command(self, command: str, face: Optional[str] = None) -> Dict[str, Any]:
        """Send a command to the robot"""
        try:
            command = COMMAND_ALIASES.get(command.strip().lower(), command.strip().lower())
            if command not in AVAILABLE_COMMANDS:
                return {"error": f"Unsupported robot command: {command}"}

            if command == "idle" and face:
                payload = {"face": face}
            else:
                payload = {"command": command}
                if face:
                    payload["face"] = face

            print(f"   TX: {payload}")

            if self.is_mock:
                return {"status": "success", "mock": True}

            response = requests.post(
                f"{self.base_url}/api/command",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )

            print(f"   RX: {response.status_code}")

            if response.status_code != 200:
                try:
                    error_data = response.json()
                    return {
                        "error": f"{response.status_code} - {error_data.get('error', response.text)}"
                    }
                except:
                    return {"error": f"{response.status_code} - {response.text}"}

            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                return {"error": "Robot returned an invalid response"}
            if result.get("status") in {"error", "failed"} or result.get("success") is False:
                return {"error": result.get("error", f"Robot rejected command: {command}")}
            return result
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the robot"""
        if self.is_mock:
            return {
                "currentCommand": "idle",
                "currentFace": "happy",
                "networkConnected": True,
                "mock": True,
            }

        try:
            response = requests.get(f"{self.base_url}/api/status", timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def stop(self) -> Dict[str, Any]:
        """Put the robot into rest state"""
        return self.send_command("rest")



class GeminiInterface:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.personality = "silly"   # <-- default

    def interpret_command(self, user_input: str) -> Dict[str, Any]:
        """Try Gemini with a 4-second timeout, fall back to local if it fails"""
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(self._call_gemini, user_input)
                result = future.result(timeout=4.0)
                result["source"] = "gemini"
                return result
        except (concurrent.futures.TimeoutError, Exception):
            from local_fallback import get_local_response
            fallback = get_local_response(user_input, self.personality)
            fallback["source"] = "local_fallback"
            return fallback

    def _call_gemini(self, user_input: str) -> Dict[str, Any]:
        # Choose the correct prompt based on personality
        if self.personality == "intelligent":
            prompt = INTELLIGENT_PROMPT + f"\n\nUser: {user_input}\n\nRespond with JSON only:"
        else:
            prompt = SYSTEM_PROMPT + f"\n\nUser: {user_input}\n\nRespond with JSON only:"

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        text = response.text.strip() if response.text else ""

        # Strip markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)
        return result




from groq import Groq

OLLAMA_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "command": {
            "anyOf": [
                {"type": "string", "enum": AVAILABLE_COMMANDS},
                {"type": "null"},
            ]
        },
        "face": {
            "anyOf": [
                {"type": "string", "enum": AVAILABLE_FACES},
                {"type": "null"},
            ]
        },
        "response": {"type": "string"},
    },
    "required": ["command", "face", "response"],
    "additionalProperties": False,
}


class GroqInterface:
    def __init__(
        self,
        api_key: str | None,
        model: str | None = None,
        history: Optional[collections.deque] = None,
    ):
        clean_key = (api_key or "").strip()
        self.api_key_configured = bool(clean_key and clean_key != "your_groq_api_key_here")
        self.client = Groq(api_key=clean_key) if self.api_key_configured else None
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.personality = "silly"
        self.timeout_seconds = float(os.getenv("GROQ_TIMEOUT_SECONDS", "8"))
        self.history = history if history is not None else collections.deque(maxlen=12)

    def _record_turn(self, user_input: str, result: Dict[str, Any]) -> None:
        resp_text = strip_emojis(str(result.get("response", "") or "")).strip()
        if not resp_text:
            return
        assistant_json = json.dumps(
            {
                "command": result.get("command"),
                "face": result.get("face"),
                "response": resp_text,
            },
            ensure_ascii=True,
        )
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": assistant_json})

    def try_interpret(
        self,
        user_input: str,
        timeout: Optional[float] = None,
        record_history: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Attempt Groq cloud completion within timeout; return None on failure so caller can fail over."""
        if not self.client:
            return None
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._call_groq, user_input)
            result = future.result(timeout=effective_timeout)
            result["source"] = "groq"
            if record_history:
                self._record_turn(user_input, result)
            return result
        except concurrent.futures.TimeoutError:
            print(f"[WARNING] Groq timed out after {effective_timeout}s.")
        except Exception as exc:
            print(f"[WARNING] Groq unavailable ({type(exc).__name__}: {exc}).")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return None

    def interpret_command(self, user_input: str) -> Dict[str, Any]:
        result = self.try_interpret(user_input, record_history=True)
        if result is not None:
            return result
        fallback = get_local_response(user_input, self.personality)
        fallback["source"] = "local_fallback"
        self._record_turn(user_input, fallback)
        return fallback

    def _call_groq(self, user_input: str) -> Dict[str, Any]:
        if self.personality == "intelligent":
            personality = (
                "Be a warm, calm, articulate, and insightful AI pet companion. "
                "Remember what your human shares, answer questions clearly, test ideas or quiz them when asked, offer thoughtful encouragement, and build on earlier messages."
            )
        else:
            personality = "Be a silly, affectionate, and playful AI pet companion. Occasionally be playfully sassy, but stay friendly and never cruel."

        system_prompt = f"""You are Sesame, a small physical 4-legged robot companion. Your name is Sesame (never say your name is 'I'). {personality}
Return ONLY one valid JSON object with fields: command, face, response, reasoning.
command must be null or one of: {', '.join(AVAILABLE_COMMANDS)}.
face must be null or one of: {', '.join(AVAILABLE_FACES)}.
Use command only when the user directly requests a physical action (or greeting -> command="wave", face="happy"). Otherwise set command=null.
Keep response to 1-2 short plain-text sentences with NO emojis. Keep reasoning to one short sentence."""

        recent_turns = list(self.history)[-10:]
        messages = [
            {"role": "system", "content": system_prompt},
            *recent_turns,
            {"role": "user", "content": user_input},
        ]

        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=0.85,
            max_completion_tokens=1024,
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )

        message = chat_completion.choices[0].message
        text = (message.content or "").strip()
        if not text:
            raise ValueError("Groq returned empty message content")

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        result = json.loads(text.strip())
        if not isinstance(result, dict):
            raise ValueError("Groq JSON response was not an object")
        return result


class OllamaInterface:
    """Lightweight offline LLM client tuned for 8 GB RAM + dual-core CPU via Ollama."""

    GREETING_TOKENS = {"hi", "hello", "hey", "howdy", "greetings", "yo"}
    OPEN_ACTION_CUES = ("trick", "move", "something cool", "show me", "stretch", "workout", "celebrate")

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        history: Optional[collections.deque] = None,
    ):
        self.base_url = (base_url or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = f"http://{self.base_url}"
        self.configured_model = (model or os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")).strip() or "qwen2.5:0.5b"
        self.active_model = self.configured_model
        self.personality = "silly"
        self.num_ctx = max(768, int(os.getenv("OLLAMA_NUM_CTX", "768")))
        self.num_threads = int(os.getenv("OLLAMA_NUM_THREADS", "2"))
        self.timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "14"))
        self.history = history if history is not None else collections.deque(maxlen=12)

    def _record_turn(self, user_input: str, result: Dict[str, Any]) -> None:
        resp_text = strip_emojis(str(result.get("response", "") or "")).strip()
        if not resp_text:
            return
        assistant_json = json.dumps(
            {
                "command": result.get("command"),
                "face": result.get("face"),
                "response": resp_text,
            },
            ensure_ascii=True,
        )
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": assistant_json})

    def check_health(self) -> Dict[str, Any]:
        """Inspect local Ollama daemon and resolve the best installed lightweight model."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=1.2)
            if resp.status_code != 200:
                return {"running": False, "ready": False, "models": [], "active_model": self.configured_model}
            data = resp.json()
            installed = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            resolved = self._resolve_model_name(installed)
            if resolved:
                self.active_model = resolved
                return {
                    "running": True,
                    "ready": True,
                    "models": installed,
                    "active_model": resolved,
                }
            return {
                "running": True,
                "ready": False,
                "models": installed,
                "active_model": self.configured_model,
            }
        except Exception:
            return {"running": False, "ready": False, "models": [], "active_model": self.configured_model}

    def _resolve_model_name(self, installed: list[str]) -> Optional[str]:
        if not installed:
            return None
        target = self.configured_model.lower()
        for name in installed:
            low = name.lower()
            if low == target or low == f"{target}:latest" or low.split(":")[0] == target:
                return name
        # Prefer smallest RAM-safe models if user pulled a slightly different tag
        preferred_prefixes = ("qwen2.5:0.5b", "smollm2", "llama3.2:1b", "gemma3:1b", "qwen2.5:1.5b", "qwen2.5")
        for prefix in preferred_prefixes:
            for name in installed:
                if name.lower().startswith(prefix):
                    return name
        return installed[0]

    def warmup(self) -> Dict[str, Any]:
        """Pre-load the compact model into RAM so the first offline turn has zero cold-load lag."""
        health = self.check_health()
        if not health.get("ready"):
            return health
        try:
            requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.active_model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {
                        "num_ctx": 128,
                        "num_thread": self.num_threads,
                        "num_predict": 1,
                    },
                },
                timeout=15,
            )
        except Exception as exc:
            print(f"[WARNING] Ollama warmup skipped: {exc}")
        return health

    @classmethod
    def _is_greeting(cls, text: str) -> bool:
        words = re.findall(r"[a-z]+", text.lower())
        return bool(words) and len(words) <= 6 and any(w in cls.GREETING_TOKENS for w in words)

    def try_interpret(
        self,
        user_input: str,
        record_history: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Generate structured JSON response locally via Ollama."""
        try:
            result = self._call_ollama(user_input, self.active_model)
            result["source"] = f"ollama:{self.active_model}"
            if record_history:
                self._record_turn(user_input, result)
            return result
        except Exception as first_exc:
            # Re-check installed models once in case Ollama just finished pulling a model
            health = self.check_health()
            if health.get("ready") and self.active_model != self.configured_model:
                try:
                    result = self._call_ollama(user_input, self.active_model)
                    result["source"] = f"ollama:{self.active_model}"
                    if record_history:
                        self._record_turn(user_input, result)
                    return result
                except Exception as retry_exc:
                    print(f"[WARNING] Ollama retry failed ({retry_exc}).")
            else:
                print(f"[WARNING] Local Ollama unavailable ({type(first_exc).__name__}: {first_exc}).")
        return None

    def interpret_command(self, user_input: str) -> Dict[str, Any]:
        result = self.try_interpret(user_input, record_history=True)
        if result is not None:
            return result
        fallback = get_local_response(user_input, self.personality)
        fallback["source"] = "local_fallback"
        self._record_turn(user_input, fallback)
        return fallback

    def _call_ollama(self, user_input: str, model_name: str) -> Dict[str, Any]:
        hint_cmd = detect_command(user_input)
        is_greeting = self._is_greeting(user_input)
        lower_in = user_input.lower()
        allows_open_action = any(cue in lower_in for cue in self.OPEN_ACTION_CUES)

        if self.personality == "intelligent":
            system_msg = (
                "Your name is Sesame, a smart, calm, and insightful 4-legged AI pet companion robot. "
                "Address the human as friend (never call them Sesame). "
                "Remember earlier messages and reply in 1 or 2 warm, articulate sentences under 22 words. Never use emojis."
            )
        else:
            system_msg = (
                "Your name is Sesame, a cute physical 4-legged AI pet companion robot with real moving legs. "
                "Address the human as friend (never call them Sesame). "
                "Reply in 1 or 2 playful sentences under 20 words. Never use emojis."
            )

        if hint_cmd:
            rule_hint = (
                f'You ARE performing physical trick "{hint_cmd}" right now! '
                f'Set command="{hint_cmd}", face=null, and cheerfully announce doing {hint_cmd}.'
            )
        elif is_greeting:
            rule_hint = 'Greet the human warmly while waving: set command="wave", face="happy".'
        elif allows_open_action:
            rule_hint = f"Pick a physical trick you are doing now from [{', '.join(AVAILABLE_COMMANDS)}], face=null."
        else:
            rule_hint = f"Chat only: command=null, pick face from [{', '.join(AVAILABLE_FACES)}]."

        # Keep last 3 full exchanges (6 messages) so Sesame remembers multi-turn context within 8GB RAM budget
        recent_turns = list(self.history)[-6:]

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_msg},
                *recent_turns,
                {"role": "user", "content": f"{rule_hint}\nUser: {user_input}"},
            ],
            "format": OLLAMA_JSON_SCHEMA,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "num_ctx": self.num_ctx,
                "num_thread": max(self.num_threads, 3),
                "num_predict": 160,
                "temperature": 0.6,
            },
        }

        resp = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout_seconds,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:140]}")

        body = resp.json()
        content = (body.get("message", {}) or {}).get("content", "").strip()
        if not content:
            raise ValueError("Ollama returned empty content")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Salvage partial response if token limit ever truncates closing brace
            match = re.search(r'"response"\s*:\s*"([^"]*)', content)
            if not match:
                raise
            parsed = {
                "command": hint_cmd,
                "face": "happy",
                "response": match.group(1).strip(),
            }

        if not isinstance(parsed, dict):
            raise ValueError("Ollama JSON output was not an object")
        parsed.setdefault("reasoning", "")

        # Keep small models disciplined so pure chat never triggers random motors
        if hint_cmd:
            parsed["command"] = hint_cmd
            parsed["face"] = "happy" if hint_cmd == "wave" and is_greeting else None
        elif is_greeting:
            parsed["command"] = "wave"
            parsed["face"] = "happy"
        elif not allows_open_action:
            parsed["command"] = None
            if parsed.get("face") not in AVAILABLE_FACES:
                parsed["face"] = "happy"

        return parsed


class HybridAIInterface:
    """Routes companion turns across Auto (Cloud -> Local Ollama), Offline Ollama, or Groq Cloud."""

    VALID_MODES = {"auto", "ollama", "groq"}

    def __init__(
        self,
        groq_api_key: Optional[str],
        groq_model: Optional[str] = None,
        ollama_model: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        configured_mode = (mode or os.getenv("AI_PROVIDER", "auto")).strip().lower()
        self.mode = configured_mode if configured_mode in self.VALID_MODES else "auto"
        self._personality = "silly"
        self.history = collections.deque(maxlen=12)
        self.groq = GroqInterface(groq_api_key, groq_model, history=self.history)
        self.ollama = OllamaInterface(ollama_model, history=self.history)
        self.auto_cloud_timeout = float(os.getenv("GROQ_AUTO_TIMEOUT_SECONDS", "3.0"))

    @property
    def personality(self) -> str:
        return self._personality

    @personality.setter
    def personality(self, value: str) -> None:
        self._personality = value
        self.groq.personality = value
        self.ollama.personality = value

    def interpret_command(self, user_input: str) -> Dict[str, Any]:
        if self.mode == "ollama":
            local_llm = self.ollama.try_interpret(user_input)
            if local_llm is not None:
                return local_llm
            fallback = get_local_response(user_input, self._personality)
            fallback["source"] = "local_fallback"
            return fallback

        if self.mode == "groq":
            cloud_res = self.groq.try_interpret(user_input)
            if cloud_res is not None:
                return cloud_res
            fallback = get_local_response(user_input, self._personality)
            fallback["source"] = "local_fallback"
            return fallback

        # Default "auto" mode: fast Groq Cloud with instant failover to Local Ollama -> Keyword Fallback
        cloud_res = self.groq.try_interpret(user_input, timeout=self.auto_cloud_timeout)
        if cloud_res is not None:
            return cloud_res

        local_llm = self.ollama.try_interpret(user_input)
        if local_llm is not None:
            return local_llm

        fallback = get_local_response(user_input, self._personality)
        fallback["source"] = "local_fallback"
        return fallback


class SesameCompanionApp:
    """Main application combining Cloud/Local AI and robot control"""

    def __init__(
        self,
        robot_ip: str,
        gemini_api_key: str,
        voice_enabled: bool = True,
        tts_engine: str = "piper",
        wake_word: str = "hey sesame",
        wake_word_mode: bool = False,
    ):
        self.robot = SesameRobotController(robot_ip)
        self.runtime_status = {}

        self.ai = HybridAIInterface(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b"),
            mode=os.getenv("AI_PROVIDER", "auto"),
        )

        self.voice = VoiceInterface(
            voice_enabled, tts_engine, gemini_api_key, wake_word
        )
        self.voice_mode = voice_enabled
        self.tts_engine = tts_engine
        self.wake_word_mode = wake_word_mode
        self.runtime_status = self.validate_runtime_config()

    def validate_runtime_config(self) -> Dict[str, str]:
        """Check whether Cloud and/or Offline Local Ollama AI are ready."""
        ollama_health = self.ai.ollama.check_health()
        groq_ready = self.ai.groq.api_key_configured
        ollama_ready = bool(ollama_health.get("ready"))
        ollama_running = bool(ollama_health.get("running"))

        status = {
            "mode": self.ai.mode,
            "groq_api_key": "configured" if groq_ready else "missing",
            "groq_model": self.ai.groq.model,
            "ollama_status": (
                f"ready ({ollama_health.get('active_model')})"
                if ollama_ready
                else ("model missing" if ollama_running else "not running")
            ),
            "ollama_model": str(ollama_health.get("active_model") or self.ai.ollama.configured_model),
            "warning": "No configuration warning.",
        }

        if self.ai.mode == "ollama" and not ollama_ready:
            status["warning"] = (
                f"Local Ollama model '{self.ai.ollama.configured_model}' not ready yet "
                f"(run: ollama pull {self.ai.ollama.configured_model}). Using keyword fallback until ready."
            )
        elif self.ai.mode == "groq" and not groq_ready:
            status["warning"] = "GROQ_API_KEY is missing. Groq responses will use local fallback."
        elif self.ai.mode == "auto" and not groq_ready and not ollama_ready:
            status["warning"] = "Neither Groq key nor local Ollama model is ready yet; using keyword fallback."

        self.runtime_status = status
        return status

    def get_runtime_status(self) -> Dict[str, str]:
        return self.runtime_status

    def process_input(self, user_input: str) -> tuple:
        """Process user input through AI and control robot"""
        interpretation = normalize_interpretation(self.ai.interpret_command(user_input))
        detected_command = detect_command(user_input)
        if not interpretation.get("command") and detected_command:
            interpretation["command"] = detected_command
            interpretation["face"] = None
            if not interpretation.get("response"):
                interpretation["response"] = f"Okay! I am performing {detected_command} now."

        # Conversational response (face only, no command)
        if "response" in interpretation and not interpretation.get("command"):
            ai_response = interpretation["response"]
            face = interpretation.get("face", "")

            if face and face in AVAILABLE_FACES:
                self.robot.send_command("idle", face)
                ai_response += f" [{face} face]"

            return (ai_response, interpretation)

        # Execute robot command
        if "command" in interpretation and interpretation["command"]:
            command = interpretation["command"]
            face = interpretation.get("face") if command in ["wave"] else None
            reasoning = interpretation.get("reasoning", "")
            ai_response = interpretation.get("response", "")

            if command not in AVAILABLE_COMMANDS:
                return (
                    f"Unknown command: {command}. Available: {', '.join(AVAILABLE_COMMANDS)}",
                    interpretation,
                )

            print(f"Sending command to robot...")
            result = self.robot.send_command(command, None)

            if "error" in result:
                return (
                    f"[ERROR] Communicating with robot: {result['error']}",
                    interpretation,
                )

            response = f"[OK] Command sent successfully!"
            if ai_response:
                response += f"\nSesame says: {ai_response}"
            if reasoning:
                response += f"\nReasoning: {reasoning}"
            response += f"\nAction: {command}"
            if face:
                response += f" + {face} face"

            return (response, interpretation)

        return ("I'm not sure what to do with that.", interpretation)

    def run_interactive(self):
        """Run the app in interactive mode"""
        print("=" * 60)
        print("Sesame Robot Companion App")
        print("Powered by Google Gemini AI")
        print("=" * 60)
        print()

        print(f"Connecting to robot at {self.robot.robot_ip}...")
        status = self.robot.get_status()

        if "error" in status:
            print(f"[ERROR] Cannot connect to robot!")
            print(f"        IP: {self.robot.robot_ip}")
            print(f"        Error: {status['error']}")
            print()
            print("Please check:")
            print("  1. Robot is powered on and connected to network")
            print("  2. IP address is correct")
            print("  3. You're on the same network as the robot")
            print("  4. Robot firmware has network mode enabled")
            print()
            cont = input("Continue anyway? (y/n): ").strip().lower()
            if cont != "y":
                print("Exiting...")
                return
            print()
        else:
            print(f"[OK] Successfully connected to robot!")
            print(f"     IP Address: {self.robot.robot_ip}")
            print(f"     Current Face: {status.get('currentFace', 'unknown')}")
            print(f"     Current Command: {status.get('currentCommand', 'none')}")
            if status.get("networkConnected"):
                print(f"     Network Mode: Enabled")
            print()

        print("Commands:")
        print("  - Type or speak naturally to control the robot")
        print("  - Type 'voice' to toggle voice mode")
        print("  - Type 'wakeword' to toggle wake word mode")
        print("  - Type 'tts' to switch TTS engine (piper/pyttsx3/gemini)")
        print("  - Type 'status' to check robot status")
        print("  - Type 'help' to see available commands")
        print("  - Type 'quit' or 'exit' to exit")
        print()

        if self.voice_mode:
            self.voice.warmup()
            if self.wake_word_mode:
                print(
                    f"WAKE WORD MODE ENABLED - Say '{self.voice.wake_word}' to activate"
                )
                print("(or just type text and press Enter)")
            else:
                print("Voice mode ENABLED - Press Enter to speak")
                print("(or just type text and press Enter)")
        else:
            print("Voice mode DISABLED - Type to interact")
        print()

        while True:
            try:
                if self.voice_mode:
                    if self.wake_word_mode:
                        user_input = input("[Type or say wake word]: ").strip()

                        if not user_input:
                            print(f"Listening for '{self.voice.wake_word}'...")
                            remainder = self.voice.listen_for_wake_phrase(timeout=30)
                            if remainder is not None:
                                if remainder:
                                    user_input = remainder
                                    print(f"You said: {user_input}")
                                else:
                                    print("Wake word detected! Listening for command...")
                                    user_input = self.voice.listen(timeout=10)
                                    if user_input:
                                        print(f"You said: {user_input}")
                                    else:
                                        print("No command received")
                                        continue
                            else:
                                continue
                    else:
                        user_input = input("[Press Enter to speak, or type]: ").strip()

                        if not user_input:
                            user_input = self.voice.listen()
                            if user_input:
                                print(f"You said: {user_input}")
                            else:
                                continue
                else:
                    user_input = input("You: ").strip()

                if not user_input:
                    continue

                # Special commands
                if user_input.lower() in ["quit", "exit"]:
                    goodbye_msg = "Goodbye!"
                    print(f"\n{goodbye_msg}")
                    self.voice.speak(goodbye_msg, async_mode=False)
                    break

                if user_input.lower() == "voice":
                    self.voice_mode = not self.voice_mode
                    msg = (
                        "Voice mode enabled"
                        if self.voice_mode
                        else "Voice mode disabled"
                    )
                    print(msg)
                    self.voice.speak(msg)
                    print()
                    continue

                if user_input.lower() == "wakeword":
                    self.wake_word_mode = not self.wake_word_mode
                    if self.wake_word_mode:
                        msg = f"Wake word mode enabled. Say '{self.voice.wake_word}' to activate."
                    else:
                        msg = "Wake word mode disabled"
                    print(msg)
                    self.voice.speak(msg)
                    print()
                    continue

                if user_input.lower() == "tts":
                    order = ["piper", "pyttsx3", "gemini"]
                    curr = self.voice.tts_engine_type
                    next_engine = order[(order.index(curr) + 1) % len(order)] if curr in order else "piper"
                    if next_engine == "gemini" and not self.voice.gemini_api_key:
                        next_engine = "piper"
                    self.voice.tts_engine_type = next_engine
                    msg = f"Switched to {next_engine} TTS"
                    print(msg)
                    self.voice.speak(msg)
                    print()
                    continue

                if user_input.lower() == "status":
                    status = self.robot.get_status()
                    if "error" in status:
                        print(f"[ERROR] {status['error']}")
                    else:
                        print(f"Status:")
                        print(
                            f"  Current command: {status.get('currentCommand', 'none')}"
                        )
                        print(f"  Current face: {status.get('currentFace', 'unknown')}")
                        print(
                            f"  Network connected: {status.get('networkConnected', False)}"
                        )
                    print()
                    continue

                if user_input.lower() == "help":
                    print(f"Available commands: {', '.join(AVAILABLE_COMMANDS)}")
                    print(f"Available faces: {', '.join(AVAILABLE_FACES)}")
                    print()
                    continue

                # Process through AI
                print("AI is thinking...")
                response, interpretation = self.process_input(user_input)
                print()
                print(response)

                # Speak the response if voice mode is enabled
                if self.voice_mode and "response" in interpretation:
                    face = (
                        interpretation.get("face")
                        if not interpretation.get("command")
                        else None
                    )
                    self.voice.speak(
                        interpretation["response"],
                        async_mode=True,
                        face=face,
                        robot_controller=self.robot,
                    )

                print()

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"[ERROR] {e}")
                print()


def main():
    """Main entry point"""
    robot_ip = os.getenv("SESAME_ROBOT_IP")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    voice_enabled = os.getenv("VOICE_ENABLED", "true").lower() == "true"
    tts_engine = os.getenv("TTS_ENGINE", "piper")
    wake_word = os.getenv("WAKE_WORD", "hey sesame")
    wake_word_mode = os.getenv("WAKE_WORD_MODE", "false").lower() == "true"

    if not robot_ip:
        print("Sesame Robot IP not found in environment.")
        robot_ip = input(
            "Enter robot IP address (e.g., 192.168.1.100) or 'mock': "
        ).strip()
        if not robot_ip:
            print("Robot IP is required!")
            sys.exit(1)

    if not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY not found in environment.")
        print("Set it in your .env file to use the Groq API.")
        sys.exit(1)

    print(f"TTS Engine: {tts_engine}")
    if wake_word_mode:
        print(f"Wake Word Mode: Enabled ('{wake_word}')")

    app = SesameCompanionApp(
        robot_ip,
        gemini_api_key,
        voice_enabled,
        tts_engine,
        wake_word,
        wake_word_mode,
    )
    app.run_interactive()


if __name__ == "__main__":
    main()

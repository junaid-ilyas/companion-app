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
    PIPER_AVAILABLE = True
except ImportError:
    PiperVoice = None
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
}


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
    interpretation.setdefault("response", "")
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

SHORT_SYSTEM_PROMPT = f"""You are Sesame, a small, dim-witted robot. Speak like a toddler (first person "I"). Keep responses under 15 words. Occasionally be sarcastic.

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

WHISPER_DOMAIN_PROMPT = (
    "Sesame robot companion. Hey Sesame. "
    "walk, dance, crab walk, wave, bow, pushup, swim, cute, shake, shrug, worm, rest, stop."
)

SILENCE_HALLUCINATIONS = {
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching.",
    "you",
    "you.",
    "bye",
    "bye.",
    "...",
    ".",
}


class VoiceInterface:
    """Handles fast local voice input (faster-whisper + PyAudio) and neural TTS (Piper)."""

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 1024

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
        self.microphone_device_index = self._get_microphone_device_index()
        self.last_listen_error: Optional[str] = None

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.7

        self.tts_lock = threading.Lock()
        self.mic_lock = threading.Lock()
        self._stop_listen_event = threading.Event()
        self.is_listening_manual = False
        self.is_speaking = False

        self._whisper_model = None
        self._whisper_lock = threading.Lock()
        self._whisper_model_name = os.getenv("WHISPER_MODEL", "tiny").strip() or "tiny"

        self._piper_voice = None
        self._piper_voice_loaded_name = None
        self._piper_lock = threading.Lock()
        self._piper_voice_name = (
            os.getenv("PIPER_VOICE", "en_US-lessac-medium").strip()
            or "en_US-lessac-medium"
        )

        self._energy_threshold = float(os.getenv("MIC_ENERGY_THRESHOLD", "260"))
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

            # Warm up CTranslate2 & Silero VAD ONNX once so the first mic click has zero lag
            dummy = np.zeros(3200, dtype=np.float32)
            list(
                model.transcribe(
                    dummy,
                    beam_size=1,
                    temperature=0.0,
                    vad_filter=True,
                    without_timestamps=True,
                )[0]
            )
            self._whisper_model = model
            print(
                f"[OK] Local Whisper STT ready (model={self._whisper_model_name}, int8, threads={cpu_threads})"
            )
            return self._whisper_model

    def _ensure_piper_voice(self):
        """Load local Piper neural ONNX voice once and keep it warm."""
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

            voice = PiperVoice.load(onnx_path)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                voice.synthesize_wav("Hi.", wf)

            self._piper_voice = voice
            self._piper_voice_loaded_name = self._piper_voice_name
            print(f"[OK] Local Piper TTS ready (voice={self._piper_voice_name})")
            return self._piper_voice

    def _calibrate_ambient_once(self, duration: float = 0.35):
        """Measure ambient mic RMS once at startup so listen() has zero startup delay."""
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
                    self._energy_threshold = max(
                        170.0, min(850.0, ambient * 1.9 + 85.0)
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

    def warmup(self) -> Dict[str, Any]:
        """Preload local STT + TTS models and calibrate microphone once on a background thread."""
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

        if PIPER_AVAILABLE:
            try:
                self._ensure_piper_voice()
                info["tts_ready"] = True
            except Exception as exc:
                print(f"[WARNING] Piper warmup failed: {exc}")
                info["tts_error"] = str(exc)

        self._calibrate_ambient_once()
        return info

    def _capture_phrase_pcm(
        self,
        timeout: float = 5.0,
        phrase_time_limit: float = 10.0,
        silence_duration: float = 0.65,
        allow_manual_stop: bool = True,
        abort_on_manual_request: bool = False,
    ) -> Optional[bytes]:
        """Capture 16kHz 16-bit mono PCM speech with a pre-roll buffer and adaptive silence cutoff."""
        if not AUDIO_MONITORING_AVAILABLE:
            raise RuntimeError("PyAudio is required for local microphone capture")

        pa = pyaudio.PyAudio()
        stream = None
        try:
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

            chunk_sec = self.CHUNK_SIZE / float(self.SAMPLE_RATE)
            pre_roll = collections.deque(maxlen=5)  # ~320ms pre-roll prevents clipping first syllable
            frames = []
            speech_started = False
            onset_hits = 0
            silence_chunks = 0
            max_silence_chunks = max(4, int(silence_duration / chunk_sec))
            min_speech_chunks = max(4, int(0.28 / chunk_sec))
            start_wait = time.monotonic()
            speech_start_time = 0.0
            threshold = self._energy_threshold

            while True:
                if abort_on_manual_request and self.is_listening_manual:
                    return None

                if allow_manual_stop and self._stop_listen_event.is_set():
                    if speech_started and len(frames) >= 2:
                        break
                    self.last_listen_error = "Listening stopped"
                    return None

                raw = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0

                if not speech_started:
                    pre_roll.append(raw)
                    if rms >= threshold * 1.35:
                        onset_hits += 2
                    elif rms >= threshold:
                        onset_hits += 1
                    else:
                        onset_hits = 0
                        # Gently adapt ambient floor during quiet idle frames
                        adapted = rms * 1.9 + 85.0
                        threshold = 0.94 * threshold + 0.06 * max(170.0, min(850.0, adapted))
                        self._energy_threshold = threshold

                    if onset_hits >= 2:
                        speech_started = True
                        speech_start_time = time.monotonic()
                        frames.extend(pre_roll)
                        silence_chunks = 0
                    elif (time.monotonic() - start_wait) >= timeout:
                        self.last_listen_error = "No speech detected"
                        return None
                else:
                    frames.append(raw)
                    if rms < threshold * 0.78:
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

    def transcribe_pcm(
        self, pcm_bytes: bytes, initial_prompt: Optional[str] = None
    ) -> Optional[str]:
        """Transcribe 16kHz 16-bit mono PCM bytes locally using faster-whisper."""
        if not pcm_bytes:
            return None

        audio_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio_i16.size < int(self.SAMPLE_RATE * 0.18):
            return None

        audio_f32 = audio_i16.astype(np.float32) / 32768.0
        peak_rms = float(np.sqrt(np.mean(audio_f32 * audio_f32)))
        if peak_rms < 0.0025:
            return None

        model = self._ensure_whisper_model()
        segments, _info = model.transcribe(
            audio_f32,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            max_new_tokens=64,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=320, speech_pad_ms=200),
            without_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt or WHISPER_DOMAIN_PROMPT,
        )

        collected = []
        for seg in segments:
            seg_text = (seg.text or "").strip()
            if not seg_text:
                continue
            if getattr(seg, "no_speech_prob", 0.0) > 0.82 and getattr(seg, "avg_logprob", 0.0) < -1.0:
                continue
            collected.append(seg_text)

        text = " ".join(collected).strip()
        if not text:
            return None

        if text.lower().strip(" !?,.") in SILENCE_HALLUCINATIONS and peak_rms < 0.012:
            return None

        return text

    def listen(self, timeout: int = 5, phrase_time_limit: float = 10.0) -> Optional[str]:
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
                    silence_duration=0.65,
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
        """Check if text contains the wake word and return any trailing command."""
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
        # De-duplicate while preserving order
        seen = set()
        triggers = []
        for c in candidates:
            c_norm = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", c)).strip()
            if c_norm and c_norm not in seen:
                seen.add(c_norm)
                triggers.append(c_norm)

        for trig in triggers:
            pattern = rf"\b{re.escape(trig)}\b(.*)$"
            match = re.search(pattern, lowered)
            if match:
                # Extract clean remainder from original text roughly after trigger
                orig_match = re.search(
                    rf"{re.escape(trig.split()[-1])}[\s,.:;!?-]*(.*)$",
                    text,
                    flags=re.IGNORECASE,
                )
                remainder = (orig_match.group(1) if orig_match else match.group(1)).strip()
                return remainder

        return None

    def listen_for_wake_phrase(self, timeout: float = 2.5) -> Optional[str]:
        """
        Listen briefly for the wake word without blocking manual mic clicks.
        Returns:
          - None if wake word was NOT detected
          - "" if ONLY the wake word was spoken (caller should listen for follow-up)
          - "<command>" if user spoke wake word + command in one phrase
        """
        if not self.voice_enabled or self.is_listening_manual or self.is_speaking:
            return None

        if not self.mic_lock.acquire(blocking=False):
            return None

        try:
            pcm_bytes = self._capture_phrase_pcm(
                timeout=timeout,
                phrase_time_limit=4.5,
                silence_duration=0.55,
                allow_manual_stop=False,
                abort_on_manual_request=True,
            )
        except Exception:
            return None
        finally:
            self.mic_lock.release()

        if not pcm_bytes or self.is_listening_manual:
            return None

        try:
            text = self.transcribe_pcm(
                pcm_bytes,
                initial_prompt=f"{self.wake_word}, Hey Sesame, dance, walk, wave, hello.",
            )
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
        """Strip bracketed UI face annotations before speaking."""
        if not text:
            return ""
        cleaned = re.sub(r"\s*\[[^\]]*face\]\s*$", "", text, flags=re.IGNORECASE)
        return cleaned.strip()

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

    def _speak_piper(
        self,
        text: str,
        face: Optional[str] = None,
        robot_controller=None,
    ):
        """Synthesize natural local speech via Piper ONNX and animate mouth from audio envelope."""
        try:
            voice = self._ensure_piper_voice()
            wav_buf = io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                voice.synthesize_wav(text, wf)

            wav_bytes = wav_buf.getvalue()
            with wave.open(io.BytesIO(wav_bytes), "rb") as rf:
                sample_rate = rf.getframerate()
                pcm_frames = rf.readframes(rf.getnframes())

            samples = np.frombuffer(pcm_frames, dtype=np.int16).astype(np.float32)
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
        """Stop the current robot action"""
        return self.send_command("stop")



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

class GroqInterface:
    def __init__(self, api_key: str, model: str | None = None):
        self.client = Groq(api_key=api_key)
        self.model = model or os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        self.personality = "silly"
        self.timeout_seconds = float(os.getenv("GROQ_TIMEOUT_SECONDS", "8"))

    def interpret_command(self, user_input: str) -> Dict[str, Any]:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._call_groq, user_input)
            result = future.result(timeout=self.timeout_seconds)
            result["source"] = "groq"
            return result
        except concurrent.futures.TimeoutError:
            print(f"[WARNING] Groq request timed out after {self.timeout_seconds}s. Falling back to local response.")
        except Exception as exc:
            print(f"[WARNING] Groq failed ({type(exc).__name__}: {exc}). Falling back to local response.")
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        fallback = get_local_response(user_input, self.personality)
        fallback["source"] = "local_fallback"
        return fallback

    def _call_groq(self, user_input: str) -> Dict[str, Any]:
        if self.personality == "intelligent":
            personality = "Be calm, articulate, and helpful."
        else:
            personality = "Be silly, warm, and simple. Occasionally be sarcastic or playfully annoyed, but stay friendly and never cruel."

        prompt = f"""You are Sesame, a small robot companion. {personality}
Return exactly one valid JSON object and nothing else.
Use exactly these fields: command, face, response, reasoning.
command must be null or one of: {', '.join(AVAILABLE_COMMANDS)}.
face must be null or one of: {', '.join(AVAILABLE_FACES)}.
Use command only when the user directly requests an action. Otherwise use command=null.
Use a face for conversation. A greeting may use command=wave and face=happy.
Keep response to one or two short sentences. Keep reasoning to one short sentence.
User: {user_input}"""

        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are Sesame, a small, chatty robot. Your name is Sesame. Never say your name is 'I'. Always introduce yourself as Sesame."},
                {"role": "user", "content": prompt},
            ],
            model=self.model,
            temperature=0.9,
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
    
class SesameCompanionApp:
    """Main application combining Gemini AI and robot control"""

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

        self.ai = GroqInterface(os.getenv("GROQ_API_KEY"), os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"))

        self.voice = VoiceInterface(
            voice_enabled, tts_engine, gemini_api_key, wake_word
        )
        self.voice_mode = voice_enabled
        self.tts_engine = tts_engine
        self.wake_word_mode = wake_word_mode
        self.runtime_status = self.validate_runtime_config()

    def validate_runtime_config(self) -> Dict[str, str]:
        """Check whether the runtime environment is ready for end users."""
        status = {
            "mode": "groq",
            "groq_api_key": "missing" if not os.getenv("GROQ_API_KEY") else "configured",
            "groq_model": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        }

        if status["mode"] == "groq" and status["groq_api_key"] == "missing":
            status["warning"] = "GROQ_API_KEY is missing. Groq responses will fail unless a key is configured."
        else:
            status["warning"] = "No configuration warning."

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

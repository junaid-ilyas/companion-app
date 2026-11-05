# Sesame Robot Companion App

Modern desktop companion app and AI-powered natural language interface for the Sesame robot. Built with a responsive glassmorphic frontend (HTML/CSS/JS) powered by **PyWebView**, ultrafast cloud LLM inference via **Groq**, Google Gemini via the official **`google-genai`** SDK, and **pyttsx3** / **Gemini TTS** voice synthesis.

---

## Setup

### Requirements

- Python 3.10+
- Sesame robot on the same local network (or `'mock'` mode for offline testing)
- [Groq API Key](https://console.groq.com/keys) (primary AI chat completion)
- Optional: [Google Gemini API key](https://aistudio.google.com/app/apikey) (for Gemini AI / Gemini TTS)

### Installation

```powershell
pip install -r requirements.txt
```

### Configuration

Create or edit your `.env` file in the project root:

```env
# Robot connection (use 'mock' if robot is offline)
SESAME_ROBOT_IP=192.168.100.97

# AI API Keys & Models
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-20b
GEMINI_API_KEY=your_gemini_api_key_here

# Voice & Speech
VOICE_ENABLED=true
TTS_ENGINE=pyttsx3
# Optional microphone selection; use either index or a name fragment
# MIC_DEVICE_INDEX=5
# MIC_DEVICE_NAME=Microphone Array
WAKE_WORD=hey sesame
WAKE_WORD_MODE=true
```

### Connecting After Wi-Fi Setup

The robot uses two different IP addresses:

- `appIP` (usually `192.168.4.1`) is the temporary setup portal address. Do not use it for the app after configuring Wi-Fi.
- `networkIP` is the address assigned by your home router. Use this address in `SESAME_ROBOT_IP`.

After saving your home Wi-Fi credentials in the robot portal:

1. Reconnect your laptop to the same home Wi-Fi network as the robot.
2. Check the robot status response or serial monitor for `networkIP`.
3. Set that address in `.env`, for example:

   ```env
   SESAME_ROBOT_IP=192.168.100.29
   ```

4. Restart the app:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

5. Test the robot connection:

   ```powershell
   curl.exe http://192.168.100.29/api/status
   ```

The status request should return JSON. If it does not, confirm that the laptop and robot are connected to the same non-guest Wi-Fi network and replace the example address with the robot's current `networkIP`.

---

## Running the App

### Desktop Application (Recommended)

Launch the native PyWebView desktop interface:

```powershell
python app.py
```

### Interactive CLI Mode

Run directly in your terminal for testing or headless environments:

```powershell
python sesame_companion.py
```

### Hardware-Free Command Tests

The command reliability tests use fake AI and robot objects, so they do not require the physical robot or a network connection:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests cover fallback command detection, AI command recovery, command aliases, unsupported commands, sidebar success responses, status verification failures, microphone transcription flow, and microphone timeout handling. Microphone tests use fakes, so they validate the application path without accessing a physical microphone.

---

## Features

### UI Quick Actions
- **Movements**: Walk, Dance, Crab Walk
- **Gestures**: Wave, Bow, Pushup, Swim, Cute Pose
- **System**: Demo Mode, Status Refresh, Stop Action
- **Interactive Chat**: Natural language dialogue with real-time feedback and response source telemetry
- **Dynamic Face Display**: Animated vector robot face responding to emotions, talking waveforms, and actions

### Supported Robot Commands
- **Locomotion**: `walk`, `crab`, `dance`
- **Gestures & Poses**: `cute`, `wave`, `bow`, `pushup`, `swim`, `freaky`, `worm`, `shake`, `shrug`, `point`, `stand`
- **Control**: `idle`, `stop`, `rest`, `dead`

### Robot Face Expressions
- **Base Emotions**: `default`, `happy`, `sad`, `angry`, `surprised`, `sleepy`, `love`, `excited`, `confused`
- **Talking Variants**: Mouth open/talk frames synced with speech audio levels

### Voice & Audio
- Speech-to-text via SpeechRecognition (Google Speech API)
- Optional microphone selection with `MIC_DEVICE_INDEX` or `MIC_DEVICE_NAME`.
- Text-to-speech options:
  - `pyttsx3` (fast, offline native speech)
  - `gemini` (cloud neural voice synthesis via `google-genai` + `pygame`)
- Configurable wake-word mode (`"hey sesame"`)

### AI Personas & Resiliency
- **Silly Persona**: Endearing, funny, childlike robot with comic timing and sassy remarks.
- **Intelligent Persona**: Articulate, polite, and helpful assistant.
- **Offline Fallback**: Automatic failover to pre-scripted conversational responses (`local_fallback.py`) if cloud APIs encounter network or timeout issues.

---

## Architecture & Codebase

- **`app.py`**: Native desktop entry point using `pywebview` with bidirectional Python-JavaScript API bridge.
- **`static/`**: Clean frontend interface:
  - `index.html`: Responsive glassmorphism layout with left quick controls, center canvas face & chat, right telemetry sidebar.
  - `style.css`: Modern dark theme with CSS animations, glowing neon accents, and smooth transitions.
  - `app.js`: Client-side logic, real-time face canvas rendering, chat bubbling, and backend synchronization.
- **`sesame_companion.py`**: Core companion logic:
  - `GroqInterface`: High-speed cloud model completions with strict JSON output formatting.
  - `GeminiInterface`: Modern `google.genai` SDK integration.
  - `VoiceInterface`: Speech recognition, microphone listening, and audio-reactive face talk animation.
  - `SesameRobotController`: HTTP REST client for sending commands and querying telemetry from the robot ESP32.
- **`local_fallback.py`**: Offline canned response bank for graceful degradation when disconnected.

---

## API Protocol

### Command Endpoint (`POST /api/command`)

```json
{"command": "walk"}
{"face": "happy"}
{"command": "cute", "face": "love"}
```

### Status Endpoint (`GET /api/status`)

```json
{
  "currentCommand": "idle",
  "currentFace": "happy",
  "networkConnected": true
}
```

---

## Finding Robot IP

1. Connect the Sesame robot via USB.
2. Open a serial monitor at `115200` baud.
3. Look for: `Connected to network! IP: X.X.X.X`
4. Set `SESAME_ROBOT_IP` in your `.env` file to this address.

---

## Troubleshooting

- **Robot connection error**:
  - Ensure the robot and your computer are on the same Wi-Fi subnet.
  - Test connectivity in your browser or terminal: `curl http://<SESAME_ROBOT_IP>/api/status`.
  - For offline testing without hardware, set `SESAME_ROBOT_IP=mock`.
- **Groq API key error**:
  - Confirm `GROQ_API_KEY` is set in your `.env` file and is valid.
- **Audio animation warning (pyaudio)**:
  - If `pyaudio` is unavailable, audio synchronization gracefully falls back to time-based mouth animation.

# companion-app

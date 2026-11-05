import unittest
from unittest.mock import patch

from app import Api
from local_fallback import detect_command, get_local_response
from sesame_companion import (
    SesameCompanionApp,
    SesameRobotController,
    VoiceInterface,
    normalize_interpretation,
    sr,
)


class FakeRobot:
    def __init__(self, command_result=None, status=None):
        self.command_result = command_result or {"status": "success"}
        self.status = status or {
            "currentCommand": "dance",
            "currentFace": "default",
        }
        self.commands = []

    def send_command(self, command, face=None):
        self.commands.append((command, face))
        return self.command_result

    def get_status(self):
        return self.status


class FakeAi:
    def __init__(self, interpretation):
        self.interpretation = interpretation

    def interpret_command(self, _user_input):
        return self.interpretation


class FakeMicrophone:
    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False


class FakeRecognizer:
    def __init__(self, text="dance"):
        self.text = text

    def adjust_for_ambient_noise(self, _source, duration):
        self.ambient_noise_duration = duration

    def listen(self, _source, timeout, phrase_time_limit):
        self.listen_args = (timeout, phrase_time_limit)
        return object()

    def recognize_sphinx(self, _audio):
        return self.text


class CommandReliabilityTests(unittest.TestCase):
    def test_fallback_maps_direct_request_to_command_json(self):
        result = get_local_response("Please make the robot dance")

        self.assertEqual(result["command"], "dance")
        self.assertIsNone(result["face"])

    def test_fallback_does_not_turn_conversation_into_command(self):
        self.assertIsNone(detect_command("Can you explain dance?"))
        self.assertIsNone(get_local_response("Can you explain dance?")["command"])

    def test_fallback_supports_command_alias_phrases(self):
        self.assertEqual(detect_command("Do a push-up"), "pushup")
        self.assertEqual(detect_command("Could you do a crab walk?"), "crab")

    def test_ai_missing_command_is_recovered_from_direct_request(self):
        robot = FakeRobot()
        app = SesameCompanionApp.__new__(SesameCompanionApp)
        app.ai = FakeAi({"response": "I will do it", "command": None, "face": "thinking"})
        app.robot = robot

        _, interpretation = app.process_input("Please make the robot dance")

        self.assertEqual(interpretation["command"], "dance")
        self.assertEqual(robot.commands, [("dance", None)])

    def test_normalization_removes_invalid_face_and_normalizes_alias(self):
        result = normalize_interpretation({"command": "push-up", "face": "unknown"})

        self.assertEqual(result["command"], "pushup")
        self.assertIsNone(result["face"])
        self.assertIn("response", result)
        self.assertIn("reasoning", result)

    def test_controller_rejects_unsupported_command_without_network(self):
        result = SesameRobotController("mock").send_command("not-a-command")

        self.assertIn("error", result)
        self.assertIn("Unsupported robot command", result["error"])

    def test_sidebar_api_reports_confirmed_command(self):
        api = Api.__new__(Api)
        api._app = type("Backend", (), {"robot": FakeRobot()})()

        result = api.send_command("dance")

        self.assertTrue(result["success"])
        self.assertEqual(result["command"], "dance")

    def test_sidebar_api_reports_status_verification_failure(self):
        api = Api.__new__(Api)
        robot = FakeRobot(status={"error": "robot unavailable"})
        api._app = type("Backend", (), {"robot": robot})()

        result = api.send_command("dance")

        self.assertIn("error", result)
        self.assertIn("status verification failed", result["error"])

    def test_microphone_input_path_returns_transcribed_text(self):
        voice = VoiceInterface(voice_enabled=True)
        captured_kwargs = {}

        def fake_capture(**kwargs):
            captured_kwargs.update(kwargs)
            return b"\x10\x00" * 8000

        voice._capture_phrase_pcm = fake_capture
        voice.transcribe_pcm = lambda pcm_bytes: "walk forward"

        result = voice.listen(timeout=3)

        self.assertEqual(result, "walk forward")
        self.assertEqual(captured_kwargs["timeout"], 3.0)
        self.assertTrue(captured_kwargs["allow_manual_stop"])

    def test_microphone_timeout_is_reported_as_no_input(self):
        voice = VoiceInterface(voice_enabled=True)

        def timeout_capture(**_kwargs):
            voice.last_listen_error = "No speech detected"
            return None

        voice._capture_phrase_pcm = timeout_capture

        self.assertIsNone(voice.listen())
        self.assertEqual(voice.last_listen_error, "No speech detected")

    def test_wake_phrase_extracts_trailing_command(self):
        voice = VoiceInterface(voice_enabled=True, wake_word="hey sesame")

        self.assertEqual(
            voice._extract_wake_remainder("Hey Sesame, do a dance!"),
            "do a dance!",
        )
        self.assertEqual(voice._extract_wake_remainder("Hey Sesame"), "")
        self.assertIsNone(voice._extract_wake_remainder("good morning friend"))

    def test_api_exposes_only_safe_public_methods_for_pywebview(self):
        api = Api()
        public_names = {name for name in dir(api) if not name.startswith("_")}
        expected = {
            "get_initial_state",
            "send_message",
            "send_command",
            "run_demo",
            "get_status",
            "toggle_listening",
            "stop_listening",
            "update_setting",
        }
        self.assertEqual(public_names, expected)

    def test_api_reports_transcribed_microphone_text(self):
        api = Api.__new__(Api)
        api._voice_enabled = True
        api._app = type("Backend", (), {"voice": type("Voice", (), {
            "listen": lambda _self: "wave"
        })()})()

        result = api.toggle_listening()

        self.assertEqual(result, {"text": "wave"})


if __name__ == "__main__":
    unittest.main()

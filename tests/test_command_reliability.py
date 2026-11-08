import unittest
from unittest.mock import patch

from app import Api
from local_fallback import detect_command, get_local_response
from sesame_companion import (
    HybridAIInterface,
    OllamaInterface,
    SesameCompanionApp,
    SesameRobotController,
    VoiceInterface,
    normalize_interpretation,
    sr,
    strip_emojis,
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
        self.assertEqual(detect_command("stop"), "rest")
        self.assertEqual(detect_command("take a rest"), "rest")

    def test_stop_command_normalizes_to_rest(self):
        self.assertEqual(normalize_interpretation({"command": "stop"})["command"], "rest")
        self.assertEqual(
            SesameRobotController("mock").send_command("stop"),
            {"status": "success", "mock": True},
        )
        self.assertEqual(
            SesameRobotController("mock").stop(),
            {"status": "success", "mock": True},
        )

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
        self.assertEqual(
            voice._extract_wake_remainder("Hey Sesame, Hey Sesame, Hey Sesame!"),
            "",
        )
        self.assertIsNone(voice._extract_wake_remainder("good morning friend"))

    def test_hallucination_filter_blocks_repetitions_and_foreign_scripts(self):
        voice = VoiceInterface(voice_enabled=True)
        voice.voice_language = "en"

        # Repeated wake-word loop from exhibition hall noise
        self.assertIsNone(
            voice._filter_hallucination("Hey Sesame, Hey Sesame, Hey Sesame, Hey Sesame.")
        )
        # Random Japanese & Urdu noise hallucinations
        self.assertIsNone(voice._filter_hallucination("ご視聴ありがとうございました"))
        self.assertIsNone(voice._filter_hallucination("آپ کا بہت شکریہ"))
        # Common Whisper silence hallucinations
        self.assertIsNone(voice._filter_hallucination("Thank you for watching."))
        # Legitimate English commands pass cleanly
        self.assertEqual(
            voice._filter_hallucination("Do a happy dance for me!"),
            "Do a happy dance for me!",
        )

    def test_close_talk_threshold_enforces_4000_floor_and_scales_in_loud_hall(self):
        self.assertEqual(VoiceInterface.compute_exhibition_threshold(120.0, 4000.0), 4000.0)
        self.assertEqual(VoiceInterface.compute_exhibition_threshold(2000.0, 4000.0), 5400.0)

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

    def test_hybrid_ai_auto_fails_over_from_cloud_to_local_ollama(self):
        hybrid = HybridAIInterface(groq_api_key=None, ollama_model="qwen2.5:0.5b", mode="auto")
        hybrid.personality = "intelligent"
        self.assertEqual(hybrid.groq.personality, "intelligent")
        self.assertEqual(hybrid.ollama.personality, "intelligent")

        hybrid.ollama.try_interpret = lambda text: {
            "command": None,
            "face": "happy",
            "response": "You have got this, friend!",
            "reasoning": "Intelligent companion encouragement",
            "source": "ollama:qwen2.5:0.5b",
        }

        result = hybrid.interpret_command("Give me a quick pep talk")
        self.assertEqual(result["source"], "ollama:qwen2.5:0.5b")
        self.assertIsNone(result["command"])
        self.assertEqual(result["face"], "happy")

    def test_ollama_interface_keeps_chat_motor_safe_and_honors_tricks(self):
        ollama = OllamaInterface(model="qwen2.5:0.5b")

        class FakeResp:
            status_code = 200

            def __init__(self, payload_text):
                self._payload_text = payload_text

            def json(self):
                return {"message": {"content": self._payload_text}}

        # Even if a tiny 0.5B model tries to set a random command during pure Q&A, it stays None
        with patch(
            "sesame_companion.requests.post",
            return_value=FakeResp('{"command":"swim","face":"happy","response":"Here is a joke!","reasoning":"fun"}'),
        ):
            chat_res = ollama.interpret_command("Tell me a short funny joke!")
            self.assertIsNone(chat_res["command"])
            self.assertEqual(chat_res["face"], "happy")

        # Direct trick requests always execute the requested command
        with patch(
            "sesame_companion.requests.post",
            return_value=FakeResp('{"command":"crab","face":null,"response":"Sideways crab time!","reasoning":"trick"}'),
        ):
            trick_res = ollama.interpret_command("Do a crab walk!")
            self.assertEqual(trick_res["command"], "crab")
            self.assertIsNone(trick_res["face"])

    def test_api_updates_robot_ip_and_ai_mode_cleanly(self):
        api = Api()
        with patch.object(Api, "_save_env_key") as save_mock:
            ip_res = api.update_setting("robot_ip", "http://192.168.43.108/")
            self.assertEqual(ip_res["ip"], "192.168.43.108")
            self.assertEqual(api._robot_ip, "192.168.43.108")
            save_mock.assert_any_call("SESAME_ROBOT_IP", "192.168.43.108")

            mode_res = api.update_setting("ai_mode", "ollama")
            self.assertEqual(api._ai_mode, "ollama")
            self.assertIn("ollama", mode_res["message"])
            save_mock.assert_any_call("AI_PROVIDER", "ollama")

    def test_emoji_filter_strips_emojis_from_ai_and_tts(self):
        raw = "Hey there, professors! Ready to wave your arms around? 🐍\n👋"
        self.assertEqual(
            strip_emojis(raw),
            "Hey there, professors! Ready to wave your arms around?",
        )
        normalized = normalize_interpretation({"command": "wave", "face": "happy", "response": raw})
        self.assertEqual(
            normalized["response"],
            "Hey there, professors! Ready to wave your arms around?",
        )
        self.assertEqual(
            VoiceInterface._clean_tts_text(raw + " [happy face]"),
            "Hey there, professors! Ready to wave your arms around?",
        )

    def test_cute_buddy_voice_shifts_vocal_tract_and_updates_style(self):
        import numpy as np
        src = (np.sin(np.linspace(0, 50.0, 4000)) * 12000.0).astype(np.float32)
        shifted, out_rate, wav_bytes = VoiceInterface._shift_vocal_tract_to_wav(
            src, orig_rate=16000, pitch_factor=1.32, out_rate=24000
        )
        self.assertEqual(out_rate, 24000)
        self.assertGreater(len(wav_bytes), 44)
        self.assertGreater(shifted.size, 0)

        api = Api()
        with patch.object(Api, "_save_env_key") as save_mock:
            res = api.update_setting("voice_style", "silly")
            self.assertEqual(api._voice_style, "silly")
            self.assertIn("silly", res["message"])
            save_mock.assert_any_call("PIPER_VOICE_STYLE", "silly")

    def test_study_coach_retains_rolling_conversation_history(self):
        hybrid = HybridAIInterface(groq_api_key=None, ollama_model="qwen2.5:0.5b", mode="ollama")
        hybrid.personality = "intelligent"

        captured_messages = []

        class FakeResp:
            status_code = 200

            def __init__(self, text):
                self._text = text

            def json(self):
                return {"message": {"content": self._text}}

        def fake_post(_url, json=None, timeout=None):
            captured_messages.append(list(json["messages"]))
            if len(captured_messages) == 1:
                return FakeResp('{"command":null,"face":"happy","response":"Sure! What gas do plants absorb during photosynthesis?"}')
            return FakeResp('{"command":null,"face":"excited","response":"Spot on! Carbon dioxide is right!"}')

        with patch("sesame_companion.requests.post", side_effect=fake_post):
            hybrid.interpret_command("I am studying photosynthesis, quiz me!")
            second = hybrid.interpret_command("Is it carbon dioxide?")

        self.assertEqual(second["face"], "excited")
        # Turn 2 includes system + Turn 1 user + Turn 1 assistant + Turn 2 user = 4 messages
        self.assertEqual(len(captured_messages[1]), 4)
        self.assertIn("photosynthesis", captured_messages[1][1]["content"])
        self.assertIn("What gas do plants absorb", captured_messages[1][2]["content"])


if __name__ == "__main__":
    unittest.main()

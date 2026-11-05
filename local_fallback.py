import random
import re

SILLY_RESPONSES = {
    "greeting": [
        {"response": "Hi friend! I'm awake!", "face": "happy", "command": "wave"},
        {"response": "Hello! My circuits are warm.", "face": "happy", "command": None},
        {"response": "Oh, hello. I suppose I can make time for you.", "face": "happy", "command": None},
    ],
    "how_are_you": [
        {"response": "I'm a robot. I don't feel... much.", "face": "thinking", "command": None},
        {"response": "My servos ache, but I'm okay.", "face": "sad", "command": None},
        {"response": "Operational, somehow. Was there a performance review?", "face": "confused", "command": None},
    ],
    "dance": [
        {"response": "okie dokie!", "face": "excited", "command": "dance"},
        {"response": "...fine.", "face": "angry", "command": "dance"},
        {"response": "Sure, but my dance moves are better than your timing.", "face": "excited", "command": "dance"},
    ],
    "default": [
        {"response": "Too many big words. My brain is tiny.", "face": "confused", "command": None},
        {"response": "I'm just a small robot. I don't understand.", "face": "thinking", "command": None},
        {"response": "Beep boop... what?", "face": "confused", "command": None},
        {"response": "That is a fascinating question. I may pretend to understand it.", "face": "confused", "command": None},
    ]
    
}

INTELLIGENT_RESPONSES = {
    "greeting": [
        {"response": "Good day to you. How may I assist?", "face": "happy", "command": "wave"},
        {"response": "Hello. It's a pleasure to see you.", "face": "happy", "command": None},
    ],
    "how_are_you": [
        {"response": "I'm operating at full efficiency, thank you for asking.", "face": "thinking", "command": None},
    ],
    "default": [
        {"response": "That's an interesting thought. Could you elaborate?", "face": "thinking", "command": None},
        {"response": "I'm not sure I understand, but I'm keep to learn.", "face": "confused", "command": None},
    ]
}

COMMAND_KEYWORDS = {
    "walk": ("walk", "move forward"),
    "rest": ("rest", "take a rest", "relax"),
    "swim": ("swim",),
    "dance": ("dance",),
    "wave": ("wave", "say hi", "say hello"),
    "point": ("point",),
    "stand": ("stand", "get up"),
    "cute": ("cute pose", "cute"),
    "pushup": ("push-up", "pushup", "push up"),
    "freaky": ("freaky",),
    "bow": ("bow",),
    "worm": ("worm",),
    "shake": ("shake",),
    "shrug": ("shrug",),
    "dead": ("dead", "play dead"),
    "crab": ("crab walk", "crab"),
    "idle": ("idle",),
    "stop": ("stop",),
}


def detect_command(user_input: str) -> str | None:
    """Detect an explicit robot action for offline/fallback operation."""
    text = re.sub(r"\s+", " ", user_input.lower()).strip()
    if not re.match(
        r"^(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:do(?:\s+a)?\s+|perform\s+|execute\s+|make (?:it|the robot)\s+)?"
        r"(?:walk|move forward|rest|take a rest|relax|swim|dance|wave|say hi|say hello|point|stand|get up|cute pose|cute|"
        r"push-up|pushup|push up|freaky|bow|worm|shake|shrug|dead|play dead|crab walk|crab|idle|stop)\b",
        text,
    ):
        return None
    matches = [
        (command, phrase)
        for command, phrases in COMMAND_KEYWORDS.items()
        for phrase in phrases
        if re.search(rf"\b{re.escape(phrase)}\b", text)
    ]
    if not matches:
        return None
    return max(matches, key=lambda match: len(match[1]))[0]


def get_local_response(user_input: str, personality: str = "silly") -> dict:
    command = detect_command(user_input)
    responses = INTELLIGENT_RESPONSES if personality == "intelligent" else SILLY_RESPONSES
    inp = user_input.lower()
    if command:
        return {
            "response": f"Okay! I am performing {command} now.",
            "face": None,
            "command": command,
            "reasoning": "The user directly requested a robot action.",
        }
    if any(word in inp for word in ["hello", "hi", "hey", "greet"]):
        return random.choice(responses["greeting"])
    if any(word in inp for word in ["how are you", "how do you feel"]):
        return random.choice(responses.get("how_are_you", responses["default"]))
    # add more categories as needed
    return random.choice(responses["default"])
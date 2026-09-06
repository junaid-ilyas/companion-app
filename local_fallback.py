import random

SILLY_RESPONSES = {
    "greeting": [
        {"response": "Hi friend! I'm awake!", "face": "happy", "command": "wave"},
        {"response": "Hello! My circuits are warm.", "face": "happy", "command": None},
    ],
    "how_are_you": [
        {"response": "I'm a robot. I don't feel... much.", "face": "thinking", "command": None},
        {"response": "My servos ache, but I'm okay.", "face": "sad", "command": None},
    ],
    "dance": [
        {"response": "okie dokie!", "face": "excited", "command": "dance"},
        {"response": "...fine.", "face": "angry", "command": "dance"},
    ],
    "default": [
        {"response": "Too many big words. My brain is tiny.", "face": "confused", "command": None},
        {"response": "I'm just a small robot. I don't understand.", "face": "thinking", "command": None},
        {"response": "Beep boop... what?", "face": "confused", "command": None},
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

def get_local_response(user_input: str, personality: str = "silly") -> dict:
    responses = INTELLIGENT_RESPONSES if personality == "intelligent" else SILLY_RESPONSES
    inp = user_input.lower()
    if any(word in inp for word in ["hello", "hi", "hey", "greet"]):
        return random.choice(responses["greeting"])
    if any(word in inp for word in ["how are you", "how do you feel"]):
        return random.choice(responses.get("how_are_you", responses["default"]))
    # add more categories as needed
    return random.choice(responses["default"])
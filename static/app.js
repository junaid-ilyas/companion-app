/* ============================================================
   Sesame Companion — "Sunny Buddy" Client-Side Application Logic
   ============================================================ */

// ── State ───────────────────────────────────────────────────
let isListening = false;
let isSpeaking = false;
let currentFace = 'happy';
let currentPersona = 'silly';
let welcomeVisible = true;

const FACE_CAPTIONS = {
  default:   'Ready to hang out',
  happy:     'Feeling cheerful & curious',
  excited:   'Bursting with energy!',
  love:      'Happy you are here!',
  surprised: 'Whoa — wide awake!',
  confused:  'Hmm... scratching my tiny circuits',
  thinking:  'Thinking carefully...',
  sad:       'Feeling a little blue',
  angry:     'Acting playfully grumpy',
  sleepy:    'Cozy & resting',
};

const PROMPTS_BY_PERSONA = {
  silly: [
    { label: 'Say hello', prompt: 'Hello Sesame! Wave hi to everyone!' },
    { label: 'Tell a joke', prompt: 'Tell me a short funny joke!' },
    { label: 'Happy dance', prompt: 'Show us your happy dance!' },
    { label: 'Playful roast', prompt: 'Roast me playfully in two short sentences.' },
  ],
  intelligent: [
    { label: 'Pep talk', prompt: 'Give me a warm, encouraging pep talk for my day!' },
    { label: 'Brain teaser', prompt: 'Ask me one quick brain-teaser question and test my answer!' },
    { label: 'Explain simply', prompt: 'Explain how your servo motors let you walk in two simple sentences.' },
    { label: 'Celebrate together', prompt: 'We hit our goal today! Celebrate with a happy dance!' },
  ],
};

// ── Sunny Buddy Animated Face Engine ────────────────────────
const RobotFace = (() => {
  let svg = null;
  let tick = 0;
  let isBlinking = false;
  let speaking = false;
  let listening = false;

  const PALETTE = {
    primary: '#FEF3C7',
    accent:  '#F59E0B',
    blush:   '#FDA4AF',
    heart:   '#FB7185',
    sleepy:  '#D6B370',
    pupil:   '#1D1B18',
  };

  function init() {
    svg = document.getElementById('robot-face-svg');
    if (!svg) return;
    scheduleBlink();
    animate();
  }

  function setFace(name, customCaption) {
    currentFace = name || 'default';
    if (customCaption) {
      setMoodCaption(customCaption);
    } else if (!speaking && !listening) {
      setMoodCaption(FACE_CAPTIONS[currentFace] || FACE_CAPTIONS.default);
    }
  }

  function setSpeaking(val) {
    speaking = Boolean(val);
    if (speaking) {
      setMoodCaption('Sesame is talking...');
    } else if (!listening) {
      setMoodCaption(FACE_CAPTIONS[currentFace] || FACE_CAPTIONS.default);
    }
  }

  function setListening(val) {
    listening = Boolean(val);
    const screen = document.getElementById('buddy-screen');
    if (screen) screen.classList.toggle('listening-glow', listening);
    if (listening) {
      setMoodCaption('Listening — speak close to the mic...');
    } else if (!speaking) {
      setMoodCaption(FACE_CAPTIONS[currentFace] || FACE_CAPTIONS.default);
    }
  }

  function scheduleBlink() {
    const delay = 2800 + Math.random() * 2800;
    setTimeout(() => {
      if (currentFace !== 'sleepy' && !speaking) {
        isBlinking = true;
        setTimeout(() => {
          isBlinking = false;
          scheduleBlink();
        }, 125);
      } else {
        scheduleBlink();
      }
    }, delay);
  }

  function animate() {
    tick++;
    draw();
    requestAnimationFrame(animate);
  }

  function draw() {
    if (!svg) return;
    const breath = Math.sin(tick * 0.05) * (currentFace === 'sleepy' ? 1.2 : 2.8);
    const ey = 88 + breath;
    const lx = 98;
    const rx = 222;
    const face = listening ? 'surprised' : currentFace;

    let s = '';

    // Soft warm cheek blush on joyful expressions
    if (face === 'happy' || face === 'love' || face === 'excited') {
      s += `<ellipse cx="${lx - 26}" cy="${ey + 34}" rx="18" ry="9" fill="${PALETTE.blush}" opacity="0.32"/>`;
      s += `<ellipse cx="${rx + 26}" cy="${ey + 34}" rx="18" ry="9" fill="${PALETTE.blush}" opacity="0.32"/>`;
    }

    // Eyes
    if (isBlinking) {
      s += `<line x1="${lx - 24}" y1="${ey}" x2="${lx + 24}" y2="${ey}" stroke="${PALETTE.primary}" stroke-width="11" stroke-linecap="round"/>`;
      s += `<line x1="${rx - 24}" y1="${ey}" x2="${rx + 24}" y2="${ey}" stroke="${PALETTE.primary}" stroke-width="11" stroke-linecap="round"/>`;
    } else if (face === 'happy') {
      s += `<path d="M ${lx - 26} ${ey + 10} Q ${lx} ${ey - 26} ${lx + 26} ${ey + 10}" fill="none" stroke="${PALETTE.primary}" stroke-width="14" stroke-linecap="round"/>`;
      s += `<path d="M ${rx - 26} ${ey + 10} Q ${rx} ${ey - 26} ${rx + 26} ${ey + 10}" fill="none" stroke="${PALETTE.primary}" stroke-width="14" stroke-linecap="round"/>`;
    } else if (face === 'love') {
      [lx, rx].forEach((x) => {
        s += `<path d="M ${x} ${ey + 22} C ${x - 30} ${ey + 4} ${x - 30} ${ey - 24} ${x} ${ey - 8} C ${x + 30} ${ey - 24} ${x + 30} ${ey + 4} ${x} ${ey + 22} Z" fill="${PALETTE.heart}"/>`;
      });
    } else if (face === 'excited') {
      [lx, rx].forEach((x) => {
        s += `<rect x="${x - 21}" y="${ey - 29}" width="42" height="56" rx="21" fill="${PALETTE.primary}"/>`;
        s += `<circle cx="${x + 7}" cy="${ey - 11}" r="6.5" fill="${PALETTE.pupil}" opacity="0.28"/>`;
      });
    } else if (face === 'surprised') {
      const pulse = listening ? Math.sin(tick * 0.16) * 2.5 : 0;
      const r = 22 + pulse;
      [lx, rx].forEach((x) => {
        s += `<circle cx="${x}" cy="${ey}" r="${r}" fill="none" stroke="${PALETTE.primary}" stroke-width="11"/>`;
        s += `<circle cx="${x}" cy="${ey}" r="5.5" fill="${PALETTE.accent}"/>`;
      });
    } else if (face === 'angry') {
      [lx, rx].forEach((x) => {
        s += `<rect x="${x - 22}" y="${ey - 5}" width="44" height="22" rx="11" fill="${PALETTE.primary}"/>`;
      });
      s += `<line x1="${lx - 25}" y1="${ey - 15}" x2="${lx + 21}" y2="${ey - 5}" stroke="${PALETTE.accent}" stroke-width="6.5" stroke-linecap="round"/>`;
      s += `<line x1="${rx - 21}" y1="${ey - 5}" x2="${rx + 25}" y2="${ey - 15}" stroke="${PALETTE.accent}" stroke-width="6.5" stroke-linecap="round"/>`;
    } else if (face === 'sad') {
      s += `<path d="M ${lx - 24} ${ey - 4} Q ${lx} ${ey + 18} ${lx + 24} ${ey - 4}" fill="none" stroke="${PALETTE.primary}" stroke-width="12" stroke-linecap="round"/>`;
      s += `<path d="M ${rx - 24} ${ey - 4} Q ${rx} ${ey + 18} ${rx + 24} ${ey - 4}" fill="none" stroke="${PALETTE.primary}" stroke-width="12" stroke-linecap="round"/>`;
    } else if (face === 'sleepy') {
      s += `<path d="M ${lx - 24} ${ey + 4} Q ${lx} ${ey + 14} ${lx + 24} ${ey + 4}" fill="none" stroke="${PALETTE.sleepy}" stroke-width="10" stroke-linecap="round"/>`;
      s += `<path d="M ${rx - 24} ${ey + 4} Q ${rx} ${ey + 14} ${rx + 24} ${ey + 4}" fill="none" stroke="${PALETTE.sleepy}" stroke-width="10" stroke-linecap="round"/>`;
    } else if (face === 'confused' || face === 'thinking') {
      s += `<rect x="${lx - 17}" y="${ey - 22}" width="34" height="44" rx="17" fill="${PALETTE.primary}"/>`;
      s += `<rect x="${rx - 19}" y="${ey - 12}" width="38" height="26" rx="13" fill="${PALETTE.primary}"/>`;
      s += `<path d="M ${rx - 20} ${ey - 24} Q ${rx} ${ey - 34} ${rx + 20} ${ey - 22}" fill="none" stroke="${PALETTE.accent}" stroke-width="5.5" stroke-linecap="round"/>`;
    } else {
      [lx, rx].forEach((x) => {
        s += `<rect x="${x - 18}" y="${ey - 22}" width="36" height="44" rx="18" fill="${PALETTE.primary}"/>`;
      });
    }

    // Mouth / Waveform
    if (speaking) {
      for (let i = 0; i < 7; i++) {
        const h = 5 + Math.abs(Math.sin(tick * 0.24 + i * 0.72)) * 16;
        const bx = 124 + i * 12;
        s += `<line x1="${bx}" y1="${ey + 42 - h}" x2="${bx}" y2="${ey + 42 + h}" stroke="${PALETTE.accent}" stroke-width="6" stroke-linecap="round"/>`;
      }
    } else if (listening) {
      for (let i = 0; i < 5; i++) {
        const h = 3 + Math.abs(Math.sin(tick * 0.14 + i * 0.9)) * 8;
        const bx = 136 + i * 12;
        s += `<line x1="${bx}" y1="${ey + 44 - h}" x2="${bx}" y2="${ey + 44 + h}" stroke="${PALETTE.primary}" stroke-width="5" stroke-linecap="round" opacity="0.85"/>`;
      }
    } else if (face === 'happy' || face === 'love') {
      s += `<path d="M 142 ${ey + 36} Q 160 ${ey + 52} 178 ${ey + 36}" fill="none" stroke="${PALETTE.accent}" stroke-width="7" stroke-linecap="round"/>`;
    } else if (face === 'excited') {
      s += `<path d="M 142 ${ey + 34} Q 160 ${ey + 56} 178 ${ey + 34} Z" fill="${PALETTE.accent}"/>`;
    } else if (face === 'sad') {
      s += `<path d="M 144 ${ey + 48} Q 160 ${ey + 36} 176 ${ey + 48}" fill="none" stroke="${PALETTE.accent}" stroke-width="6" stroke-linecap="round"/>`;
    } else if (face === 'angry') {
      s += `<path d="M 146 ${ey + 42} Q 160 ${ey + 35} 174 ${ey + 41}" fill="none" stroke="${PALETTE.primary}" stroke-width="6" stroke-linecap="round"/>`;
    } else if (face === 'sleepy') {
      s += `<circle cx="160" cy="${ey + 42}" r="5" fill="none" stroke="${PALETTE.sleepy}" stroke-width="4"/>`;
    } else {
      s += `<path d="M 146 ${ey + 37} Q 160 ${ey + 46} 174 ${ey + 37}" fill="none" stroke="${PALETTE.accent}" stroke-width="6" stroke-linecap="round"/>`;
    }

    svg.innerHTML = s;
  }

  return { init, setFace, setSpeaking, setListening };
})();

function setMoodCaption(text) {
  const el = document.getElementById('mood-caption');
  if (el && text) el.textContent = text;
}

function logOperatorStatus(text) {
  const logEl = document.getElementById('operator-log');
  if (logEl && text) logEl.textContent = text;
}

// ── Modal & Persona Controls ────────────────────────────────
function toggleSettingsModal(open) {
  const modal = document.getElementById('settings-modal');
  if (modal) modal.classList.toggle('open', Boolean(open));
  if (open && window.pywebview && window.pywebview.api) {
    refreshStatus();
  }
}

function populateMicDevices(devices, selectedValue) {
  const sel = document.getElementById('mic-device-select');
  if (!sel || !Array.isArray(devices)) return;
  const current = selectedValue !== undefined ? String(selectedValue) : sel.value;
  sel.innerHTML = '<option value="">System Default Mic</option>';
  devices.forEach((d) => {
    const opt = document.createElement('option');
    opt.value = String(d.index);
    opt.textContent = d.name;
    sel.appendChild(opt);
  });
  sel.value = current;
}

function renderPromptChips(persona) {
  const row = document.getElementById('prompt-row');
  if (!row) return;
  const list = PROMPTS_BY_PERSONA[persona] || PROMPTS_BY_PERSONA.silly;
  row.innerHTML = '';
  list.forEach((item) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'prompt-chip';
    btn.textContent = item.label;
    btn.addEventListener('click', () => {
      const input = document.getElementById('chat-input');
      input.value = item.prompt;
      sendMessage();
    });
    row.appendChild(btn);
  });
}

function syncPersonaUI(persona) {
  currentPersona = persona === 'intelligent' ? 'intelligent' : 'silly';
  const sillyBtn = document.getElementById('persona-silly-btn');
  const intelBtn = document.getElementById('persona-intelligent-btn');
  if (sillyBtn) sillyBtn.classList.toggle('active', currentPersona === 'silly');
  if (intelBtn) intelBtn.classList.toggle('active', currentPersona === 'intelligent');

  const radio = document.querySelector(`input[name="personality"][value="${currentPersona}"]`);
  if (radio) radio.checked = true;

  const heading = document.getElementById('chat-heading');
  const chip = document.getElementById('personality-chip');
  if (currentPersona === 'intelligent') {
    if (heading) heading.textContent = 'Smart Chat with Sesame';
    if (chip) chip.textContent = 'Intelligent AI pet companion — calm, curious, and articulate';
    RobotFace.setFace('happy', 'Calm, curious & ready to help!');
  } else {
    if (heading) heading.textContent = 'Hang out with Sesame';
    if (chip) chip.textContent = 'Playful AI pet companion — press Voice and speak close to the mic';
    RobotFace.setFace('happy', 'Feeling cheerful & curious');
  }

  renderPromptChips(currentPersona);
}

async function selectPersona(persona) {
  syncPersonaUI(persona);
  await updateSetting('personality', currentPersona, { silentChat: true });
}

async function triggerStretchBreak() {
  highlightTrickButton('pushup');
  RobotFace.setFace('excited', 'Stretch break — let us move!');
  const input = document.getElementById('chat-input');
  input.value = 'Time for a quick desk stretch break! Do pushups with me and cheer me on!';
  await sendMessage();
}

const triggerStudyBreak = triggerStretchBreak;

// ── Chat System ─────────────────────────────────────────────
function hideWelcome() {
  if (!welcomeVisible) return;
  const ws = document.getElementById('welcome-screen');
  if (ws) ws.remove();
  welcomeVisible = false;
}

function cleanCompanionReply(text) {
  if (!text) return '';
  return String(text)
    .replace(/\s*\[[^\]]*face\]\s*$/i, '')
    .replace(/[\p{Extended_Pictographic}\p{Emoji_Presentation}\uFE0E\uFE0F\u200D\u20E3]+/gu, '')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}

function isTechnicalSystemLog(text) {
  if (!text) return true;
  const t = String(text).trim();
  return (
    t.startsWith('[OK]') ||
    t.startsWith('[Config]') ||
    t.startsWith('[Voice]') ||
    t.startsWith('AI source:') ||
    t.startsWith('Personality set to:') ||
    t.startsWith('TTS engine:') ||
    t.startsWith('Executing:')
  );
}

function addMessage(sender, text) {
  if (!text) return;

  // Keep technical telemetry inside the operator modal instead of companion chat
  if (sender === 'system' && isTechnicalSystemLog(text)) {
    logOperatorStatus(text);
    return;
  }

  if (sender === 'user' || sender === 'sesame') {
    hideWelcome();
  }

  const container = document.getElementById('messages-container');
  if (!container) return;

  const timeStr = new Date().toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });

  if (sender === 'system' || sender === 'error' || sender === 'success') {
    logOperatorStatus(text);
    const div = document.createElement('div');
    div.className = 'system-message';
    const typeClass = sender === 'error' ? 'error' : sender === 'success' ? 'success' : 'info';
    div.innerHTML = `<div class="system-pill ${typeClass}">${escapeHtml(text)}</div>`;
    container.appendChild(div);
  } else {
    const senderName = sender === 'user' ? 'You' : 'Sesame';
    const displayBody = sender === 'sesame' ? cleanCompanionReply(text) : text;
    const div = document.createElement('div');
    div.className = `message ${sender}`;
    div.innerHTML = `
      <div class="message-bubble">
        <div class="message-meta">${senderName} · ${timeStr}</div>
        <div class="message-text">${escapeHtml(displayBody)}</div>
      </div>`;
    container.appendChild(div);
  }

  requestAnimationFrame(() => {
    container.scrollTop = container.scrollHeight;
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function setTyping(active) {
  const el = document.getElementById('typing-indicator');
  const container = document.getElementById('messages-container');
  if (!el || !container) return;

  if (active) {
    container.appendChild(el);
    el.classList.add('active');
    RobotFace.setFace('thinking', 'Thinking of a reply...');
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  } else {
    el.classList.remove('active');
  }
}

// ── API Bridge (pywebview) ──────────────────────────────────
function waitForApi() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) {
      resolve();
    } else {
      window.addEventListener('pywebviewready', resolve);
    }
  });
}

async function sendMessage({ preserveInput = false } = {}) {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;

  if (!preserveInput) {
    input.value = '';
  }
  addMessage('user', text);
  setTyping(true);

  try {
    const result = await window.pywebview.api.send_message(text);
    setTyping(false);

    if (result.source) {
      logOperatorStatus(`AI source: ${result.source}`);
    }
    if (result.response) {
      addMessage('sesame', result.response);
    }
    if (result.face) {
      RobotFace.setFace(result.face);
      const faceMetric = document.getElementById('metric-face');
      if (faceMetric) faceMetric.textContent = result.face;
    } else {
      RobotFace.setFace('happy');
    }
    if (result.command) {
      highlightTrickButton(result.command);
      const cmdMetric = document.getElementById('metric-command');
      if (cmdMetric) cmdMetric.textContent = result.command;
    }
    if (result.error) {
      logOperatorStatus(`Note: ${result.error}`);
    }
  } catch (err) {
    setTyping(false);
    addMessage('error', 'Could not reach Sesame backend: ' + err);
  }
}

function highlightTrickButton(cmd) {
  document.querySelectorAll('.toy-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.cmd === cmd);
  });
}

async function triggerTrick(btn, cmd, previewFace, captionText) {
  highlightTrickButton(cmd);
  RobotFace.setFace(previewFace, captionText);
  await sendCommand(cmd, { quietSuccess: true });
}

async function triggerRest() {
  highlightTrickButton('');
  RobotFace.setFace('sleepy', 'Cozy & resting');
  await sendCommand('rest', { quietSuccess: true });
}

async function sendCommand(cmd, { quietSuccess = false } = {}) {
  logOperatorStatus(`Action: ${cmd}`);
  try {
    const result = await window.pywebview.api.send_command(cmd);
    if (result.error) {
      logOperatorStatus(`Robot offline (${cmd}): ${result.error}`);
    } else {
      const confirmedCommand = result.command || cmd;
      if (!quietSuccess) {
        addMessage('success', `Sesame started ${confirmedCommand}!`);
      }
      if (result.face) {
        RobotFace.setFace(result.face);
        const faceMetric = document.getElementById('metric-face');
        if (faceMetric) faceMetric.textContent = result.face;
      }
      const cmdMetric = document.getElementById('metric-command');
      if (cmdMetric) cmdMetric.textContent = confirmedCommand;
    }
  } catch (err) {
    logOperatorStatus('Command error: ' + err);
  }
}

async function runDemo() {
  const demoBtn = document.getElementById('demo-btn');
  if (demoBtn) demoBtn.disabled = true;
  RobotFace.setFace('excited', 'Showtime routine!');
  addMessage('system', 'Sesame is performing its showcase routine!');
  try {
    const res = await window.pywebview.api.run_demo();
    if (res && res.error) {
      logOperatorStatus(`Demo note: ${res.error}`);
    } else {
      RobotFace.setFace('happy', 'Ta-da! Routine finished!');
    }
  } catch (err) {
    logOperatorStatus('Demo error: ' + err);
  } finally {
    if (demoBtn) demoBtn.disabled = false;
  }
}

async function refreshStatus() {
  try {
    const status = await window.pywebview.api.get_status();
    applyStatus(status);
    logOperatorStatus(status && status.connected ? 'Robot link verified.' : 'Robot currently offline.');
  } catch (err) {
    logOperatorStatus('Refresh failed: ' + err);
  }
}

async function toggleListening() {
  const micBtn = document.getElementById('mic-btn');
  const micLabel = document.getElementById('mic-btn-label');

  // Clicking Voice while already listening finishes recording immediately
  if (isListening) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.stop_listening) {
      await window.pywebview.api.stop_listening();
    }
    return;
  }

  isListening = true;
  micBtn.classList.add('listening');
  if (micLabel) micLabel.textContent = 'Done';
  RobotFace.setListening(true);

  try {
    const result = await window.pywebview.api.toggle_listening();
    if (result && result.text) {
      const input = document.getElementById('chat-input');
      input.value = result.text;
      await new Promise((resolve) => requestAnimationFrame(resolve));
      await sendMessage({ preserveInput: false });
    } else {
      const msg = (result && result.error) || 'Could not hear clearly — speak closer to the mic';
      addMessage('system', msg);
    }
  } catch (err) {
    addMessage('error', 'Microphone error: ' + err);
  } finally {
    isListening = false;
    micBtn.classList.remove('listening');
    if (micLabel) micLabel.textContent = 'Voice';
    RobotFace.setListening(false);
  }
}

// Called from Python background wake-word listener when "Hey Sesame" triggers
function onWakeWordTranscript(text) {
  if (!text) return;
  const input = document.getElementById('chat-input');
  input.value = text;
  sendMessage({ preserveInput: false });
}

async function updateSetting(key, value, { silentChat = false } = {}) {
  try {
    const result = await window.pywebview.api.update_setting(key, value);
    if (result && result.error) {
      logOperatorStatus(result.error);
      return result;
    }
    if (result && result.ai_status) {
      applyAiStatus(result.ai_status);
    }
    if (result && result.ip) {
      applyIpAddress(result.ip);
    }
    if (result && result.message) {
      logOperatorStatus(result.message);
      if (!silentChat && (key === 'wake_word' || key === 'voice')) {
        addMessage('system', result.message);
      }
    }
    if (key === 'personality') {
      syncPersonaUI(value);
    }
    return result;
  } catch (err) {
    logOperatorStatus('Settings error: ' + err);
    return null;
  }
}

async function saveRobotIp() {
  const ipInput = document.getElementById('robot-ip-input');
  if (!ipInput) return;
  const val = ipInput.value.trim();
  if (!val) {
    logOperatorStatus('Enter a valid Robot Wi-Fi IP first.');
    return;
  }
  await updateSetting('robot_ip', val, { silentChat: true });
}

function syncVoiceStyleUI(style) {
  const active = style || 'cute';
  ['cute', 'silly', 'natural'].forEach((k) => {
    const btn = document.getElementById(`vstyle-${k}`);
    if (btn) btn.classList.toggle('active', k === active);
  });
}

async function selectVoiceStyle(style) {
  syncVoiceStyleUI(style);
  await updateSetting('voice_style', style, { silentChat: true });
}

// ── Status Updates (called from Python via evaluate_js) ─────
function applyStatus(status) {
  if (!status) return;
  if (status.mic_devices) {
    populateMicDevices(status.mic_devices);
  }

  const connDot = document.getElementById('conn-dot');
  const connText = document.getElementById('conn-status-text');
  const pillLabel = document.getElementById('robot-status-text');

  if (status.connected) {
    if (connDot) connDot.className = 'status-dot online';
    if (connText) connText.textContent = 'Connected';
    if (pillLabel) {
      pillLabel.className = 'conn-pill-label online';
      pillLabel.textContent = 'Connected';
    }
  } else {
    if (connDot) connDot.className = 'status-dot offline';
    if (connText) connText.textContent = 'Offline';
    if (pillLabel) {
      pillLabel.className = 'conn-pill-label';
      pillLabel.textContent = 'Offline';
    }
  }

  if (status.face) {
    RobotFace.setFace(status.face);
    const faceMetric = document.getElementById('metric-face');
    if (faceMetric) faceMetric.textContent = status.face;
  }
  if (status.command !== undefined) {
    const cmd = status.command || 'none';
    const cmdMetric = document.getElementById('metric-command');
    if (cmdMetric) cmdMetric.textContent = cmd;
  }
}

function applyAiStatus(label) {
  const dot = document.getElementById('ai-dot');
  const text = document.getElementById('ai-status-text');
  if (text) text.textContent = label;

  if (!dot) return;
  if (label.toLowerCase().includes('missing') || label.toLowerCase().includes('fallback')) {
    dot.className = 'status-dot checking';
  } else if (label.toLowerCase().includes('ready')) {
    dot.className = 'status-dot online';
  } else {
    dot.className = 'status-dot checking';
  }
}

function applyIpAddress(ip) {
  const el = document.getElementById('metric-ip');
  if (el) el.textContent = ip;
  const ipInput = document.getElementById('robot-ip-input');
  if (ipInput && document.activeElement !== ipInput) {
    ipInput.value = ip;
  }
}

function setSpeakingState(val, face) {
  isSpeaking = Boolean(val);
  if (face) {
    RobotFace.setFace(face);
    const faceMetric = document.getElementById('metric-face');
    if (faceMetric) faceMetric.textContent = face;
  }
  RobotFace.setSpeaking(isSpeaking);
}

// ── Initialization & Keyboard Shortcuts ─────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('chat-input');
  const ipInput = document.getElementById('robot-ip-input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  if (ipInput) {
    ipInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        saveRobotIp();
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      toggleSettingsModal(false);
    }
  });

  RobotFace.init();
  syncPersonaUI('silly');

  waitForApi().then(async () => {
    try {
      const state = await window.pywebview.api.get_initial_state();
      if (state.ip) applyIpAddress(state.ip);
      if (state.ai_status) applyAiStatus(state.ai_status);
      if (state.status) applyStatus(state.status);

      if (state.voice_enabled !== undefined) {
        const vt = document.getElementById('voice-toggle');
        if (vt) vt.checked = state.voice_enabled;
      }
      if (state.wake_word_mode !== undefined) {
        const wt = document.getElementById('wake-toggle');
        if (wt) wt.checked = state.wake_word_mode;
      }
      if (state.tts_engine) {
        const radio = document.querySelector(`input[name="tts"][value="${state.tts_engine}"]`);
        if (radio) radio.checked = true;
      }
      if (state.voice_style) {
        syncVoiceStyleUI(state.voice_style);
      }
      if (state.mic_devices) {
        populateMicDevices(state.mic_devices, state.mic_device || '');
      }
      if (state.ai_mode) {
        const aiRadio = document.querySelector(`input[name="ai_mode"][value="${state.ai_mode}"]`);
        if (aiRadio) aiRadio.checked = true;
      }
      if (state.personality) {
        syncPersonaUI(state.personality);
      }
    } catch (err) {
      console.error('Init state error:', err);
    }
  });
});

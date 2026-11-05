/* ============================================================
   Sesame Robot Companion App — Client-Side Application Logic
   ============================================================ */

// ── State ───────────────────────────────────────────────────
let isListening = false;
let isSpeaking = false;
let currentFace = 'default';
let welcomeVisible = true;
let liveRecognition = null;

// ── Robot Face Animation Engine ─────────────────────────────
const RobotFace = (() => {
  let svg = null;
  let tick = 0;
  let blinkTimer = null;
  let isBlinking = false;
  let speaking = false;
  let animFrameId = null;

  const COLORS = {
    glowOuter: '#8f3528',
    glowMid:   '#c84f3b',
    glowInner: '#e7674d',
    mouthColor:'#f4b860',
    mouthGlow: '#875d2d',
    bg:        '#f3ece4',
    screen:    '#d8c7b9',
    screenIn:  '#fffaf4',
    heartFill: '#5a1827',
    heartStroke:'#e63946',
    heartInner:'#ff4d6d',
    sleepyDim: '#a77b51',
    sleepyMid: '#c99557',
    sleepyBright:'#e0ad68',
  };

  function init() {
    svg = document.getElementById('robot-face-svg');
    if (!svg) return;
    scheduleBlink();
    animate();
  }

  function setFace(name) {
    currentFace = name || 'default';
  }

  function setSpeaking(val) {
    speaking = val;
  }

  function scheduleBlink() {
    const delay = 3000 + Math.random() * 3000;
    blinkTimer = setTimeout(() => {
      if (currentFace !== 'sleepy' && currentFace !== 'sad') {
        isBlinking = true;
        setTimeout(() => {
          isBlinking = false;
          scheduleBlink();
        }, 120);
      } else {
        scheduleBlink();
      }
    }, delay);
  }

  function animate() {
    tick++;
    draw();
    animFrameId = requestAnimationFrame(animate);
  }

  // ── SVG helpers ──
  function clear() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
  }

  function el(tag, attrs) {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  function addCircle(cx, cy, r, fill, stroke, strokeWidth) {
    svg.appendChild(el('circle', {
      cx, cy, r,
      fill: fill || 'none',
      stroke: stroke || 'none',
      'stroke-width': strokeWidth || 0,
    }));
  }

  function addLine(x1, y1, x2, y2, color, width, cap) {
    svg.appendChild(el('line', {
      x1, y1, x2, y2,
      stroke: color,
      'stroke-width': width,
      'stroke-linecap': cap || 'round',
    }));
  }

  function addEllipse(cx, cy, rx, ry, fill, stroke, sw) {
    svg.appendChild(el('ellipse', {
      cx, cy, rx, ry,
      fill: fill || 'none',
      stroke: stroke || 'none',
      'stroke-width': sw || 0,
    }));
  }

  function addArc(cx, cy, r, startAngle, endAngle, color, width) {
    const start = polarToCartesian(cx, cy, r, endAngle);
    const end = polarToCartesian(cx, cy, r, startAngle);
    const largeArc = endAngle - startAngle <= 180 ? '0' : '1';
    const d = `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
    svg.appendChild(el('path', {
      d,
      fill: 'none',
      stroke: color,
      'stroke-width': width,
      'stroke-linecap': 'round',
    }));
  }

  function polarToCartesian(cx, cy, r, angleDeg) {
    const rad = (angleDeg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function addCurve(points, color, width) {
    if (points.length < 4) return;
    let d = `M ${points[0]} ${points[1]}`;
    if (points.length === 6) {
      d += ` Q ${points[2]} ${points[3]} ${points[4]} ${points[5]}`;
    } else if (points.length >= 8) {
      // Use cubic bezier for smooth curves
      const mx = (points[0] + points[points.length - 2]) / 2;
      d = `M ${points[0]} ${points[1]} Q ${points[2]} ${points[3]} ${points[4]} ${points[5]}`;
    }
    svg.appendChild(el('path', {
      d,
      fill: 'none',
      stroke: color,
      'stroke-width': width,
      'stroke-linecap': 'round',
    }));
  }

  function addSmoothLine(pts, color, width) {
    // pts = [x1,y1, x2,y2, x3,y3] — draw quadratic through midpoint
    if (pts.length === 6) {
      const d = `M ${pts[0]} ${pts[1]} Q ${pts[2]} ${pts[3]} ${pts[4]} ${pts[5]}`;
      svg.appendChild(el('path', {
        d, fill: 'none', stroke: color, 'stroke-width': width, 'stroke-linecap': 'round'
      }));
    }
  }

  function addHeart(cx, cy, size, fill, stroke, sw) {
    const s = size / 12;
    const d = `M ${cx} ${cy + 8*s}
      C ${cx - 1*s} ${cy + 5*s}, ${cx - 12*s} ${cy - 1*s}, ${cx - 12*s} ${cy - 6*s}
      C ${cx - 12*s} ${cy - 12*s}, ${cx - 4*s} ${cy - 14*s}, ${cx} ${cy - 6*s}
      C ${cx + 4*s} ${cy - 14*s}, ${cx + 12*s} ${cy - 12*s}, ${cx + 12*s} ${cy - 6*s}
      C ${cx + 12*s} ${cy - 1*s}, ${cx + 1*s} ${cy + 5*s}, ${cx} ${cy + 8*s} Z`;
    svg.appendChild(el('path', { d, fill, stroke, 'stroke-width': sw }));
  }

  // ── Drawing ──
  function draw() {
    clear();
    const cx = 110, cy = 110;
    const screenR = 99;

    // Screen outline
    addCircle(cx, cy, screenR, COLORS.bg, COLORS.screen, 3);
    addCircle(cx, cy, screenR - 4, 'none', COLORS.screenIn, 1);

    // Breathing offset
    const breathSpeed = (currentFace === 'sleepy' || currentFace === 'rest') ? 0.04 : 0.08;
    const breathAmp = (currentFace === 'sleepy' || currentFace === 'rest') ? 0.5 : 1.8;
    const dy = Math.sin(tick * 0.05 * breathSpeed / 0.08) * breathAmp;

    // Eye positions
    const ey = 95 + dy;
    const lx = 75, rx = 145;

    if (isBlinking) {
      drawBlinkEyes(lx, rx, ey);
    } else {
      drawExpressionEyes(lx, rx, ey);
    }

    if (speaking) {
      drawSpeechWaveform(cx);
    } else {
      drawIdleMouth(cx, cy + 40 + dy / 2);
    }
  }

  function drawBlinkEyes(lx, rx, ey) {
    [lx, rx].forEach(x => {
      addLine(x - 14, ey, x + 14, ey, COLORS.glowOuter, 12);
      addLine(x - 14, ey, x + 14, ey, COLORS.glowMid, 8);
      addLine(x - 14, ey, x + 14, ey, COLORS.glowInner, 4);
    });
  }

  function drawExpressionEyes(lx, rx, ey) {
    const face = currentFace;

    if (face === 'happy') {
      [lx, rx].forEach(x => {
        addSmoothLine([x-14, ey+4, x, ey-8, x+14, ey+4], COLORS.glowOuter, 12);
        addSmoothLine([x-14, ey+4, x, ey-8, x+14, ey+4], COLORS.glowMid, 8);
        addSmoothLine([x-14, ey+4, x, ey-8, x+14, ey+4], COLORS.glowInner, 4);
      });
    } else if (face === 'sad') {
      const eySad = ey + 6;
      [lx, rx].forEach(x => {
        addSmoothLine([x-14, eySad-4, x, eySad+8, x+14, eySad-4], COLORS.glowOuter, 12);
        addSmoothLine([x-14, eySad-4, x, eySad+8, x+14, eySad-4], COLORS.glowMid, 8);
        addSmoothLine([x-14, eySad-4, x, eySad+8, x+14, eySad-4], COLORS.glowInner, 4);
      });
    } else if (face === 'angry') {
      addLine(lx-12, ey-8, lx+12, ey+8, COLORS.glowOuter, 14);
      addLine(lx-12, ey-8, lx+12, ey+8, COLORS.glowMid, 9);
      addLine(lx-12, ey-8, lx+12, ey+8, COLORS.glowInner, 5);
      addLine(rx+12, ey-8, rx-12, ey+8, COLORS.glowOuter, 14);
      addLine(rx+12, ey-8, rx-12, ey+8, COLORS.glowMid, 9);
      addLine(rx+12, ey-8, rx-12, ey+8, COLORS.glowInner, 5);
    } else if (face === 'sleepy') {
      const eySleep = ey + 8;
      [lx, rx].forEach(x => {
        addLine(x-14, eySleep, x+14, eySleep, COLORS.sleepyDim, 10);
        addLine(x-14, eySleep, x+14, eySleep, COLORS.sleepyMid, 6);
        addLine(x-14, eySleep, x+14, eySleep, COLORS.sleepyBright, 3);
      });
    } else if (face === 'excited' || face === 'surprised') {
      const pulse = Math.sin(tick * 0.15) * 2;
      const r = 14 + pulse;
      [lx, rx].forEach(x => {
        addCircle(x, ey, r, 'none', COLORS.glowOuter, 8);
        addCircle(x, ey, r, 'none', COLORS.glowMid, 5);
        addCircle(x, ey, r, 'none', COLORS.glowInner, 2.5);
        addLine(x-4, ey, x+4, ey, COLORS.glowInner, 2);
        addLine(x, ey-4, x, ey+4, COLORS.glowInner, 2);
      });
    } else if (face === 'love') {
      [lx, rx].forEach(x => {
        addHeart(x, ey, 12, COLORS.heartFill, COLORS.heartStroke, 2);
        addHeart(x, ey, 8, COLORS.heartStroke, COLORS.heartInner, 1);
      });
    } else if (face === 'confused') {
      // Left: vertical bar
      addLine(lx, ey-12, lx, ey+12, COLORS.glowOuter, 12);
      addLine(lx, ey-12, lx, ey+12, COLORS.glowMid, 8);
      addLine(lx, ey-12, lx, ey+12, COLORS.glowInner, 4);
      // Right: diagonal
      const ryConf = ey - 6;
      addLine(rx-10, ryConf+6, rx+10, ryConf-6, COLORS.glowOuter, 12);
      addLine(rx-10, ryConf+6, rx+10, ryConf-6, COLORS.glowMid, 8);
      addLine(rx-10, ryConf+6, rx+10, ryConf-6, COLORS.glowInner, 4);
    } else if (face === 'thinking') {
      const lxT = lx + 5, rxT = rx + 5;
      const eyT = ey - 6;
      [lxT, rxT].forEach(x => {
        addLine(x, eyT-10, x, eyT+10, COLORS.glowOuter, 12);
        addLine(x, eyT-10, x, eyT+10, COLORS.glowMid, 8);
        addLine(x, eyT-10, x, eyT+10, COLORS.glowInner, 4);
      });
      addArc(rxT + 20, eyT - 17, 6, 0, 270, COLORS.glowMid, 2);
      addCircle(rxT + 30, eyT - 28, 2, COLORS.glowInner);
    } else {
      // Default
      [lx, rx].forEach(x => {
        addLine(x, ey-12, x, ey+12, COLORS.glowOuter, 12);
        addLine(x, ey-12, x, ey+12, COLORS.glowMid, 8);
        addLine(x, ey-12, x, ey+12, COLORS.glowInner, 4);
      });
    }
  }

  function drawIdleMouth(cx, my) {
    const face = currentFace;
    if (face === 'happy') {
      addSmoothLine([cx-12, my-2, cx, my+4, cx+12, my-2], COLORS.glowMid, 3);
    } else if (face === 'sad') {
      addSmoothLine([cx-12, my+4, cx, my-2, cx+12, my+4], COLORS.glowMid, 3);
    } else if (face === 'angry') {
      addLine(cx-10, my, cx+10, my, COLORS.glowMid, 3);
    } else if (face === 'excited' || face === 'surprised') {
      addCircle(cx, my+2, 6, 'none', COLORS.glowMid, 3);
    } else if (face === 'sleepy') {
      addCircle(cx, my+2, 4, 'none', COLORS.sleepyMid, 2);
    } else {
      addSmoothLine([cx-10, my, cx, my+3, cx+10, my], COLORS.glowMid, 3);
    }
  }

  function drawSpeechWaveform(cx) {
    const wy = 150;
    const numBars = 9;
    const spacing = 11;
    const startX = cx - ((numBars - 1) * spacing) / 2;

    for (let i = 0; i < numBars; i++) {
      const offset = Math.sin(tick * 0.04 * 0.35 / 0.05 + i * 0.7) * 12;
      const distCenter = Math.abs(i - (numBars - 1) / 2);
      const multiplier = Math.max(0.3, 1.0 - distCenter * 0.18);
      const height = Math.max(4, (14 + offset) * multiplier);
      const x = startX + i * spacing;

      addLine(x, wy - height, x, wy + height, COLORS.mouthGlow, 7);
      addLine(x, wy - height, x, wy + height, COLORS.mouthColor, 3.5);
    }
  }

  return { init, setFace, setSpeaking };
})();


// ── Chat System ─────────────────────────────────────────────
function hideWelcome() {
  if (!welcomeVisible) return;
  const ws = document.getElementById('welcome-screen');
  if (ws) {
    ws.style.transition = 'opacity 0.3s ease';
    ws.style.opacity = '0';
    setTimeout(() => ws.remove(), 300);
  }
  welcomeVisible = false;
}

function addMessage(sender, text) {
  if (sender !== 'system' && sender !== 'error' && sender !== 'success') {
    hideWelcome();
  }
  const container = document.getElementById('messages-container');
  const timeStr = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

  if (sender === 'system' || sender === 'error' || sender === 'success') {
    const div = document.createElement('div');
    div.className = 'system-message';
    const typeClass = sender === 'error' ? 'error' : sender === 'success' ? 'success' : 'info';
    const prefix = sender === 'error' ? '[ERROR] ' : sender === 'success' ? '[OK] ' : '';
    div.innerHTML = `<div class="system-pill ${typeClass}">${prefix}${escapeHtml(text)}</div>`;
    container.appendChild(div);
  } else {
    const senderName = sender === 'user' ? 'You' : 'Sesame';
    const div = document.createElement('div');
    div.className = `message ${sender}`;
    div.innerHTML = `
      <div class="message-bubble">
        <div class="message-meta">${senderName} · ${timeStr}</div>
        <div class="message-text">${escapeHtml(text)}</div>
      </div>`;
    container.appendChild(div);
  }

  // Auto-scroll
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
  if (active) {
    if (container) {
      container.appendChild(el);
    }
    el.classList.add('active');
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
      addMessage('system', `AI source: ${result.source}`);
    }
    if (result.response) {
      addMessage('sesame', result.response);
    }
    if (result.face) {
      RobotFace.setFace(result.face);
      document.getElementById('metric-face').textContent = result.face;
    }
    if (result.command) {
      document.getElementById('metric-command').textContent = result.command;
    }
    if (result.error) {
      addMessage('error', result.error);
    }
  } catch (err) {
    setTyping(false);
    addMessage('error', 'Failed to communicate with backend: ' + err);
  }
}

async function sendCommand(cmd) {
  addMessage('system', `Executing: ${cmd}`);
  try {
    const result = await window.pywebview.api.send_command(cmd);
    if (result.error) {
      addMessage('error', `Command failed: ${result.error}`);
    } else {
      const confirmedCommand = result.command || cmd;
      addMessage('success', `${confirmedCommand} accepted by robot`);
      if (result.face) {
        RobotFace.setFace(result.face);
        document.getElementById('metric-face').textContent = result.face;
      }
      document.getElementById('metric-command').textContent = confirmedCommand;
    }
  } catch (err) {
    addMessage('error', 'Command error: ' + err);
  }
}

async function runDemo() {
  addMessage('system', 'Demo Mode started');
  try {
    await window.pywebview.api.run_demo();
    addMessage('success', 'Demo finished!');
  } catch (err) {
    addMessage('error', 'Demo error: ' + err);
  }
}

async function refreshStatus() {
  try {
    const status = await window.pywebview.api.get_status();
    applyStatus(status);
  } catch (err) {
    addMessage('error', 'Refresh failed: ' + err);
  }
}

async function toggleListening() {
  const micBtn = document.getElementById('mic-btn');

  // Clicking mic while already listening finishes recording immediately
  if (isListening) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.stop_listening) {
      await window.pywebview.api.stop_listening();
    }
    return;
  }

  isListening = true;
  micBtn.classList.add('listening');
  addMessage('system', 'Listening... (speak now, or click mic again when done)');

  try {
    const result = await window.pywebview.api.toggle_listening();
    if (result && result.text) {
      const input = document.getElementById('chat-input');
      input.value = result.text;
      input.focus();
      await new Promise((resolve) => requestAnimationFrame(resolve));
      await sendMessage({ preserveInput: false });
    } else {
      addMessage('system', (result && result.error) || 'No speech detected');
    }
  } catch (err) {
    addMessage('error', 'Voice error: ' + err);
  } finally {
    isListening = false;
    micBtn.classList.remove('listening');
  }
}

// Called from Python background wake-word listener when "Hey Sesame" triggers
function onWakeWordTranscript(text) {
  if (!text) return;
  const input = document.getElementById('chat-input');
  input.value = text;
  sendMessage({ preserveInput: false });
}

async function updateSetting(key, value) {
  try {
    const result = await window.pywebview.api.update_setting(key, value);
    if (result.message) {
      addMessage('system', result.message);
    }
    if (key === 'personality') {
      const chip = document.getElementById('personality-chip');
      if (chip) {
        chip.textContent = value === 'intelligent' ? 'Intelligent - focused' : 'Silly - playful';
      }
    }
  } catch (err) {
    addMessage('error', 'Settings error: ' + err);
  }
}

// ── Status Updates (called from Python via evaluate_js) ─────
function applyStatus(status) {
  if (!status) return;

  // Connection
  const connDot = document.getElementById('conn-dot');
  const connText = document.getElementById('conn-status-text');
  if (status.connected) {
    connDot.className = 'status-dot online';
    connText.className = 'status-text online';
    connText.textContent = 'Connected';
  } else {
    connDot.className = 'status-dot offline';
    connText.className = 'status-text offline';
    connText.textContent = 'Disconnected';
  }

  // Face & command
  if (status.face) {
    RobotFace.setFace(status.face);
    document.getElementById('metric-face').textContent = status.face;
  }
  if (status.command !== undefined) {
    const cmd = status.command || 'none';
    document.getElementById('metric-command').textContent = cmd;
    document.getElementById('robot-status-text').textContent = `Status: ${cmd.charAt(0).toUpperCase() + cmd.slice(1)}`;
  }
}

function applyAiStatus(label) {
  const dot = document.getElementById('ai-dot');
  const text = document.getElementById('ai-status-text');
  text.textContent = label;

  if (label.toLowerCase().includes('missing') || label.toLowerCase().includes('fallback')) {
    dot.className = 'status-dot checking';
    text.className = 'status-text checking';
  } else if (label.toLowerCase().includes('ready')) {
    dot.className = 'status-dot online';
    text.className = 'status-text online';
  } else {
    dot.className = 'status-dot checking';
    text.className = 'status-text checking';
  }
}

function applyIpAddress(ip) {
  document.getElementById('metric-ip').textContent = ip;
}

function setSpeakingState(val, face) {
  isSpeaking = val;
  RobotFace.setSpeaking(val);
  if (face) {
    RobotFace.setFace(face);
    document.getElementById('metric-face').textContent = face;
  }
}

// ── Keyboard shortcuts ──────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('chat-input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  document.querySelectorAll('.prompt-chip').forEach((button) => {
    button.addEventListener('click', () => {
      input.value = button.dataset.prompt || '';
      input.focus();
      sendMessage();
    });
  });

  // Initialize robot face
  RobotFace.init();

  // Wait for pywebview API and load initial state
  waitForApi().then(async () => {
    try {
      const state = await window.pywebview.api.get_initial_state();
      if (state.ip) applyIpAddress(state.ip);
      if (state.ai_status) applyAiStatus(state.ai_status);
      if (state.status) applyStatus(state.status);

      // Sync settings UI
      if (state.voice_enabled !== undefined) {
        document.getElementById('voice-toggle').checked = state.voice_enabled;
      }
      if (state.wake_word_mode !== undefined) {
        document.getElementById('wake-toggle').checked = state.wake_word_mode;
      }
      if (state.tts_engine) {
        const radio = document.querySelector(`input[name="tts"][value="${state.tts_engine}"]`);
        if (radio) radio.checked = true;
      }
      if (state.personality) {
        const radio = document.querySelector(`input[name="personality"][value="${state.personality}"]`);
        if (radio) radio.checked = true;
      }
    } catch (err) {
      console.error('Init state error:', err);
    }
  });
});

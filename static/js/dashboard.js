/* ── dashboard.js — Kick AI Bot Dashboard ── */
'use strict';

// ── Globals ────────────────────────────────
const socket = io();
let STATE = {
  connected: false,
  channel: null,
  chatroom_id: null,
  pipelineEnabled: true,
  bots: [],
  aiTokens: [],
  kickAccounts: [],
  emotes: [],
};
let chatAutoScroll = true;
let currentTab = 'chat';

// ── Helpers ────────────────────────────────
function esc(s) {
  return String(s ?? '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function ts(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString('tr-TR', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

function nowTime() {
  return new Date().toLocaleTimeString('tr-TR', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

function toast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  const icons = { success:'✅', error:'❌', info:'ℹ️' };
  t.innerHTML = `<span>${icons[type] || '•'}</span><span>${esc(msg)}</span>`;
  document.getElementById('toast-container').appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

async function api(method, path, body) {
  try {
    const opts = {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Username': localStorage.getItem('kick_user') || 'egeazakli'
      }
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  } catch (e) {
    toast(e.message, 'error');
    throw e;
  }
}

function botInitials(name) {
  return name ? name[0].toUpperCase() : '?';
}

// ── Tab Navigation ─────────────────────────
function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`tab-${tab}`)?.classList.add('active');
  document.getElementById(`nav-${tab}`)?.classList.add('active');
}

// ── SocketIO Events ────────────────────────
socket.on('connect', () => console.log('Socket connected'));
socket.on('disconnect', () => console.log('Socket disconnected'));

socket.on('init', data => {
  STATE.channel = data.channel;
  STATE.chatroom_id = data.chatroom_id;
  STATE.connected = data.connected;
  STATE.pipelineEnabled = data.pipeline_enabled ?? true;
  updateConnectionUI();
  updatePipelineToggle();
  const chInput = document.getElementById('channel-input') || document.getElementById('kick-setup-input');
  if (data.channel && chInput) chInput.value = data.channel;
});

socket.on('kick_status', data => {
  const { status, message } = data;
  STATE.connected = (status === 'connected');
  updateConnectionUI(status, message);
  appendSystemMsg(message, status);
});

socket.on('chat_message', msg => appendChatMessage(msg));

socket.on('pipeline_status', ev => appendPipelineEvent(ev));

// ── Connection UI ──────────────────────────
function updateConnectionUI(status, label) {
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const btn = document.getElementById('connect-btn');
  const discBtn = document.getElementById('disconnect-btn');

  const miniDot = document.getElementById('kick-mini-dot');
  const miniTxt = document.getElementById('kick-mini-channel');

  if (STATE.connected) {
    if (dot) dot.className = 'status-dot connected';
    if (txt) txt.textContent = STATE.channel ? `#${STATE.channel}` : 'Bağlandı';
    if (miniDot) {
      miniDot.style.background = '#53fc18';
      miniDot.style.boxShadow = '0 0 6px rgba(83,252,24,0.8)';
    }
    if (miniTxt) miniTxt.textContent = STATE.channel ? `@${STATE.channel}` : 'Bağlandı';
    if (btn) btn.style.display = 'none';
    if (discBtn) discBtn.style.display = '';
  } else if (status === 'connecting' || status === 'reconnecting') {
    if (dot) dot.className = 'status-dot connecting';
    if (txt) txt.textContent = status === 'reconnecting' ? 'Yeniden bağlanıyor…' : 'Bağlanıyor…';
    if (miniDot) {
      miniDot.style.background = '#ffd740';
      miniDot.style.boxShadow = '0 0 6px rgba(255,215,64,0.8)';
    }
    if (miniTxt) miniTxt.textContent = 'Bağlanıyor…';
    if (btn) btn.style.display = '';
    if (discBtn) discBtn.style.display = 'none';
  } else {
    if (dot) dot.className = 'status-dot';
    if (txt) txt.textContent = 'Bağlı değil';
    if (miniDot) {
      miniDot.style.background = '#555';
      miniDot.style.boxShadow = 'none';
    }
    if (miniTxt) miniTxt.textContent = 'Bağlı Değil';
    if (btn) btn.style.display = '';
    if (discBtn) discBtn.style.display = 'none';
  }
}

function updatePipelineToggle() {
  const btn = document.getElementById('pipeline-btn');
  if (!btn) return;
  if (STATE.pipelineEnabled) {
    btn.classList.add('active');
    btn.innerHTML = '⚡ Otomatik Yanıt: Aktif';
  } else {
    btn.classList.remove('active');
    btn.innerHTML = '⏸ Otomatik Yanıt: Durduruldu';
  }
}

// ── Channel Connect ─────────────────────────
async function connectChannel(channelName) {
  const inputEl = document.getElementById('channel-input') || document.getElementById('kick-setup-input');
  const ch = (channelName || (inputEl ? inputEl.value : '')).trim();
  if (!ch) { toast('Kanal adı veya Chatroom ID girin', 'error'); return; }
  const btn = document.getElementById('connect-btn') || document.getElementById('kick-setup-btn');
  if (btn) {
    btn.innerHTML = '<span class="spinner"></span> Bağlanıyor…';
    btn.disabled = true;
  }
  try {
    const r = await api('POST', '/api/channel/connect', { channel: ch });
    STATE.channel = ch;
    STATE.chatroom_id = r.chatroom_id;
    STATE.connected = true;
    updateConnectionUI();
    toast(`Kanal/Chatroom (${ch}) bağlandı!`, 'success');
    return r;
  } finally {
    if (btn) {
      btn.innerHTML = '⚡ Bağlan';
      btn.disabled = false;
    }
  }
}

async function disconnectChannel() {
  await api('POST', '/api/channel/disconnect');
  STATE.connected = false;
  STATE.channel = null;
  updateConnectionUI();
  toast('Bağlantı kesildi', 'info');
}

// ── Pipeline toggle ─────────────────────────
async function togglePipeline() {
  STATE.pipelineEnabled = !STATE.pipelineEnabled;
  await api('POST', '/api/pipeline/toggle', { enabled: STATE.pipelineEnabled });
  updatePipelineToggle();
  toast(STATE.pipelineEnabled ? 'Otomatik yanıt sistemi başlatıldı' : 'Otomatik yanıt sistemi durduruldu', 'info');
}

function formatChatContent(content) {
  const safe = esc(content);
  return safe.replace(/\[emote:(\d+):([a-zA-Z0-9_]+)\]/g, (match, id, name) => {
    return `<span class="kick-emote-tag" title="${match}"><img src="https://files.kick.com/emotes/${id}/fullsize" alt="${name}" onerror="this.style.display='none'" style="height:20px;width:20px;object-fit:contain;vertical-align:middle"> <span>${name}</span></span>`;
  });
}

// ── Chat messages ──────────────────────────
function appendChatMessage(msg) {
  const el = document.getElementById('chat-messages');
  if (!el) return;

  const type = msg.msg_type || msg.type || 'user';
  const cls = type === 'bot' ? 'bot-msg' : type === 'manual' ? 'manual-msg' : '';
  const avatarCls = type === 'bot' ? 'avatar-bot' : type === 'manual' ? 'avatar-manual' : 'avatar-user';
  const userCls = type === 'bot' ? 'user-color-bot' : type === 'manual' ? 'user-color-manual' : 'user-color-user';

  const div = document.createElement('div');
  div.className = `chat-msg ${cls}`;
  div.innerHTML = `
    <div class="chat-avatar ${avatarCls}">${botInitials(msg.username)}</div>
    <div class="chat-msg-body">
      <div class="chat-msg-meta">
        <span class="chat-msg-user ${userCls}">${esc(msg.username)}</span>
        ${type === 'bot' ? '<span class="badge badge-purple" style="font-size:0.65rem">AI BOT</span>' : ''}
        <span class="chat-msg-time">${nowTime()}</span>
      </div>
      <div class="chat-msg-content">${formatChatContent(msg.content)}</div>
    </div>
  `;
  el.appendChild(div);
  if (chatAutoScroll) el.scrollTop = el.scrollHeight;
}

function appendSystemMsg(msg, type) {
  const el = document.getElementById('chat-messages');
  if (!el) return;
  const colors = { connected:'var(--green)', error:'var(--red)', reconnecting:'var(--yellow)', disconnected:'var(--text3)' };
  const div = document.createElement('div');
  div.className = 'chat-msg system-msg';
  div.innerHTML = `
    <div class="chat-avatar avatar-system">⚙</div>
    <div class="chat-msg-body">
      <div class="chat-msg-meta">
        <span class="chat-msg-user" style="color:${colors[type]||'var(--text3)'}">Sistem</span>
        <span class="chat-msg-time">${nowTime()}</span>
      </div>
      <div class="chat-msg-content text-muted">${esc(msg)}</div>
    </div>
  `;
  el.appendChild(div);
  if (chatAutoScroll) el.scrollTop = el.scrollHeight;
}

function appendPipelineEvent(ev) {
  const el = document.getElementById('pipeline-events');
  if (!el) return;

  const colors = {
    generating: { cls: 'ev-generating', icon: '🤔', label: `${ev.bot || ''} → yanıt üretiyor` },
    sent:        { cls: 'ev-sent',       icon: '✅', label: `${ev.bot || ''} → gönderildi` },
    error:       { cls: 'ev-error',      icon: '⚠️', label: `${ev.bot || ''} → AI hatası` },
    send_error:  { cls: 'ev-send_error', icon: '❌', label: `${ev.bot || ''} → gönderim hatası` },
    skipped:     { cls: 'ev-skipped',   icon: '⏭',  label: 'atlandı' },
  };
  const c = colors[ev.status] || { cls: '', icon: '•', label: ev.status };

  const div = document.createElement('div');
  div.className = `pipeline-event ${c.cls}`;

  let body = '';
  if (ev.trigger) body += `<div class="text-dim text-xs">↩ "${esc(ev.trigger)}"</div>`;
  if (ev.message) body += `<div class="mt-4">${esc(ev.message)}</div>`;
  if (ev.error)   body += `<div class="mt-4 text-xs" style="color:var(--red)">${esc(ev.error)}</div>`;

  div.innerHTML = `
    <div class="ev-label">${c.icon} ${esc(c.label)}</div>
    ${body}
    <div class="text-xs text-dim mt-4">${nowTime()}</div>
  `;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
  // Keep max 60 events
  while (el.children.length > 60) el.removeChild(el.firstChild);
}

// ── Send chat message (manual) ──────────────
async function sendManualMessage() {
  const content = document.getElementById('manual-msg-input').value.trim();
  const sel = document.getElementById('manual-account-select');
  const accountId = sel ? sel.value : '';
  if (!content) return;

  let chatroom_id = STATE.chatroom_id;
  if (!chatroom_id) {
    const chInp = document.getElementById('channel-input') || document.getElementById('kick-setup-input');
    const ch = chInp ? chInp.value.trim() : '';
    if (ch) {
      toast('Kanala bağlanılıyor...', 'info');
      const conn = await connectChannel(ch);
      if (conn && conn.chatroom_id) {
        chatroom_id = conn.chatroom_id;
      }
    }
  }

  if (!chatroom_id) {
    toast('Önce kanala bağlanın veya kanal adı girin', 'error');
    return;
  }

  const targetId = (!accountId || accountId === 'auto') ? 0 : accountId;

  try {
    const res = await api('POST', `/api/kick-accounts/${targetId}/send`, { content, chatroom_id });
    if (res && res.success === false) {
      toast(res.error || 'Mesaj gönderilemedi', 'error');
      return;
    }
    document.getElementById('manual-msg-input').value = '';
    toast('Mesaj gönderildi 🚀', 'success');
  } catch (err) {
    toast(err.message || 'Mesaj gönderilemedi', 'error');
  }
}

// ── Kick Emotes ─────────────────────────────
async function loadEmotes() {
  try {
    const list = await api('GET', '/api/emotes');
    if (Array.isArray(list)) {
      STATE.emotes = list;
      renderEmotesUI();
    }
  } catch (err) {
    console.error('loadEmotes error:', err);
  }
}

function updateEmoteBotSelect() {
  const sel = document.getElementById('emote-bot-select');
  if (!sel) return;
  const currentVal = sel.value;
  let html = `
    <option value="random">🎲 Rastgele Aktif Bot</option>
    <option value="all">👥 Tüm Aktif Botlar</option>
  `;
  const activeBots = (STATE.bots || []).filter(b => b.enabled);
  activeBots.forEach(bot => {
    html += `<option value="${bot.id}">🤖 ${esc(bot.name)}</option>`;
  });
  sel.innerHTML = html;
  if (currentVal && Array.from(sel.options).some(o => o.value === currentVal)) {
    sel.value = currentVal;
  }
}

function renderEmotesUI() {
  const countBadge = document.getElementById('emotes-count-badge');
  if (countBadge) countBadge.textContent = (STATE.emotes || []).length;
  const modalCount = document.getElementById('modal-emotes-count');
  if (modalCount) modalCount.textContent = (STATE.emotes || []).length;

  // 1. Quick Bar
  const quickBar = document.getElementById('quick-emotes-bar');
  if (quickBar) {
    if (!STATE.emotes || !STATE.emotes.length) {
      quickBar.innerHTML = '<span class="text-xs text-muted">Kayıtlı Kick emojisi yok. "Emojileri Yönet"ten ekleyin.</span>';
    } else {
      quickBar.innerHTML = STATE.emotes.map(e => {
        const match = e.match(/\[emote:(\d+):([a-zA-Z0-9_]+)\]/);
        const id = match ? match[1] : '';
        const name = match ? match[2] : e;
        const imgTag = id ? `<img src="https://files.kick.com/emotes/${id}/fullsize" alt="${name}" onerror="this.style.display='none'" style="height:18px;width:18px;object-fit:contain;vertical-align:middle">` : '🎭';
        return `
          <div class="quick-emote-chip" onclick="insertEmoteToInput('${esc(e)}')" title="Tıkla: Manuel mesaja ekle (${esc(e)})">
            ${imgTag}
            <span>${esc(name)}</span>
          </div>
        `;
      }).join('');
    }
  }

  // 2. Modal List
  const modalList = document.getElementById('modal-emotes-list');
  if (modalList) {
    if (!STATE.emotes || !STATE.emotes.length) {
      modalList.innerHTML = '<div class="text-xs text-muted" style="padding:10px;text-align:center">Hiç emoji eklenmemiş.</div>';
    } else {
      modalList.innerHTML = STATE.emotes.map(e => {
        const match = e.match(/\[emote:(\d+):([a-zA-Z0-9_]+)\]/);
        const id = match ? match[1] : '';
        const name = match ? match[2] : e;
        const imgTag = id ? `<img src="https://files.kick.com/emotes/${id}/fullsize" alt="${name}" onerror="this.style.display='none'" style="height:20px;width:20px;object-fit:contain;vertical-align:middle">` : '🎭';
        return `
          <div class="emote-list-item">
            <div style="display:flex;align-items:center;gap:8px;overflow:hidden">
              ${imgTag}
              <span style="color:var(--green);font-weight:600">${esc(name)}</span>
              <span class="text-xs text-dim" style="text-overflow:ellipsis;overflow:hidden;white-space:nowrap">${esc(e)}</span>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <button class="btn btn-ghost btn-xs" onclick="insertEmoteToInput('${esc(e)}');closeEmotesModal()" title="Mesaj kutusuna ekle">➕</button>
              <button class="btn btn-ghost btn-xs" onclick="deleteEmote('${esc(e)}')" style="color:var(--red)" title="Sil">🗑️</button>
            </div>
          </div>
        `;
      }).join('');
    }
  }
}

function insertEmoteToInput(code) {
  const input = document.getElementById('manual-msg-input');
  if (!input) return;
  const cur = input.value.trim();
  input.value = cur ? `${cur} ${code}` : code;
  input.focus();
  toast(`Emoji eklendi: ${code}`, 'info');
}

async function sendRandomEmote() {
  const btn = document.getElementById('btn-send-random-emote');
  const botSelect = document.getElementById('emote-bot-select');
  const botChoice = botSelect ? botSelect.value : 'random';
  const chatroom_id = STATE.chatroom_id;

  if (!STATE.connected && !chatroom_id) {
    toast('Önce Kick kanalına bağlanmalısınız!', 'error');
    return;
  }

  if (!STATE.emotes || !STATE.emotes.length) {
    toast('Hiç kayıtlı Kick emojisi yok! Önce emoji ekleyin.', 'error');
    return;
  }

  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> <span>Gönderiliyor…</span>';
  }

  try {
    const res = await api('POST', '/api/emotes/send-random', {
      bot_id: botChoice,
      chatroom_id: chatroom_id
    });
    if (res && res.success) {
      const count = res.results ? res.results.filter(r => r.success).length : 1;
      toast(`🎲 ${count} bot kanala rastgele emoji gönderdi!`, 'success');
    }
  } catch (err) {
    console.error('Send random emote error:', err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
  }
}

async function triggerHypeAttack() {
  const btn = document.getElementById('btn-hype-raid');
  const chatroom_id = STATE.chatroom_id;

  if (!STATE.connected && !chatroom_id) {
    toast('Önce bir Kick kanalına bağlanmalısınız!', 'error');
    return;
  }

  const customText = prompt('Hype/Raid mesajı girin (Boş bırakırsanız rastgele emoji basar):', '🔥 W YAYIN GG');
  if (customText === null) return;

  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span> <span>Raid Başlatıldı…</span>';
  }

  try {
    const res = await api('POST', '/api/hype', {
      count: 50,
      content: customText.trim() || undefined,
      chatroom_id: chatroom_id
    });
    if (res && res.success) {
      toast('🔥 50 Hesapla Anlık Hype Raid Başlatıldı!', 'success');
    }
  } catch (err) {
    toast(`Hata: ${err.message}`, 'error');
  } finally {
    setTimeout(() => {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }, 2000);
  }
}

window.triggerHypeAttack = triggerHypeAttack;

async function addSingleEmote() {
  const input = document.getElementById('emote-single-input');
  if (!input) return;
  const val = input.value.trim();
  if (!val) {
    toast('Lütfen bir Kick emoji kodu girin! (Örn: [emote:1579033:emojiAstonished])', 'error');
    return;
  }
  try {
    const res = await api('POST', '/api/emotes', { emote: val });
    if (res && res.success) {
      STATE.emotes = res.emotes;
      renderEmotesUI();
      input.value = '';
      await syncCloudBackup();
      toast('Emoji başarıyla eklendi! 🎉', 'success');
    }
  } catch (err) {}
}

async function addBulkEmotes() {
  const textarea = document.getElementById('emote-bulk-input');
  if (!textarea) return;
  const lines = textarea.value.split('\n').map(l => l.trim()).filter(Boolean);
  if (!lines.length) {
    toast('Lütfen en az bir emoji satırı girin!', 'error');
    return;
  }
  try {
    const res = await api('POST', '/api/emotes', { emotes: lines });
    if (res && res.success) {
      STATE.emotes = res.emotes;
      renderEmotesUI();
      textarea.value = '';
      await syncCloudBackup();
      toast(`${lines.length} adet emoji eklendi! ⚡`, 'success');
    }
  } catch (err) {}
}

async function deleteEmote(emoteStr) {
  if (!confirm(`Bu emojiyi silmek istediğine emin misin?\n${emoteStr}`)) return;
  try {
    const res = await api('DELETE', '/api/emotes', { emote: emoteStr });
    if (res && res.success) {
      STATE.emotes = res.emotes;
      renderEmotesUI();
      await syncCloudBackup();
      toast('Emoji silindi.', 'info');
    }
  } catch (err) {}
}

function openEmotesModal() {
  const m = document.getElementById('modal-emotes');
  if (m) {
    m.classList.add('open');
    m.classList.add('active');
    renderEmotesUI();
  }
}

function closeEmotesModal() {
  const m = document.getElementById('modal-emotes');
  if (m) {
    m.classList.remove('open');
    m.classList.remove('active');
  }
}

window.openEmotesModal = openEmotesModal;
window.closeEmotesModal = closeEmotesModal;
window.sendRandomEmote = sendRandomEmote;
window.addSingleEmote = addSingleEmote;
window.addBulkEmotes = addBulkEmotes;
window.deleteEmote = deleteEmote;
window.insertEmoteToInput = insertEmoteToInput;

// ── Bots ────────────────────────────────────
async function loadBots() {
  STATE.bots = await api('GET', '/api/bots');
  renderBots();
  loadBotOptions();
}

function renderBots() {
  const grid = document.getElementById('bots-grid');
  if (!grid) return;

  if (!STATE.bots.length) {
    grid.innerHTML = '<p class="text-muted">Henüz bot yok.</p>';
    return;
  }

  grid.innerHTML = STATE.bots.map(bot => {
    const traits = [
      bot.personality, bot.style, bot.interests
    ].filter(Boolean).join(' • ');
    const pct = bot.daily_limit > 0 ? Math.round((bot.daily_count / bot.daily_limit) * 100) : 0;
    const cdPct = 0; // dynamic via JS
    const tokenLabel = STATE.aiTokens.find(t => t.id === bot.ai_token_id)?.name || 'Varsayılan';
    const kickLabel = STATE.kickAccounts.find(a => a.id === bot.kick_account_id)?.username || '—';

    return `
      <div class="bot-card ${bot.enabled ? '' : 'disabled'}" id="bot-card-${bot.id}">
        <div class="bot-card-header">
          <div class="bot-avatar">${botInitials(bot.name)}</div>
          <div style="flex:1;min-width:0">
            <div class="bot-name">${esc(bot.name)}</div>
            <div class="text-xs text-dim">ID #${bot.id} · Chance ${Math.round(bot.response_chance*100)}%</div>
          </div>
          <label class="toggle" title="${bot.enabled ? 'Durdur' : 'Başlat'}">
            <input type="checkbox" ${bot.enabled ? 'checked' : ''} onchange="toggleBot(${bot.id}, this.checked)">
            <div class="toggle-track"></div>
            <div class="toggle-thumb"></div>
          </label>
        </div>
        <div class="bot-card-body">
          <div class="bot-traits">${traits.split('•').map(t => t.trim()).filter(Boolean).map(t => `<span class="trait-tag">${esc(t)}</span>`).join('')}</div>

          <div class="bot-stat-row">
            <span class="bot-stat-label">Günlük mesaj</span>
            <span class="bot-stat-val">
              ${bot.daily_count} / ${bot.daily_limit}
              <button class="btn btn-ghost btn-xs" onclick="resetDailyCounters(${bot.id})" title="Bu botun sayacını sıfırla" style="margin-left:4px;padding:2px 6px">🔄</button>
            </span>
          </div>
          <div class="progress mb-8">
            <div class="progress-fill" style="width:${pct}%"></div>
          </div>

          <div class="bot-stat-row">
            <span class="bot-stat-label">Cooldown</span>
            <span class="bot-stat-val" id="cd-${bot.id}">${bot.cooldown_remaining > 0 ? bot.cooldown_remaining.toFixed(0)+'s' : '—'}</span>
          </div>
          <div class="cooldown-bar mb-8">
            <div class="cooldown-fill" id="cd-fill-${bot.id}" style="width:0%"></div>
          </div>

          <div class="bot-stat-row">
            <span class="bot-stat-label">AI Token</span>
            <span class="badge badge-purple text-xs">${esc(tokenLabel)}</span>
          </div>
          <div class="bot-stat-row mt-4">
            <span class="bot-stat-label">Kick Hesabı</span>
            <span class="badge badge-cyan text-xs">${esc(kickLabel)}</span>
          </div>

          <div class="divider"></div>
          <div class="bot-actions">
            <button class="btn btn-ghost btn-sm" onclick="openBotEditor(${bot.id})">✏️ Düzenle</button>
            <button class="btn btn-cyan btn-sm" onclick="openBotSendModal(${bot.id})">💬 Gönder</button>
            <button class="btn btn-danger btn-sm" onclick="deleteBot(${bot.id})">🗑</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
  updateEmoteBotSelect();
}

async function toggleBot(id, enabled) {
  await api('POST', `/api/bots/${id}/toggle`, { enabled });
  STATE.bots = STATE.bots.map(b => b.id === id ? { ...b, enabled: enabled ? 1 : 0 } : b);
  document.getElementById(`bot-card-${id}`)?.classList.toggle('disabled', !enabled);
  updateEmoteBotSelect();
  toast(`Bot ${enabled ? 'başlatıldı' : 'durduruldu'}`, 'info');
}

async function deleteBot(id) {
  if (!confirm('Bu botu silmek istediğine emin misin?')) return;
  await api('DELETE', `/api/bots/${id}`);
  await loadBots();
  await syncCloudBackup();
  toast('Bot silindi', 'info');
}

async function resetDailyCounters(botId = null) {
  const confirmMsg = botId
    ? 'Bu botun günlük mesaj sayacı sıfırlansın mı?'
    : 'Tüm botların günlük mesaj sayaçları sıfırlansın mı?';
  if (!confirm(confirmMsg)) return;
  await api('POST', '/api/bots/reset-daily', botId ? { bot_id: botId } : {});
  toast('Günlük mesaj sayacı sıfırlandı', 'success');
  await loadBots();
}

// Bot cooldown live update
setInterval(async () => {
  if (currentTab !== 'bots') return;
  try {
    const stats = await fetch('/api/stats').then(r => r.json());
    stats.forEach(s => {
      const cdEl = document.getElementById(`cd-${s.id}`);
      const cdFill = document.getElementById(`cd-fill-${s.id}`);
      if (cdEl) cdEl.textContent = s.cooldown_remaining > 0 ? s.cooldown_remaining.toFixed(0) + 's' : '—';
      if (cdFill) {
        const bot = STATE.bots.find(b => b.id === s.id);
        const maxDelay = bot?.max_delay || 60;
        const pct = s.cooldown_remaining > 0 ? Math.min((s.cooldown_remaining / maxDelay) * 100, 100) : 0;
        cdFill.style.width = pct + '%';
      }
    });
  } catch {}
}, 2000);

// ── Bot Editor Modal ────────────────────────
let _editBotId = null;

function openBotEditor(id) {
  _editBotId = id;
  const bot = id ? STATE.bots.find(b => b.id === id) : null;
  const m = document.getElementById('modal-bot');
  document.getElementById('modal-bot-title').textContent = bot ? `${bot.name} — Düzenle` : 'Yeni Bot';

  const fields = ['name','personality','style','interests','system_prompt'];
  fields.forEach(f => {
    const el = document.getElementById(`bot-edit-${f}`);
    if (el) el.value = bot?.[f] || '';
  });

  const numFields = ['response_chance','min_delay','max_delay','daily_limit'];
  numFields.forEach(f => {
    const el = document.getElementById(`bot-edit-${f}`);
    if (el) el.value = bot?.[f] ?? '';
  });

  // populate token selects
  const tokenSel = document.getElementById('bot-edit-ai_token_id');
  tokenSel.innerHTML = '<option value="">Varsayılan (ilk token)</option>' +
    STATE.aiTokens.map(t => `<option value="${t.id}" ${bot?.ai_token_id === t.id ? 'selected' : ''}>${esc(t.name)}</option>`).join('');

  const kickSel = document.getElementById('bot-edit-kick_account_id');
  kickSel.innerHTML = '<option value="">— Seç —</option>' +
    STATE.kickAccounts.map(a => `<option value="${a.id}" ${bot?.kick_account_id === a.id ? 'selected' : ''}>${esc(a.username || `Hesap #${a.id}`)}</option>`).join('');

  m.classList.add('open');
}

function closeBotModal() {
  document.getElementById('modal-bot').classList.remove('open');
  _editBotId = null;
}

async function saveBotEditor() {
  const data = {
    name: document.getElementById('bot-edit-name').value.trim(),
    personality: document.getElementById('bot-edit-personality').value.trim(),
    style: document.getElementById('bot-edit-style').value.trim(),
    interests: document.getElementById('bot-edit-interests').value.trim(),
    system_prompt: document.getElementById('bot-edit-system_prompt').value.trim(),
    response_chance: parseFloat(document.getElementById('bot-edit-response_chance').value) || 0.35,
    min_delay: parseInt(document.getElementById('bot-edit-min_delay').value) || 8,
    max_delay: parseInt(document.getElementById('bot-edit-max_delay').value) || 45,
    daily_limit: parseInt(document.getElementById('bot-edit-daily_limit').value) || 50,
    ai_token_id: document.getElementById('bot-edit-ai_token_id').value || null,
    kick_account_id: document.getElementById('bot-edit-kick_account_id').value || null,
    enabled: 1,
  };
  if (!data.name) { toast('İsim gerekli', 'error'); return; }

  if (_editBotId) {
    await api('PUT', `/api/bots/${_editBotId}`, data);
    toast('Bot güncellendi', 'success');
  } else {
    await api('POST', '/api/bots', data);
    toast('Bot eklendi', 'success');
  }
  closeBotModal();
  await loadBots();
  await syncCloudBackup();
}

// Bot manual send modal
let _sendBotId = null;

function openBotSendModal(id) {
  _sendBotId = id;
  const bot = STATE.bots.find(b => b.id === id);
  document.getElementById('bot-send-name').textContent = bot?.name || '';
  document.getElementById('bot-send-msg').value = '';
  document.getElementById('modal-bot-send').classList.add('open');
}

function closeBotSendModal() {
  document.getElementById('modal-bot-send').classList.remove('open');
}

async function sendBotMessage() {
  const content = document.getElementById('bot-send-msg').value.trim();
  if (!content) return;
  if (!STATE.chatroom_id) {
    const chInp = document.getElementById('channel-input') || document.getElementById('kick-setup-input');
    const ch = chInp ? chInp.value.trim() : '';
    if (ch) await connectChannel(ch);
  }
  if (!STATE.chatroom_id) { toast('Önce kanala bağlanın', 'error'); return; }
  try {
    const res = await api('POST', `/api/bots/${_sendBotId}/send`, { content, chatroom_id: STATE.chatroom_id });
    if (res && res.success === false) {
      toast(res.error || 'Bot mesajı gönderilemedi', 'error');
      return;
    }
    toast('Bot mesajı gönderildi 🤖', 'success');
    closeBotSendModal();
  } catch (err) {
    toast(err.message || 'Bot mesajı gönderilemedi', 'error');
  }
}

// ── AI Tokens ──────────────────────────────
async function loadAiTokens() {
  try {
    const list = await api('GET', '/api/tokens');
    if (Array.isArray(list)) {
      STATE.aiTokens = list;
      renderAiTokens();
    }
  } catch (err) {
    console.error('loadAiTokens error:', err);
  }
}

function renderAiTokens() {
  const list = document.getElementById('ai-tokens-list');
  if (!list) return;
  if (!STATE.aiTokens.length) {
    list.innerHTML = '<p class="text-muted text-sm">Henüz AI token eklenmemiş.</p>';
    return;
  }
  list.innerHTML = STATE.aiTokens.map(t => `
    <div class="token-card">
      <div class="token-card-header">
        <div>
          <div class="token-name">${esc(t.name)}</div>
          <div class="text-xs text-dim">${esc(t.model)} · ${esc(t.base_url)}</div>
        </div>
        <div class="flex gap-8">
          <button class="btn btn-ghost btn-sm" onclick="testAiToken(${t.id}, this)" title="Test Et">🧪 Test</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deleteAiToken(${t.id})" title="Sil">🗑</button>
        </div>
      </div>
      <div class="token-card-body">
        <div class="token-value">${esc(t.token_masked)}</div>
        <div class="text-xs text-dim">Eklenme: ${ts(t.created_at) || t.created_at}</div>
      </div>
    </div>
  `).join('');
}

async function addAiToken() {
  const name = document.getElementById('ai-name').value.trim();
  const token = document.getElementById('ai-token').value.trim();
  const base_url = document.getElementById('ai-base-url').value.trim() || 'https://api.openai.com/v1';
  const model = document.getElementById('ai-model').value.trim() || 'gpt-4o-mini';

  if (!name || !token) { toast('İsim ve token gerekli', 'error'); return; }

  await api('POST', '/api/tokens', { name, token, base_url, model });
  document.getElementById('ai-name').value = '';
  document.getElementById('ai-token').value = '';
  toast('AI token eklendi', 'success');
  await loadAiTokens();
  await syncCloudBackup();
}

async function deleteAiToken(id) {
  if (!confirm('Bu token silinsin mi?')) return;
  await api('DELETE', `/api/tokens/${id}`);
  await loadAiTokens();
  await syncCloudBackup();
  toast('Token silindi', 'info');
}

async function testAiToken(id, btn) {
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  try {
    const r = await api('POST', `/api/tokens/${id}/test`);
    toast(r.valid ? `✅ ${r.message}` : `❌ ${r.message}`, r.valid ? 'success' : 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🧪 Test';
  }
}

// ── Kick Accounts ──────────────────────────
async function loadKickAccounts() {
  try {
    const list = await api('GET', '/api/kick-accounts');
    if (Array.isArray(list)) {
      STATE.kickAccounts = list;
      renderKickAccounts();
      loadBotOptions();
    }
  } catch (err) {
    console.error('loadKickAccounts error:', err);
  }
}

function renderKickAccounts() {
  const list = document.getElementById('kick-accounts-list');
  if (list) {
    if (!STATE.kickAccounts.length) {
      list.innerHTML = '<p class="text-muted text-sm">Henüz Kick hesabı eklenmemiş.</p>';
    } else {
      list.innerHTML = STATE.kickAccounts.map(a => `
        <div class="kick-account-card">
          <div>
            <div class="fw-600">${esc(a.username || `Hesap #${a.id}`)}</div>
            <div class="mono text-xs text-dim">${esc(a.token_masked)}</div>
          </div>
          <div style="display:flex;gap:6px">
            <button class="btn btn-ghost btn-sm" onclick="testKickAccount(${a.id}, this)">🧪 Test</button>
            <button class="btn btn-danger btn-sm" onclick="deleteKickAccount(${a.id})">🗑 Sil</button>
          </div>
        </div>
      `).join('');
    }
  }

  // Update manual send selector
  const sel = document.getElementById('manual-account-select');
  if (sel) {
    const curVal = sel.value;
    sel.innerHTML = '<option value="auto">⚡ Otomatik (Aktif Hesap)</option>' +
      STATE.kickAccounts.slice(0, 100).map(a => `<option value="${a.id}">${esc(a.username || `Hesap #${a.id}`)}</option>`).join('');
    if (curVal) sel.value = curVal;
  }
}

async function testKickAccount(id, btn) {
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  try {
    const r = await api('POST', `/api/kick-accounts/${id}/test`);
    toast(r.valid ? `✅ ${r.message}` : `❌ ${r.message}`, r.valid ? 'success' : 'error');
  } catch (err) {
    toast(`❌ Hata: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🧪 Test';
  }
}

async function addKickAccount() {
  const username = document.getElementById('kick-username').value.trim();
  const token = document.getElementById('kick-token').value.trim();
  if (!token) { toast('Bearer token gerekli', 'error'); return; }
  await api('POST', '/api/kick-accounts', { username, token });
  document.getElementById('kick-username').value = '';
  document.getElementById('kick-token').value = '';
  toast('Kick hesabı eklendi', 'success');
  await loadKickAccounts();
  await loadBots();
  await syncCloudBackup();
}

async function bulkAddKickAccounts() {
  const text = document.getElementById('kick-bulk-tokens').value.trim();
  const testMsg = document.getElementById('kick-bulk-msg').value.trim() || '';
  if (!text) { toast('En az 1 token yazın', 'error'); return; }

  const tokens = text.split('\n').map(t => t.trim()).filter(Boolean);
  if (!tokens.length) { toast('Geçerli token bulunamadı', 'error'); return; }

  const btn = document.getElementById('btn-bulk-add');
  const resultsDiv = document.getElementById('kick-bulk-results');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Ekleniyor...';
  resultsDiv.style.display = 'flex';
  resultsDiv.innerHTML = '<div class="text-dim text-sm"><span class="spinner"></span> Kick API\'den kullanıcı adları çekiliyor ve kaydediliyor...</div>';

  try {
    const res = await api('POST', '/api/kick-accounts/bulk-add', {
      tokens,
      chatroom_id: STATE.chatroom_id || null,
      test_msg: testMsg,
    });

    resultsDiv.innerHTML = '';
    if (res.results && res.results.length) {
      const okItems = res.results.filter(r => r.saved && !r.error);
      const errItems = res.results.filter(r => r.error);

      if (okItems.length) {
        const okSec = document.createElement('div');
        okSec.style.cssText = 'margin-bottom:10px';
        okSec.innerHTML = `<div style="font-weight:700;color:var(--accent);margin-bottom:6px">✅ Başarıyla Eklendi (${okItems.length})</div>`;
        okItems.forEach(r => {
          okSec.innerHTML += `<div style="padding:8px 12px;background:rgba(var(--accent-rgb,0,230,118),0.08);border:1px solid var(--accent);border-radius:6px;font-size:0.83rem">
            👤 <strong>${esc(r.username)}</strong> — <span class="text-dim">${esc(r.token_preview)}</span></div>`;
        });
        resultsDiv.appendChild(okSec);
      }

      if (errItems.length) {
        const errSec = document.createElement('div');
        errSec.innerHTML = `<div style="font-weight:700;color:var(--red);margin-bottom:6px">⚠️ Sorunlu (${errItems.length})</div>`;
        errItems.forEach(r => {
          errSec.innerHTML += `<div style="padding:8px 12px;background:rgba(255,80,80,0.08);border:1px solid var(--red);border-radius:6px;font-size:0.83rem">
            ❌ <strong>${esc(r.username || r.token_preview)}</strong> — ${esc(r.error)}</div>`;
        });
        resultsDiv.appendChild(errSec);
      }

      toast(`${okItems.length} hesap eklendi${errItems.length ? ', ' + errItems.length + ' hatalı' : ''}`, okItems.length ? 'success' : 'error');
    }

    await loadKickAccounts();
    await loadBots();
    await syncCloudBackup();
  } catch(e) {
    resultsDiv.innerHTML = `<div class="text-xs" style="color:var(--red)">❌ Hata: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚡ Toplu Ekle';
  }
}

async function deleteKickAccount(id) {
  if (!confirm('Bu Kick hesabı silinsin mi?')) return;
  await api('DELETE', `/api/kick-accounts/${id}`);
  await loadKickAccounts();
  await syncCloudBackup();
  toast('Hesap silindi', 'info');
}

async function purgeDeadTokensUI() {
  const btn = document.getElementById('btn-purge-dead');
  if (!confirm('Kick API üzerinden tüm tokenler taranacak ve geçersiz/ölü olanlar temizlenecek. Onaylıyor musunuz?')) return;
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Taranıyor…';
  }
  try {
    const res = await api('POST', '/api/accounts/health-check', { count: 200 });
    toast(res.status || 'Tarama tamamlandı!', 'info');
    await loadKickAccounts();
    await loadBots();
    await syncCloudBackup();
  } catch (err) {
    toast(`Hata: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '🧹 Ölü Tokenleri Süpür';
    }
  }
}

function exportTokensList() {
  window.open('/api/kick-accounts/export', '_blank');
}

// ── Bot dropdowns helper ────────────────────
function loadBotOptions() {
  // Update bot editor selects (called during render)
}

// ── Logs ────────────────────────────────────
async function loadLogs() {
  const logs = await api('GET', '/api/logs?limit=200');
  renderLogs(logs);
}

function renderLogs(logs) {
  const el = document.getElementById('logs-body');
  if (!el) return;
  if (!logs.length) {
    el.innerHTML = '<div class="text-muted text-sm" style="padding:12px">Log yok.</div>';
    return;
  }
  el.innerHTML = logs.map(l => {
    const statusCls = l.status === 'sent' ? 'log-status-sent' : l.status === 'error' ? 'log-status-error' : 'log-status-skipped';
    return `
      <div class="log-row">
        <span class="log-type">${
          l.msg_type === 'bot' ? '<span class="badge badge-purple">BOT</span>' :
          l.msg_type === 'system' ? '<span class="badge badge-gray">SYS</span>' :
          '<span class="badge badge-cyan">USER</span>'
        }</span>
        <span class="text-sm">${esc(l.username || '—')}</span>
        <span class="text-sm ${l.msg_type === 'bot' ? 'glow-text' : 'text-muted'}">${esc(l.bot_name || '—')}</span>
        <span class="log-content">${esc((l.content || '').substring(0,120))}</span>
        <span class="log-status ${statusCls}">${esc(l.status || '—')}</span>
        <span class="log-time">${ts(l.timestamp) || l.timestamp}</span>
      </div>
    `;
  }).join('');
}

async function clearLogs() {
  if (!confirm('Tüm loglar silinsin mi?')) return;
  await api('POST', '/api/logs/clear');
  renderLogs([]);
  toast('Loglar temizlendi', 'info');
}

// ── Bearer Token Batch Test ─────────────────
async function runBatchTokenTest() {
  const text = document.getElementById('batch-tokens-input').value.trim();
  const testMsg = document.getElementById('batch-test-msg').value.trim() || '31';
  if (!text) { toast('En az 1 adet Kick Bearer Token girin', 'error'); return; }
  if (!STATE.chatroom_id) { toast('Önce yukarıdan bir kanala/chatroom id\'ye bağlanın', 'error'); return; }

  const tokens = text.split('\n').map(t => t.trim()).filter(Boolean);
  if (!tokens.length) { toast('Geçerli token bulunamadı', 'error'); return; }

  const btn = document.getElementById('btn-run-bearer-test');
  const resultsCard = document.getElementById('bearer-test-results-card');
  const okList = document.getElementById('bearer-ok-list');
  const failList = document.getElementById('bearer-fail-list');
  const summaryEl = document.getElementById('bearer-test-summary');
  const okSection = document.getElementById('bearer-ok-section');
  const failSection = document.getElementById('bearer-fail-section');
  const okCount = document.getElementById('bearer-ok-count');
  const failCount = document.getElementById('bearer-fail-count');

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Test Yapılıyor...';
  resultsCard.style.display = 'block';
  okList.innerHTML = '';
  failList.innerHTML = '';
  summaryEl.innerHTML = '<span class="text-dim text-sm"><span class="spinner"></span> Test ediliyor...</span>';
  okSection.style.display = 'none';
  failSection.style.display = 'none';

  let okArr = [], failArr = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    try {
      const res = await api('POST', '/api/kick-accounts/batch-test', {
        token,
        chatroom_id: STATE.chatroom_id,
        content: testMsg
      });

      if (res.success) {
        okArr.push(token);
        const div = document.createElement('div');
        div.style.cssText = 'padding:8px 12px;background:rgba(0,230,118,0.07);border:1px solid var(--accent);border-radius:6px;font-size:0.83rem;font-family:monospace';
        div.innerHTML = `✅ <strong>Token #${i+1}</strong> <span style="color:var(--text3)">${esc(token.substring(0,16))}...</span> <span style="color:var(--accent)">BAŞARILI ✓</span>`;
        okList.appendChild(div);
        okSection.style.display = 'block';
        okCount.textContent = okArr.length;
      } else {
        failArr.push(token);
        const div = document.createElement('div');
        div.style.cssText = 'padding:8px 12px;background:rgba(255,80,80,0.07);border:1px solid var(--red);border-radius:6px;font-size:0.83rem;font-family:monospace';
        div.innerHTML = `❌ <strong>Token #${i+1}</strong> <span style="color:var(--text3)">${esc(token.substring(0,16))}...</span> <span style="color:var(--red)">BAŞARISIZ</span>`;
        failList.appendChild(div);
        failSection.style.display = 'block';
        failCount.textContent = failArr.length;
      }
    } catch (e) {
      failArr.push(token);
      const div = document.createElement('div');
      div.style.cssText = 'padding:8px 12px;background:rgba(255,80,80,0.07);border:1px solid var(--red);border-radius:6px;font-size:0.83rem;font-family:monospace';
      div.innerHTML = `❌ <strong>Token #${i+1}</strong> <span style="color:var(--text3)">${esc(token.substring(0,16))}...</span> <span style="color:var(--red)">HATA: ${esc(e.message)}</span>`;
      failList.appendChild(div);
      failSection.style.display = 'block';
      failCount.textContent = failArr.length;
    }
  }

  // Summary bar
  summaryEl.innerHTML = `
    <div style="padding:8px 16px;background:rgba(0,230,118,0.12);border-radius:8px;border:1px solid var(--accent);font-size:0.85rem">
      ✅ <strong style="color:var(--accent)">${okArr.length}</strong> Başarılı
    </div>
    <div style="padding:8px 16px;background:rgba(255,80,80,0.12);border-radius:8px;border:1px solid var(--red);font-size:0.85rem">
      ❌ <strong style="color:var(--red)">${failArr.length}</strong> Başarısız
    </div>
    <div style="padding:8px 16px;background:var(--bg3);border-radius:8px;border:1px solid var(--border);font-size:0.85rem">
      📊 Toplam: <strong>${tokens.length}</strong>
    </div>
  `;

  btn.disabled = false;
  btn.innerHTML = '⚡ Toplu Testi Başlat (Chata "31" Gönder)';
  toast(`Test tamamlandı: ${okArr.length} başarılı / ${failArr.length} başarısız`, okArr.length > 0 ? 'success' : 'error');
}

// ═══════════════════════════════════════════════
// Kick Otomatik Hesap Oluşturucu
// ═══════════════════════════════════════════════

function toggleMailMode() {
  const isTemp = document.getElementById('ac-mode-temp')?.checked;
  const emailInp = document.getElementById('ac-email');
  const btnNewMail = document.getElementById('btn-ac-new-mail');
  const hint = document.getElementById('ac-email-hint');

  if (isTemp) {
    emailInp.placeholder = 'temp.tf Gmail adresi otomatik alınacak...';
    if (btnNewMail) btnNewMail.style.display = '';
    if (hint) hint.textContent = 'temp.tf Gmail ile gelen 6 haneli Kick onay kodu otomatik okunur.';
    if (!emailInp.value || !emailInp.value.includes('@')) {
      generateTempEmail();
    }
  } else {
    emailInp.placeholder = 'kendi_epostaniz@gmail.com';
    if (btnNewMail) btnNewMail.style.display = 'none';
    if (hint) hint.textContent = 'Kendi e-postanızı girin. Onay kodu gelince web panelindeki kutucuğa yazacaksınız.';
    emailInp.value = '';
    emailInp.focus();
  }
}

async function generateAccountCredentials() {
  try {
    const isTemp = document.getElementById('ac-mode-temp')?.checked ?? true;
    const res = await api('POST', '/api/account-creator/generate-data', { use_temp_mail: isTemp });
    if (res.username) document.getElementById('ac-username').value = res.username;
    if (res.password) document.getElementById('ac-password').value = res.password;
    if (res.birthdate) document.getElementById('ac-birthdate').value = res.birthdate;
    if (res.email && isTemp) document.getElementById('ac-email').value = res.email;
    toast('Hesap bilgileri hazırlandı', 'success');
  } catch (e) {
    console.error('generateAccountCredentials error:', e);
  }
}

function randomizeUsername() {
  const adjs = ['dark', 'hyper', 'cyber', 'neon', 'turbo', 'shadow', 'frost', 'vortex', 'kral', 'efsane', 'ates', 'bozkurt'];
  const nouns = ['rider', 'gamer', 'streamer', 'player', 'wolf', 'strike', 'titan', 'sniper', 'kartal', 'avci', 'aslan'];
  const num = Math.floor(Math.random() * 900) + 10;
  const user = `${adjs[Math.floor(Math.random() * adjs.length)]}_${nouns[Math.floor(Math.random() * nouns.length)]}_${num}`;
  const inp = document.getElementById('ac-username');
  if (inp) inp.value = user;
}

function randomizePassword() {
  const uppers = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const lowers = 'abcdefghijkmnopqrstuvwxyz';
  const digits = '23456789';
  const specials = '!@#$%^&*';
  const all = uppers + lowers + digits + specials;

  const chars = [
    uppers[Math.floor(Math.random() * uppers.length)],
    uppers[Math.floor(Math.random() * uppers.length)],
    lowers[Math.floor(Math.random() * lowers.length)],
    lowers[Math.floor(Math.random() * lowers.length)],
    digits[Math.floor(Math.random() * digits.length)],
    digits[Math.floor(Math.random() * digits.length)],
    specials[Math.floor(Math.random() * specials.length)],
    specials[Math.floor(Math.random() * specials.length)],
  ];

  while (chars.length < 14) {
    chars.push(all[Math.floor(Math.random() * all.length)]);
  }

  // Karıştır (Fisher-Yates)
  for (let i = chars.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }

  const pwd = chars.join('');
  const inp = document.getElementById('ac-password');
  if (inp) {
    inp.value = pwd;
    toast('Yeni güçlü şifre üretildi', 'info');
  }
}

async function generateTempEmail() {
  try {
    const btn = document.getElementById('btn-ac-new-mail');
    if (btn) btn.disabled = true;
    const res = await api('POST', '/api/account-creator/generate-data', { use_temp_mail: true });
    if (res.email) {
      document.getElementById('ac-email').value = res.email;
      toast(`Yeni temp.tf Gmail adresi alındı: ${res.email}`, 'success');
    }
  } catch (e) {
    toast('Geçici e-posta alınamadı: ' + e.message, 'error');
  } finally {
    const btn = document.getElementById('btn-ac-new-mail');
    if (btn) btn.disabled = false;
  }
}

function togglePasswordVisibility(id) {
  const inp = document.getElementById(id);
  if (!inp) return;
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

async function startAccountCreation() {
  const username = document.getElementById('ac-username')?.value.trim();
  const email = document.getElementById('ac-email')?.value.trim();
  const password = document.getElementById('ac-password')?.value.trim();
  const birthdate = document.getElementById('ac-birthdate')?.value.trim();
  const isTemp = document.getElementById('ac-mode-temp')?.checked ?? true;
  const visibleBrowser = document.getElementById('ac-visible-browser')?.checked ?? true;

  if (!username) {
    toast('Kullanıcı adı boş olamaz', 'error');
    return;
  }
  if (!password) {
    toast('Şifre boş olamaz', 'error');
    return;
  }
  if (!isTemp && !email) {
    toast('Lütfen geçerli bir e-posta adresi girin', 'error');
    return;
  }

  // UI durumunu güncelle
  document.getElementById('btn-ac-start').style.display = 'none';
  document.getElementById('btn-ac-stop').style.display = '';
  document.getElementById('ac-code-box').style.display = 'none';
  document.getElementById('ac-success-card').style.display = 'none';
  setAcStatus('starting', 'Başlatılıyor...');

  appendAcLog('info', 'Otomatik hesap açma süreci başlatılıyor...');

  try {
    const res = await api('POST', '/api/account-creator/start', {
      username,
      email,
      password,
      birthdate,
      use_temp_mail: isTemp,
      headless: !visibleBrowser,
    });

    if (res.error) {
      toast(res.error, 'error');
      resetAcButtons();
    } else {
      toast('Tarayıcı oturumu başlatıldı!', 'info');
    }
  } catch (e) {
    resetAcButtons();
  }
}

async function submitManualCode() {
  const code = document.getElementById('ac-manual-code')?.value.trim();
  if (!code || code.length < 4) {
    toast('Lütfen gelen doğrulama kodunu tam giriniz', 'error');
    return;
  }
  try {
    await api('POST', '/api/account-creator/submit-code', { code });
    toast('Doğrulama kodu tarayıcıya iletildi', 'success');
    appendAcLog('info', `Onay kodu forma aktarılıyor: ${code}`);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function stopAccountCreation() {
  try {
    await api('POST', '/api/account-creator/stop');
    toast('Hesap açma işlemi iptal edildi', 'info');
    resetAcButtons();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function resetAcButtons() {
  const startBtn = document.getElementById('btn-ac-start');
  const stopBtn = document.getElementById('btn-ac-stop');
  if (startBtn) startBtn.style.display = '';
  if (stopBtn) stopBtn.style.display = 'none';
}

function setAcStatus(status, label) {
  const badge = document.getElementById('ac-status-badge');
  if (!badge) return;

  const colorMap = {
    idle: 'badge-gray',
    starting: 'badge-yellow',
    navigating: 'badge-purple',
    filling_form: 'badge-cyan',
    waiting_captcha: 'badge-yellow',
    waiting_code: 'badge-yellow',
    submitting_code: 'badge-cyan',
    extracting_token: 'badge-purple',
    success: 'badge-green',
    error: 'badge-red',
    stopped: 'badge-gray',
  };

  badge.className = `badge ${colorMap[status] || 'badge-gray'} text-xs`;
  badge.textContent = label || status;
}

function appendAcLog(level, msg, timeStr) {
  const term = document.getElementById('ac-terminal');
  if (!term) return;

  const time = timeStr || nowTime();
  const colors = {
    info: '#38bdf8',
    success: '#4ade80',
    warning: '#facc15',
    error: '#f87171',
  };
  const color = colors[level] || '#94a3b8';

  const line = document.createElement('div');
  line.style.marginBottom = '4px';
  line.innerHTML = `<span style="color:#64748b">[${time}]</span> <span style="color:${color}">${esc(msg)}</span>`;
  term.appendChild(line);
  term.scrollTop = term.scrollHeight;
}

function clearAcTerminal() {
  const term = document.getElementById('ac-terminal');
  if (term) term.innerHTML = '<div style="color:var(--text3)">Terminal temizlendi.</div>';
}

function copyAcToken() {
  const tok = document.getElementById('ac-succ-token')?.value;
  if (tok) {
    navigator.clipboard.writeText(tok);
    toast('Bearer Token panoya kopyalandı!', 'success');
  }
}

// ── SocketIO Account Creator Events ─────────
socket.on('account_creator_log', data => {
  appendAcLog(data.level, data.message, data.time);
});

socket.on('account_creator_status', data => {
  const userEl = document.getElementById('ac-status-user');
  const emailEl = document.getElementById('ac-status-email');
  if (userEl && data.username) userEl.textContent = data.username;
  if (emailEl && data.email) emailEl.textContent = data.email;
  
  const labels = {
    idle: 'Hazır (Boşta)',
    starting: 'Başlatılıyor...',
    navigating: 'Kick.com Açılıyor...',
    filling_form: 'Form Dolduruluyor...',
    waiting_captcha: 'Cloudflare Bekleniyor...',
    waiting_code: 'Onay Kodu Bekleniyor...',
    submitting_code: 'Kod Giriliyor...',
    extracting_token: 'Token Aranıyor...',
    success: 'Başarılı!',
    error: 'Hata Oluştu',
    stopped: 'Durduruldu',
  };
  setAcStatus(data.status, labels[data.status] || data.status);

  if (['success', 'error', 'stopped'].includes(data.status)) {
    resetAcButtons();
  }
});

socket.on('account_creator_code_required', data => {
  const codeBox = document.getElementById('ac-code-box');
  if (codeBox) {
    codeBox.style.display = '';
    const inp = document.getElementById('ac-manual-code');
    if (inp) {
      inp.value = '';
      inp.focus();
    }
  }
  toast(`E-postanıza (${data.email}) gelen 6 haneli kodu giriniz!`, 'warning');
});

socket.on('account_creator_success', data => {
  resetAcButtons();
  const codeBox = document.getElementById('ac-code-box');
  if (codeBox) codeBox.style.display = 'none';

  const card = document.getElementById('ac-success-card');
  if (card) {
    card.style.display = '';
    document.getElementById('ac-succ-user').textContent = data.username;
    document.getElementById('ac-succ-pass').textContent = data.password;
    document.getElementById('ac-succ-email').textContent = data.email;
    document.getElementById('ac-succ-token').value = data.token;
  }
  toast(`Hesap başarıyla açıldı: ${data.username}`, 'success');
  loadKickAccounts();
});

// Switch tab helper update for new tab
window.switchTab = function(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

  const pane = document.getElementById(`tab-${tabName}`);
  const nav = document.getElementById(`nav-${tabName}`);
  if (pane) pane.classList.add('active');
  if (nav) nav.classList.add('active');

  // Refresh data when switching to relevant tabs
  if (tabName === 'tokens') { loadAiTokens(); loadKickAccounts(); }
  if (tabName === 'bots') { loadBots(); }
  if (tabName === 'logs') { loadLogs(); }
  if (tabName === 'hesapolustur') {
    const userInp = document.getElementById('ac-username');
    if (userInp && !userInp.value) {
      generateAccountCredentials();
    }
  }
};

// ── Cloud Sync & Auto-Persistence ───────────
async function syncCloudBackup() {
  try {
    const backup = await api('GET', '/api/sync/backup');
    if (backup && (backup.ai_tokens?.length || backup.kick_accounts?.length || backup.bots?.length)) {
      localStorage.setItem('taxer_persistent_backup', JSON.stringify(backup));
    }
  } catch (e) {
    console.warn('Backup sync failed:', e);
  }
}

async function checkAndRestoreBackup() {
  try {
    const status = await api('GET', '/api/sync/status');
    const localBackupRaw = localStorage.getItem('taxer_persistent_backup');
    
    // Eğer sunucu yeni açıldıysa veya yeniden başlatıldıysa ve tokenlar boşsa:
    if (status && status.ai_tokens === 0 && status.kick_accounts === 0 && localBackupRaw) {
      const localBackup = JSON.parse(localBackupRaw);
      if (localBackup && (localBackup.ai_tokens?.length || localBackup.kick_accounts?.length || localBackup.bots?.length)) {
        await api('POST', '/api/sync/restore', localBackup);
        toast('Kayıtlı token ve botlarınız otomatik geri yüklendi! ✅', 'success');
      }
    }
  } catch (err) {
    console.warn('Auto restore check failed:', err);
  }
}

async function exportBackupJson() {
  try {
    const data = await api('GET', '/api/sync/backup');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `taxerai_backup_${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast('Yedek JSON dosyası indirildi! 📥', 'success');
  } catch (err) {
    toast('Yedek indirilemedi: ' + err.message, 'error');
  }
}

function triggerImportJson() {
  const inp = document.getElementById('backup-file-input');
  if (inp) inp.click();
}

async function handleImportJson(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async (ev) => {
    try {
      const data = JSON.parse(ev.target.result);
      await api('POST', '/api/sync/restore', data);
      await syncCloudBackup();
      await Promise.all([loadAiTokens(), loadKickAccounts(), loadBots(), loadEmotes()]);
      toast('Yedek başarıyla geri yüklendi! ✅', 'success');
    } catch (err) {
      toast('Geçersiz yedek dosyası: ' + err.message, 'error');
    } finally {
      e.target.value = '';
    }
  };
  reader.readAsText(file);
}

// ── Page Init ───────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  try {
    // 1. Sunucuda token yoksa tarayıcıdaki yedekten anında geri yükle
    await checkAndRestoreBackup();

    // 2. Verileri paralel yükle
    await Promise.all([
      loadAiTokens(),
      loadKickAccounts(),
      loadBots(),
      loadEmotes(),
    ]);

    // 3. Güncel hali tarayıcıya yedekle
    await syncCloudBackup();

    // 4. Kanal ve bağlantı durumunu kontrol et
    try {
      const chStatus = await api('GET', '/api/channel/status');
      if (chStatus) {
        if (chStatus.channel) {
          STATE.channel = chStatus.channel;
          const chInput = document.getElementById('channel-input') || document.getElementById('kick-setup-input');
          if (chInput) chInput.value = chStatus.channel;
        }
        if (chStatus.chatroom_id) STATE.chatroom_id = chStatus.chatroom_id;
        STATE.connected = Boolean(chStatus.connected);
        updateConnectionUI();
      }
    } catch {}
  } catch (e) {
    console.error('Init load error:', e);
  }

  // Check if opened directly via /hesapolustur route
  if (window.location.pathname.includes('/hesapolustur')) {
    switchTab('hesapolustur');
  }

  // Enter key sends manual message
  const msgInput = document.getElementById('manual-msg-input');
  if (msgInput) {
    msgInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendManualMessage();
    });
  }

  // Enter key on channel input connects
  const chInput = document.getElementById('channel-input');
  if (chInput) {
    chInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') connectChannel();
    });
  }

  // Enter key on ac-manual-code submits code
  const codeInp = document.getElementById('ac-manual-code');
  if (codeInp) {
    codeInp.addEventListener('keydown', e => {
      if (e.key === 'Enter') submitManualCode();
    });
  }
});


// ── Follow Bot ──────────────────────────────
async function startFollowBot() {
  const channel = (document.getElementById('follow-channel-input')?.value || '').trim();
  const count = parseInt(document.getElementById('follow-count-input')?.value || '100', 10);
  const delay = parseFloat(document.getElementById('follow-delay-input')?.value || '0.2');

  if (!channel) {
    toast('Lütfen hedef kanal kullanıcı adını girin!', 'error');
    return;
  }
  if (!count || count <= 0) {
    toast('Geçerli bir takipçi sayısı girin!', 'error');
    return;
  }

  try {
    const res = await api('POST', '/api/follow/start', { channel, count, delay });
    if (res.success) {
      const btnStart = document.getElementById('btn-follow-start');
      const btnStop = document.getElementById('btn-follow-stop');
      const badge = document.getElementById('follow-status-badge');
      if (btnStart) btnStart.style.display = 'none';
      if (btnStop) btnStop.style.display = 'block';
      if (badge) {
        badge.textContent = 'Çalışıyor';
        badge.className = 'badge badge-green text-xs';
      }
      toast(res.message, 'success');
    }
  } catch (err) {
    console.error(err);
  }
}

async function stopFollowBot() {
  try {
    const res = await api('POST', '/api/follow/stop');
    if (res.success) {
      const btnStart = document.getElementById('btn-follow-start');
      const btnStop = document.getElementById('btn-follow-stop');
      const badge = document.getElementById('follow-status-badge');
      if (btnStart) btnStart.style.display = 'block';
      if (btnStop) btnStop.style.display = 'none';
      if (badge) {
        badge.textContent = 'Durduruldu';
        badge.className = 'badge badge-gray text-xs';
      }
      toast('Durdurma isteği gönderildi', 'info');
    }
  } catch (err) {
    console.error(err);
  }
}

function clearFollowTerminal() {
  const term = document.getElementById('follow-terminal');
  if (term) {
    term.innerHTML = '<div style="color:var(--text3)">Takipçi botu terminal hazır...</div>';
  }
}

function addFollowLog(msg, isSuccess = true) {
  const terminal = document.getElementById('follow-terminal');
  if (!terminal) return;
  const time = new Date().toLocaleTimeString('tr-TR');
  const color = isSuccess ? '#53fc18' : '#ef4444';
  const logLine = document.createElement('div');
  logLine.innerHTML = `<span style="color:#666">[${time}]</span> <span style="color:${color}">${esc(msg)}</span>`;
  terminal.appendChild(logLine);
  terminal.scrollTop = terminal.scrollHeight;
}

// SocketIO Follow event listener
if (typeof socket !== 'undefined') {
  socket.on('follow_progress', function(data) {
    if (!data) return;
    
    if (document.getElementById('follow-stat-total')) {
      document.getElementById('follow-stat-total').textContent = data.total || 0;
      document.getElementById('follow-stat-sent').textContent = data.sent || 0;
      document.getElementById('follow-stat-success').textContent = data.success || 0;
      document.getElementById('follow-stat-failed').textContent = data.failed || 0;

      const pct = (data.total > 0) ? Math.round((data.sent / data.total) * 100) : 0;
      document.getElementById('follow-progress-percent').textContent = pct + '%';
      document.getElementById('follow-progress-bar').style.width = pct + '%';
    }

    if (data.message) {
      addFollowLog(data.message, data.is_success !== false);
    }

    if (!data.running) {
      const btnStart = document.getElementById('btn-follow-start');
      const btnStop = document.getElementById('btn-follow-stop');
      const badge = document.getElementById('follow-status-badge');
      if (btnStart) btnStart.style.display = 'block';
      if (btnStop) btnStop.style.display = 'none';
      if (badge) {
        badge.textContent = 'Bitti / Hazır';
        badge.className = 'badge badge-gray text-xs';
      }
    }
  });
}






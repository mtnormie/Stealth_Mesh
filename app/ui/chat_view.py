"""Modern consumer-style Messenger UI (Ukrainian & English) without admin/routing clutter."""

from __future__ import annotations

CHAT_VIEW_HTML: str = """<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="StealthMesh">
<meta name="theme-color" content="#0f172a">
<link rel="manifest" href="/manifest.json">
<link rel="apple-touch-icon" href="/icon.svg">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<title>Stealth Mesh</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;margin:0;background:#0b141a;color:#e9edef;font:15px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;overflow:hidden}
.app{display:grid;grid-template-columns:340px 1fr;height:100dvh;max-width:1440px;margin:0 auto;background:#111b21;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}
@media(max-width:780px){
  .app{grid-template-columns:1fr}
  .app.chat-open .sidebar{display:none}
  .app:not(.chat-open) .chat-pane{display:none}
}
/* Sidebar */
.sidebar{display:flex;flex-direction:column;border-right:1px solid #222e35;background:#111b21;height:100%;min-height:0}
.side-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#202c33;gap:8px}
.user-pill{display:flex;align-items:center;gap:10px;cursor:pointer;padding:4px 8px;border-radius:10px;transition:background .15s}
.user-pill:hover{background:#2a3942}
.avatar{width:40px;height:40px;border-radius:50%;background:linear-gradient(135deg,#00a884,#027eb5);display:flex;align-items:center;justify-content:center;font-weight:700;color:#fff;font-size:1rem;flex-shrink:0;user-select:none}
.avatar.sm{width:34px;height:34px;font-size:.88rem}
.side-actions{display:flex;gap:6px;align-items:center}
.icon-btn{background:#2a3942;border:0;color:#d1d7db;padding:8px 11px;border-radius:10px;cursor:pointer;font:600 .83rem inherit;transition:background .15s}
.icon-btn:hover{background:#374854;color:#fff}
.icon-btn.primary{background:#00a884;color:#fff}
.icon-btn.primary:hover{background:#06cf9c}
.search-box{padding:10px 14px;border-bottom:1px solid #222e35;display:flex;gap:8px}
.search-box input{width:100%;background:#202c33;border:1px solid transparent;color:#e9edef;padding:9px 14px;border-radius:10px;font:inherit;outline:none}
.search-box input:focus{border-color:#00a884}
.chat-list{flex:1;overflow-y:auto;divide-y:1px solid #222e35}
.chat-item{display:flex;align-items:center;gap:12px;padding:12px 16px;cursor:pointer;border-bottom:1px solid #1c272e;transition:background .12s}
.chat-item:hover{background:#202c33}
.chat-item.active{background:#2a3942}
.chat-item-meta{flex:1;min-width:0}
.chat-item-title{font-weight:600;color:#e9edef;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-item-sub{font-size:.82rem;color:#8696a0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
/* Main Chat Pane */
.chat-pane{display:flex;flex-direction:column;height:100%;min-height:0;background:#0b141a;position:relative}
.chat-header{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:#202c33;border-bottom:1px solid #222e35;min-height:62px;gap:10px}
.chat-header-left{display:flex;align-items:center;gap:12px;min-width:0}
.back-btn{display:none;background:transparent;border:0;color:#e9edef;font-size:1.3rem;cursor:pointer;padding:4px 8px}
@media(max-width:780px){.back-btn{display:inline-block}}
.chat-title{font-weight:600;font-size:1.02rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-sub{font-size:.78rem;color:#00a884;display:flex;align-items:center;gap:4px}
.messages-wrap{flex:1;overflow-y:auto;padding:18px 20px;display:flex;flex-direction:column;gap:8px;background:radial-gradient(circle at 20% 20%,#111f28 0%,#0b141a 100%)}
.e2e-notice{align-self:center;background:#182229;color:#ffd279;border:1px solid #2a3942;border-radius:10px;padding:7px 14px;font-size:.8rem;text-align:center;max-width:480px;margin:4px 0 12px}
.msg-row{display:flex;gap:8px;max-width:78%;align-items:flex-end}
.msg-row.mine{align-self:flex-end;flex-direction:row-reverse}
.msg-row.theirs{align-self:flex-start}
.bubble{padding:8px 12px;border-radius:14px;position:relative;word-wrap:break-word;overflow-wrap:anywhere;box-shadow:0 1px 2px rgba(0,0,0,.25)}
.msg-row.mine .bubble{background:#005c4b;color:#e9edef;border-bottom-right-radius:4px}
.msg-row.theirs .bubble{background:#202c33;color:#e9edef;border-bottom-left-radius:4px}
.sender-label{font-size:.76rem;font-weight:700;color:#38bdf8;margin-bottom:2px}
.msg-text{font-size:.95rem;line-height:1.38;white-space:pre-wrap}
.msg-time{font-size:.7rem;color:rgba(233,237,239,.65);text-align:right;margin-top:3px;display:flex;align-items:center;justify-content:flex-end;gap:4px}
.empty-state{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#8696a0;text-align:center;padding:24px}
.empty-state h2{color:#e9edef;margin:12px 0 6px;font-size:1.25rem}
/* Composer */
.composer{display:flex;align-items:center;gap:10px;padding:10px 16px;background:#202c33;border-top:1px solid #222e35}
.composer input{flex:1;background:#2a3942;border:0;color:#e9edef;padding:12px 16px;border-radius:24px;font:inherit;outline:none}
.send-btn{width:44px;height:44px;border-radius:50%;background:#00a884;border:0;color:#fff;font-size:1.1rem;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:transform .1s,background .15s}
.send-btn:hover{background:#06cf9c}
.send-btn:active{transform:scale(.94)}
/* Modals */
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.65);display:none;align-items:center;justify-content:center;padding:16px;z-index:50}
.modal-backdrop.open{display:flex}
.modal{background:#202c33;border:1px solid #2f3f49;border-radius:16px;padding:20px;width:100%;max-width:400px;box-shadow:0 16px 40px rgba(0,0,0,.5)}
.modal h3{margin:0 0 12px;color:#e9edef;font-size:1.12rem}
.modal input{width:100%;background:#111b21;border:1px solid #374854;color:#e9edef;padding:11px 13px;border-radius:10px;font:inherit;margin:8px 0 14px;outline:none}
.modal input:focus{border-color:#00a884}
.modal-actions{display:flex;justify-content:flex-end;gap:8px}
#qr-img{width:200px;height:200px;background:#fff;padding:8px;border-radius:12px;display:block;margin:12px auto}
.code-pill{background:#111b21;border:1px solid #2f3f49;padding:8px 10px;border-radius:8px;font-family:monospace;font-size:.82rem;word-break:break-all;color:#7de2c3;margin:8px 0}
</style>
</head>
<body>
<div class="app" id="app-root">
  <!-- Left Sidebar: Chat List -->
  <aside class="sidebar">
    <div class="side-header">
      <div class="user-pill" id="btn-profile" title="Profile">
        <div class="avatar sm" id="my-avatar">У</div>
        <div>
          <div style="font-weight:600;font-size:.92rem" id="my-name-label">Учасник</div>
          <div style="font-size:.74rem;color:#00a884" data-i18n="online_status">В мережі</div>
        </div>
      </div>
      <div class="side-actions">
        <button class="icon-btn primary" id="btn-new-group" type="button" data-i18n="new_chat">+ Чат</button>
        <button class="icon-btn" id="btn-join-group" type="button" data-i18n="join_btn">Вхід</button>
        <button class="icon-btn" id="btn-lang" type="button">EN</button>
      </div>
    </div>

    <div class="search-box">
      <input id="chat-filter" type="search" data-i18n-placeholder="search_placeholder" placeholder="Пошук чатів...">
    </div>

    <div class="chat-list" id="chat-list"></div>
  </aside>

  <!-- Right Main Chat Window -->
  <section class="chat-pane">
    <div id="no-chat-selected" class="empty-state">
      <div class="avatar" style="width:68px;height:68px;font-size:1.7rem">💬</div>
      <h2 data-i18n="welcome_title">Stealth Mesh Месенджер</h2>
      <p style="max-width:340px" data-i18n="welcome_sub">Виберіть чат зі списку ліворуч або створіть нову захищену групу для спілкування.</p>
      <div style="display:flex;gap:10px;margin-top:12px">
        <button class="icon-btn primary" id="btn-empty-new" type="button" data-i18n="create_group_btn">Створити групу</button>
        <button class="icon-btn" id="btn-empty-join" type="button" data-i18n="join_code_btn">Ввести код запрошення</button>
      </div>
    </div>

    <div id="active-chat-view" style="display:none;flex-direction:column;height:100%;min-height:0">
      <header class="chat-header">
        <div class="chat-header-left">
          <button class="back-btn" id="btn-back" type="button" aria-label="Back">←</button>
          <div class="avatar sm" id="active-chat-avatar">#</div>
          <div style="min-width:0">
            <div class="chat-title" id="active-chat-title">Група</div>
            <div class="chat-sub"><span>🔒</span> <span data-i18n="e2e_badge">Захищено наскрізним шифруванням</span></div>
          </div>
        </div>
        <button class="icon-btn" id="btn-invite-qr" type="button" data-i18n="invite_btn">Запросити</button>
      </header>

      <div class="messages-wrap" id="messages"></div>

      <form class="composer" id="send-form">
        <input name="body" id="msg-input" autocomplete="off" maxlength="4000" data-i18n-placeholder="msg_placeholder" placeholder="Написати повідомлення..." required>
        <button class="send-btn" type="submit" aria-label="Send">➤</button>
      </form>
    </div>
  </section>
</div>

<!-- Modal: Create Group -->
<div class="modal-backdrop" id="modal-create">
  <form class="modal" id="form-create">
    <h3 data-i18n="modal_create_title">Нова група</h3>
    <input name="name" id="input-group-name" maxlength="80" data-i18n-placeholder="group_name_placeholder" placeholder="Назва групи" required>
    <div class="modal-actions">
      <button class="icon-btn" type="button" data-close="modal-create" data-i18n="cancel">Скасувати</button>
      <button class="icon-btn primary" type="submit" data-i18n="create">Створити</button>
    </div>
  </form>
</div>

<!-- Modal: Join Group -->
<div class="modal-backdrop" id="modal-join">
  <form class="modal" id="form-join">
    <h3 data-i18n="modal_join_title">Приєднатися до групи</h3>
    <input name="token" id="input-join-token" data-i18n-placeholder="invite_code_placeholder" placeholder="Одноразовий код запрошення" required>
    <div class="modal-actions">
      <button class="icon-btn" type="button" data-close="modal-join" data-i18n="cancel">Скасувати</button>
      <button class="icon-btn primary" type="submit" data-i18n="join">Приєднатися</button>
    </div>
  </form>
</div>

<!-- Modal: Invite QR -->
<div class="modal-backdrop" id="modal-invite">
  <div class="modal">
    <h3 data-i18n="modal_invite_title">Запрошення у групу</h3>
    <p style="font-size:.86rem;color:#8696a0;margin:0" data-i18n="modal_invite_hint">Відскануйте QR-код камерою телефона або перешліть одноразовий код співрозмовнику:</p>
    <img id="qr-img" alt="QR">
    <div class="code-pill" id="invite-token-text"></div>
    <div class="modal-actions">
      <button class="icon-btn primary" type="button" data-close="modal-invite" data-i18n="done">Готово</button>
    </div>
  </div>
</div>

<!-- Modal: Profile Name -->
<div class="modal-backdrop" id="modal-profile">
  <form class="modal" id="form-profile">
    <h3 data-i18n="modal_profile_title">Ваше ім’я у чаті</h3>
    <input id="input-sender-name" maxlength="80" required>
    <div class="modal-actions">
      <button class="icon-btn" type="button" data-close="modal-profile" data-i18n="cancel">Скасувати</button>
      <button class="icon-btn primary" type="submit" data-i18n="save">Зберегти</button>
    </div>
  </form>
</div>

<script>
const I18N = {
  uk: {
    online_status: "В мережі",
    new_chat: "+ Чат",
    join_btn: "Вхід",
    search_placeholder: "Пошук чатів...",
    welcome_title: "Stealth Mesh Месенджер",
    welcome_sub: "Виберіть чат зі списку ліворуч або створіть нову захищену групу для спілкування.",
    create_group_btn: "Створити групу",
    join_code_btn: "Ввести код запрошення",
    e2e_badge: "Захищено наскрізним шифруванням",
    invite_btn: "Запросити",
    msg_placeholder: "Написати повідомлення...",
    modal_create_title: "Нова група",
    group_name_placeholder: "Назва групи",
    modal_join_title: "Приєднатися до групи",
    invite_code_placeholder: "Одноразовий код запрошення",
    modal_invite_title: "Запрошення у групу",
    modal_invite_hint: "Відскануйте QR-код камерою телефона або перешліть одноразовий код співрозмовнику:",
    modal_profile_title: "Ваше ім’я у чаті",
    cancel: "Скасувати",
    create: "Створити",
    join: "Приєднатися",
    done: "Готово",
    save: "Зберегти",
    e2e_banner: "🔒 Повідомлення у цьому чаті захищені наскрізним шифруванням AES-256-GCM.",
    chat_sub_encrypted: "Захищений груповий чат",
    no_chats_yet: "Ще немає чатів. Натисніть «+ Чат», щоб почати.",
    default_user: "Учасник",
    errors: {
      "group not found": "Групу не знайдено.",
      "invitation is invalid or has already been used": "Запрошення недійсне або вже використане.",
      "group name must contain 1 to 80 characters": "Назва групи має містити від 1 до 80 символів.",
      "sender must contain 1 to 80 characters": "Ім’я має містити від 1 до 80 символів.",
      "message must contain 1 to 4000 characters": "Повідомлення має містити від 1 до 4000 символів."
    }
  },
  en: {
    online_status: "Online",
    new_chat: "+ Chat",
    join_btn: "Join",
    search_placeholder: "Search chats...",
    welcome_title: "Stealth Mesh Messenger",
    welcome_sub: "Select a chat from the sidebar or create a new end-to-end encrypted group.",
    create_group_btn: "Create Group",
    join_code_btn: "Enter Invitation Code",
    e2e_badge: "End-to-end encrypted",
    invite_btn: "Invite",
    msg_placeholder: "Write a message...",
    modal_create_title: "New Group",
    group_name_placeholder: "Group name",
    modal_join_title: "Join Group",
    invite_code_placeholder: "One-time invitation code",
    modal_invite_title: "Group Invitation",
    modal_invite_hint: "Scan this QR code with a phone camera or share the one-time invitation code:",
    modal_profile_title: "Your Display Name",
    cancel: "Cancel",
    create: "Create",
    join: "Join",
    done: "Done",
    save: "Save",
    e2e_banner: "🔒 Messages in this chat are protected with end-to-end AES-256-GCM encryption.",
    chat_sub_encrypted: "Encrypted group chat",
    no_chats_yet: "No chats yet. Tap '+ Chat' to start.",
    default_user: "Member",
    errors: {
      "group not found": "Group not found.",
      "invitation is invalid or has already been used": "Invitation is invalid or has already been used.",
      "group name must contain 1 to 80 characters": "Group name must contain 1 to 80 characters.",
      "sender must contain 1 to 80 characters": "Name must contain 1 to 80 characters.",
      "message must contain 1 to 4000 characters": "Message must contain 1 to 4000 characters."
    }
  }
};

let lang = localStorage.getItem('stealth-mesh-language') || 'uk';
if (!I18N[lang]) lang = 'uk';
let senderName = localStorage.getItem('stealth-mesh-sender') || I18N[lang].default_user;
let allGroups = [];
let activeGroupId = '';

function t(key) {
  return (I18N[lang] && I18N[lang][key]) || I18N.uk[key] || key;
}

function initials(name) {
  const s = (name || '?').trim();
  return s ? s.slice(0, 2).toUpperCase() : '?';
}

function updateProfileUI() {
  document.getElementById('my-name-label').textContent = senderName;
  document.getElementById('my-avatar').textContent = initials(senderName);
}

function applyLanguage() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.getElementById('btn-lang').textContent = lang === 'uk' ? 'EN' : 'УКР';
  if (senderName === I18N.uk.default_user || senderName === I18N.en.default_user) {
    senderName = I18N[lang].default_user;
  }
  updateProfileUI();
  renderChatList();
  if (activeGroupId) refreshMessages();
}

let groupTokens = {};
try { groupTokens = JSON.parse(localStorage.getItem('stealth-mesh-tokens') || '{}') || {}; } catch (e) { groupTokens = {}; }
function saveGroupToken(gid, tok) {
  if (gid && tok) {
    groupTokens[gid] = tok;
    localStorage.setItem('stealth-mesh-tokens', JSON.stringify(groupTokens));
  }
}

const api = async (path, data) => {
  const headers = {};
  if (data) headers['Content-Type'] = 'application/json';
  const gid = (data && data.group_id) || activeGroupId || '';
  if (gid && groupTokens[gid]) headers['X-Group-Token'] = groupTokens[gid];
  const entries = Object.entries(groupTokens);
  if (entries.length > 0) headers['X-Group-Tokens'] = entries.map(([k, v]) => k + ':' + v).join(',');
  const r = await fetch(path, data ? {
    method: 'POST',
    headers,
    body: JSON.stringify(data)
  } : { headers });
  const j = await r.json();
  if (!r.ok) throw Error(j.error || 'Request error');
  return j;
};

function showError(e) {
  const dict = I18N[lang].errors || {};
  alert(dict[e.message] || e.message);
}

function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}
document.querySelectorAll('[data-close]').forEach(btn => {
  btn.onclick = () => closeModal(btn.dataset.close);
});

document.getElementById('btn-lang').onclick = () => {
  lang = lang === 'uk' ? 'en' : 'uk';
  localStorage.setItem('stealth-mesh-language', lang);
  applyLanguage();
};

document.getElementById('btn-new-group').onclick = () => openModal('modal-create');
document.getElementById('btn-empty-new').onclick = () => openModal('modal-create');
document.getElementById('btn-join-group').onclick = () => openModal('modal-join');
document.getElementById('btn-empty-join').onclick = () => openModal('modal-join');
document.getElementById('btn-profile').onclick = () => {
  document.getElementById('input-sender-name').value = senderName;
  openModal('modal-profile');
};
document.getElementById('btn-back').onclick = () => {
  document.getElementById('app-root').classList.remove('chat-open');
};

document.getElementById('form-profile').onsubmit = e => {
  e.preventDefault();
  const val = document.getElementById('input-sender-name').value.trim();
  if (val) {
    senderName = val;
    localStorage.setItem('stealth-mesh-sender', senderName);
    updateProfileUI();
    closeModal('modal-profile');
    if (activeGroupId) refreshMessages();
  }
};

function renderChatList() {
  const box = document.getElementById('chat-list');
  const filter = (document.getElementById('chat-filter').value || '').trim().toLowerCase();
  box.replaceChildren();
  const visible = allGroups.filter(g => g.name.toLowerCase().includes(filter));
  if (visible.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = 'padding:24px 16px;text-align:center;color:#8696a0;font-size:.88rem';
    empty.textContent = t('no_chats_yet');
    box.append(empty);
    return;
  }
  for (const g of visible) {
    const row = document.createElement('div');
    row.className = 'chat-item' + (g.group_id === activeGroupId ? ' active' : '');
    const av = document.createElement('div');
    av.className = 'avatar';
    av.textContent = initials(g.name);
    const meta = document.createElement('div');
    meta.className = 'chat-item-meta';
    const title = document.createElement('div');
    title.className = 'chat-item-title';
    title.textContent = g.name;
    const sub = document.createElement('div');
    sub.className = 'chat-item-sub';
    sub.textContent = t('chat_sub_encrypted');
    meta.append(title, sub);
    row.append(av, meta);
    row.onclick = () => selectChat(g.group_id);
    box.append(row);
  }
}

document.getElementById('chat-filter').oninput = renderChatList;

async function selectChat(groupId) {
  activeGroupId = groupId;
  const g = allGroups.find(x => x.group_id === groupId);
  if (!g) {
    document.getElementById('no-chat-selected').style.display = 'flex';
    document.getElementById('active-chat-view').style.display = 'none';
    document.getElementById('app-root').classList.remove('chat-open');
    renderChatList();
    return;
  }
  document.getElementById('no-chat-selected').style.display = 'none';
  document.getElementById('active-chat-view').style.display = 'flex';
  document.getElementById('app-root').classList.add('chat-open');
  document.getElementById('active-chat-title').textContent = g.name;
  document.getElementById('active-chat-avatar').textContent = initials(g.name);
  renderChatList();
  await refreshMessages();
}

async function refreshGroups(selectId) {
  allGroups = await api('/api/groups');
  const target = selectId || activeGroupId || (allGroups[0] && allGroups[0].group_id) || '';
  renderChatList();
  if (target) await selectChat(target);
}

async function refreshMessages() {
  if (!activeGroupId) return;
  const list = await api('/api/messages?group_id=' + encodeURIComponent(activeGroupId));
  const box = document.getElementById('messages');
  box.replaceChildren();
  const notice = document.createElement('div');
  notice.className = 'e2e-notice';
  notice.textContent = t('e2e_banner');
  box.append(notice);

  for (const m of list) {
    const isMine = (m.sender || '').trim().toLowerCase() === senderName.trim().toLowerCase();
    const row = document.createElement('div');
    row.className = 'msg-row ' + (isMine ? 'mine' : 'theirs');

    if (!isMine) {
      const av = document.createElement('div');
      av.className = 'avatar sm';
      av.textContent = initials(m.sender);
      row.append(av);
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (!isMine) {
      const sLabel = document.createElement('div');
      sLabel.className = 'sender-label';
      sLabel.textContent = m.sender;
      bubble.append(sLabel);
    }

    const txt = document.createElement('div');
    txt.className = 'msg-text';
    txt.textContent = m.body;

    const time = document.createElement('div');
    time.className = 'msg-time';
    const hhmm = (m.created_at || '').slice(11, 16) || '';
    time.textContent = hhmm + (isMine ? ' ✓✓' : '');

    bubble.append(txt, time);
    row.append(bubble);
    box.append(row);
  }
  box.scrollTop = box.scrollHeight;
}

document.getElementById('form-create').onsubmit = async e => {
  e.preventDefault();
  try {
    const input = document.getElementById('input-group-name');
    const g = await api('/api/groups', { name: input.value });
    saveGroupToken(g.group_id, g.member_token);
    input.value = '';
    closeModal('modal-create');
    await refreshGroups(g.group_id);
  } catch (err) {
    showError(err);
  }
};

document.getElementById('form-join').onsubmit = async e => {
  e.preventDefault();
  try {
    const input = document.getElementById('input-join-token');
    const g = await api('/api/join', { token: input.value.trim() });
    saveGroupToken(g.group_id, g.member_token);
    input.value = '';
    closeModal('modal-join');
    await refreshGroups(g.group_id);
  } catch (err) {
    showError(err);
  }
};

document.getElementById('btn-invite-qr').onclick = async () => {
  try {
    if (!activeGroupId) return;
    const v = await api('/api/invitations', { group_id: activeGroupId });
    document.getElementById('qr-img').src = '/qr?data=' + encodeURIComponent(v.url);
    document.getElementById('invite-token-text').textContent = v.token;
    openModal('modal-invite');
  } catch (err) {
    showError(err);
  }
};

document.getElementById('send-form').onsubmit = async e => {
  e.preventDefault();
  try {
    if (!activeGroupId) return;
    const input = document.getElementById('msg-input');
    const text = input.value;
    input.value = '';
    await api('/api/messages', {
      group_id: activeGroupId,
      sender: senderName,
      body: text
    });
    await refreshMessages();
  } catch (err) {
    showError(err);
  }
};

applyLanguage();
const hashParams = new URLSearchParams(location.hash.replace(/^#/, ''));
const queryParams = new URLSearchParams(location.search);
const joinToken = hashParams.get('join') || queryParams.get('join');
if (joinToken) {
  document.getElementById('input-join-token').value = joinToken;
  history.replaceState({}, '', location.pathname);
  openModal('modal-join');
}
refreshGroups().catch(showError);
setInterval(() => { if (activeGroupId) refreshMessages().catch(() => {}); }, 3000);
</script>
</body>
</html>"""

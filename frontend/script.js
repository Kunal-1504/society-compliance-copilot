const API_BASE = "http://127.0.0.1:8000";
const STORAGE_KEY = "societyCopilot.conversations.v1";
const ACTIVE_KEY = "societyCopilot.activeId.v1";

const sidebar = document.getElementById("sidebar");
const sidebarScrim = document.getElementById("sidebarScrim");
const menuToggle = document.getElementById("menuToggle");
const newChatBtn = document.getElementById("newChatBtn");
const historyListEl = document.getElementById("historyList");
const messagesEl = document.getElementById("messages");
const emptyState = document.getElementById("emptyState");
const composerForm = document.getElementById("composerForm");
const queryInput = document.getElementById("queryInput");
const sendBtn = document.getElementById("sendBtn");
const apiStatusEl = document.getElementById("apiStatus");
const suggestionGrid = document.getElementById("suggestionGrid");
const calendarToggle = document.getElementById("calendarToggle");
const calendarPanel = document.getElementById("calendarPanel");
const calendarGrid = document.getElementById("calendarGrid");
const chatScroll = document.getElementById("chatScroll");

let conversations = loadConversations();
let activeId = localStorage.getItem(ACTIVE_KEY);
let isSending = false;

if (!activeId || !conversations[activeId]) {
  activeId = createConversation();
}

function loadConversations() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function saveConversations() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

function setActive(id) {
  activeId = id;
  localStorage.setItem(ACTIVE_KEY, id);
}

function createConversation() {
  const id = `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  conversations[id] = { id, title: null, messages: [] };
  saveConversations();
  return id;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function detectLanguage(text) {
  const devanagari = /[\u0900-\u097F]/.test(text);
  // Improved romanized marathi keyword detection with more keywords
  const romanizedKeywords = /\b(aai|aapla|aaplya|aapli|tumhi|mi|ka|karu|sathi|samjha|mhatla|mazi|mahiti|gheu|kela|ahe|nahi|sang|mhanje|tasa|ghya|khup|samor|krya|kyun|kaay|tar|pan|la|te|cha|che|chi|nav|naveen|barobar|viruddh|samarthan|virodh|vichar|sambhav|aani|mahiti|karnyacha|kaaran|madhe|hota|lagte|sarkar|report|submit|karavi|annual|return|role|officer|secretary|chairman|treasurer|adhyaksha|sachiv|koshadhyaksha)\b/i;
  
  // Count matches to ensure it's definitely romanized marathi
  const matches = (text.match(romanizedKeywords) || []).length;
  
  if (devanagari) return { label: "मराठी", code: "mr" };
  if (matches >= 2) return { label: "Romanized Marathi", code: "r-mr" };
  return { label: "English", code: "en" };
}

function buildPrompt(query, conv) {
  const lang = detectLanguage(query);
  const langInstruction =
    lang.code === "mr"
      ? "Answer in Marathi."
      : lang.code === "r-mr"
      ? "Answer in Romanized Marathi."
      : "Answer in English.";

  const contextMessages = conv.messages.slice(-6).filter(Boolean);
  const contextBlock = contextMessages.length
    ? `Previous conversation context:\n${contextMessages.map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`).join("\n")}\n\n`
    : "";

  return `${contextBlock}${langInstruction} Use simple, clear language and keep the answer focused on housing society compliance. The user asks: ${query}`;
}

function renderHistory() {
  const ids = Object.keys(conversations).sort((a, b) => Number(b.split("_")[1]) - Number(a.split("_")[1]));

  if (ids.length === 0) {
    historyListEl.innerHTML = '<p class="history-empty">Your chats will appear here.</p>';
    return;
  }

  historyListEl.innerHTML = "";
  ids.forEach((id) => {
    const conv = conversations[id];
    const item = document.createElement("button");
    item.type = "button";
    item.className = "history-item" + (id === activeId ? " active" : "");
    item.innerHTML = `
      <span class="history-item-title">${escapeHtml(conv.title || "New chat")}</span>
      <span class="history-delete" title="Delete">✕</span>`;
    item.addEventListener("click", (e) => {
      if (e.target.closest(".history-delete")) return;
      setActive(id);
      renderHistory();
      renderMessages();
      closeMobileSidebar();
    });
    item.querySelector(".history-delete").addEventListener("click", (e) => {
      e.stopPropagation();
      deleteConversation(id);
    });
    historyListEl.appendChild(item);
  });
}

function deleteConversation(id) {
  delete conversations[id];
  saveConversations();
  if (id === activeId) {
    const remaining = Object.keys(conversations);
    setActive(remaining.length ? remaining[0] : createConversation());
  }
  renderHistory();
  renderMessages();
}

function renderMessages() {
  const conv = conversations[activeId];
  messagesEl.innerHTML = "";

  if (!conv || conv.messages.length === 0) {
    emptyState.style.display = "";
    return;
  }

  emptyState.style.display = "none";
  conv.messages.forEach((message) => messagesEl.appendChild(renderMessage(message)));
  scrollToBottom();
}

function renderMessage(message) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${message.role}${message.error ? " error" : ""}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = message.role === "user" ? "मी" : "सह";

  const body = document.createElement("div");
  body.className = "msg-body";

  const roleLabel = document.createElement("div");
  roleLabel.className = "msg-role";
  roleLabel.textContent = message.role === "user" ? "You" : "Society Copilot";

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  const badge = document.createElement("div");
  badge.className = "language-pill";
  badge.textContent = message.language || "";

  const text = document.createElement("div");
  text.innerHTML = escapeHtml(message.content).replace(/\n/g, "<br>");

  bubble.appendChild(badge);
  bubble.appendChild(text);

  body.appendChild(roleLabel);
  body.appendChild(bubble);

  if (message.role === "assistant" && Array.isArray(message.sources) && message.sources.length > 0) {
    body.appendChild(renderSources(message.sources));
  }

  wrap.appendChild(avatar);
  wrap.appendChild(body);
  return wrap;
}

function renderSources(sources) {
  const box = document.createElement("div");
  box.className = "sources";
  const heading = document.createElement("div");
  heading.className = "source-chip";
  heading.textContent = "Sources";
  box.appendChild(heading);

  sources.forEach((source) => {
    const url = source.url || source.source_page;
    
    if (url) {
      // Create clickable link
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.className = "source-chip source-link";
      const title = source.title || source.filename || source.name || "Document";
      const category = source.category ? ` • ${source.category}` : "";
      link.textContent = `${title}${category}`;
      box.appendChild(link);
    } else {
      // Fallback to non-clickable chip if no URL
      const chip = document.createElement("span");
      chip.className = "source-chip";
      const title = source.title || source.filename || source.name || "Document";
      const category = source.category ? ` • ${source.category}` : "";
      chip.textContent = `${title}${category}`;
      box.appendChild(chip);
    }
  });
  return box;
}

function showTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg assistant";
  wrap.id = "typingIndicator";
  wrap.innerHTML = `
    <div class="msg-avatar">सह</div>
    <div class="msg-body">
      <div class="msg-role">Society Copilot</div>
      <div class="msg-bubble"><span class="typing-dots"><span></span><span></span><span></span></span></div>
    </div>`;
  messagesEl.appendChild(wrap);
  scrollToBottom();
}

function hideTyping() {
  document.getElementById("typingIndicator")?.remove();
}

function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function setSending(state) {
  isSending = state;
  sendBtn.disabled = state || queryInput.value.trim().length === 0;
  queryInput.disabled = state;
}

function autoResize() {
  queryInput.style.height = "auto";
  queryInput.style.height = Math.min(queryInput.scrollHeight, 160) + "px";
}

function setApiStatus(ok) {
  apiStatusEl.classList.remove("ok", "down");
  apiStatusEl.classList.add(ok ? "ok" : "down");
  apiStatusEl.querySelector(".status-text").textContent = ok ? "online" : "offline";
}

function renderCalendar() {
  const items = [
    { month: "This month", title: "AGM notice reminder", detail: "Check the notice timeline and quorum rules." },
    { month: "Next month", title: "Annual return filing", detail: "Prepare updated member records and resolutions." },
    { month: "Next quarter", title: "Election paperwork", detail: "Review nomination and polling requirements." },
  ];

  calendarGrid.innerHTML = "";
  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "calendar-card";
    card.innerHTML = `<strong>${item.title}</strong><span>${item.month}</span><div>${item.detail}</div>`;
    calendarGrid.appendChild(card);
  });
}

async function sendMessage(text) {
  const trimmed = text.trim();
  if (!trimmed || isSending) return;

  const conv = conversations[activeId];
  if (!conv.title) {
    conv.title = trimmed.slice(0, 40) + (trimmed.length > 40 ? "…" : "");
  }

  const lang = detectLanguage(trimmed);
  conv.messages.push({ role: "user", content: trimmed, language: `${lang.label}` });
  saveConversations();
  renderHistory();
  renderMessages();

  queryInput.value = "";
  autoResize();
  setSending(true);
  showTyping();

  try {
    const prompt = buildPrompt(trimmed, conv);
    const response = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: prompt, top_k: 5 }),
    });

    if (!response.ok) throw new Error(`Server responded ${response.status}`);

    const data = await response.json();
    hideTyping();

    conv.messages.push({
      role: "assistant",
      content: data.answer || "No answer received.",
      sources: Array.isArray(data.sources) ? data.sources : [],
      language: `${lang.label}`,
    });
    saveConversations();
    renderMessages();
    setApiStatus(true);
  } catch (err) {
    hideTyping();
    conv.messages.push({
      role: "assistant",
      content: "The service is temporarily unavailable. Please try again in a moment.",
      error: true,
      language: `${lang.label}`,
    });
    saveConversations();
    renderMessages();
    setApiStatus(false);
    console.error(err);
  } finally {
    setSending(false);
  }
}

queryInput.addEventListener("input", () => {
  autoResize();
  sendBtn.disabled = isSending || queryInput.value.trim().length === 0;
});

queryInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composerForm.requestSubmit();
  }
});

composerForm.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(queryInput.value);
});

suggestionGrid.addEventListener("click", (e) => {
  const chip = e.target.closest(".suggestion-chip");
  if (!chip) return;
  sendMessage(chip.dataset.q);
});

newChatBtn.addEventListener("click", () => {
  setActive(createConversation());
  renderHistory();
  renderMessages();
  closeMobileSidebar();
  queryInput.focus();
});

menuToggle.addEventListener("click", () => {
  sidebar.classList.toggle("open");
  sidebarScrim.classList.toggle("show");
});
sidebarScrim.addEventListener("click", closeMobileSidebar);
function closeMobileSidebar() {
  sidebar.classList.remove("open");
  sidebarScrim.classList.remove("show");
}

calendarToggle.addEventListener("click", () => {
  calendarPanel.classList.toggle("open");
  calendarPanel.toggleAttribute("hidden", !calendarPanel.classList.contains("open"));
});

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    setApiStatus(res.ok && data.status === "healthy");
  } catch {
    setApiStatus(false);
  }
}

renderCalendar();
renderHistory();
renderMessages();
autoResize();
checkHealth();
setInterval(checkHealth, 30000);
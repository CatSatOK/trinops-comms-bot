/* Trinops Comms Bot — embeddable chat widget.
 *
 * Zero dependencies, self-contained. Embed with one tag:
 *
 *   <script src="https://bot.example.com/widget/chat-widget.js"
 *           data-api="https://bot.example.com"
 *           data-title="Chat with us"
 *           data-greeting="Hi! How can we help?"></script>
 *
 * data-api defaults to the page's own origin. The stylesheet is loaded from
 * the same directory as this script and every class is prefixed `tcb-` so
 * nothing bleeds into the host page.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "tcb-session";

  var script = document.currentScript;
  var apiBase = (script && script.getAttribute("data-api")) || "";
  var title = (script && script.getAttribute("data-title")) || "Chat with us";
  var greeting =
    (script && script.getAttribute("data-greeting")) ||
    "Hi! Ask me anything — if I can't help, I'll pass you to the team.";

  // stylesheet sits next to this script
  var cssHref = script && script.src
    ? script.src.replace(/chat-widget\.js.*$/, "chat-widget.css")
    : "/widget/chat-widget.css";
  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = cssHref;
  document.head.appendChild(link);

  // --- DOM ------------------------------------------------------------------

  var root = document.createElement("div");
  root.className = "tcb-root";
  root.innerHTML =
    '<button class="tcb-bubble" type="button" aria-label="Open chat">' +
    '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-9 8.36 8.5 8.5 0 0 1-3.4-.7L3 21l1.84-4.6A8.38 8.38 0 0 1 3.5 12a8.5 8.5 0 0 1 8.5-8.5 8.38 8.38 0 0 1 9 8z"></path></svg>' +
    "</button>" +
    '<div class="tcb-panel" hidden>' +
    '  <div class="tcb-header">' +
    '    <span class="tcb-status" title="Connection status"></span>' +
    '    <span class="tcb-title"></span>' +
    '    <button class="tcb-close" type="button" aria-label="Close chat">&times;</button>' +
    "  </div>" +
    '  <div class="tcb-messages"></div>' +
    '  <div class="tcb-typing" hidden><span></span><span></span><span></span></div>' +
    '  <form class="tcb-form">' +
    '    <input class="tcb-input" type="text" placeholder="Type your question…" autocomplete="off" maxlength="1000">' +
    '    <button class="tcb-send" type="submit">Send</button>' +
    "  </form>" +
    "</div>";

  var bubble = root.querySelector(".tcb-bubble");
  var panel = root.querySelector(".tcb-panel");
  var status = root.querySelector(".tcb-status");
  var messages = root.querySelector(".tcb-messages");
  var typing = root.querySelector(".tcb-typing");
  var form = root.querySelector(".tcb-form");
  var input = root.querySelector(".tcb-input");
  root.querySelector(".tcb-title").textContent = title;

  function mount() {
    document.body.appendChild(root);
  }
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);

  // --- messages -------------------------------------------------------------

  function appendMessage(who, text, handoff) {
    var msg = document.createElement("div");
    msg.className = "tcb-msg tcb-" + who + (handoff ? " tcb-handoff" : "");
    msg.textContent = text; // textContent keeps the widget XSS-safe
    if (handoff) {
      var label = document.createElement("div");
      label.className = "tcb-handoff-label";
      label.textContent = "Passed to the team";
      msg.appendChild(label);
    }
    messages.appendChild(msg);
    messages.scrollTop = messages.scrollHeight;
  }

  function showTyping(show) {
    typing.hidden = !show;
    if (show) messages.scrollTop = messages.scrollHeight;
  }

  // --- websocket --------------------------------------------------------------

  var ws = null;
  var pending = [];

  function wsUrl() {
    var base = apiBase || window.location.protocol + "//" + window.location.host;
    var url = base.replace(/^http/, "ws") + "/ws/chat";
    var session = null;
    try {
      session = window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      /* storage blocked — fall back to a fresh session per page load */
    }
    return session ? url + "?session=" + encodeURIComponent(session) : url;
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    ws = new WebSocket(wsUrl());
    ws.onopen = function () {
      status.classList.add("tcb-online");
      for (var i = 0; i < pending.length; i++) ws.send(pending[i]);
      pending = [];
    };
    ws.onmessage = function (event) {
      var data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (data.type === "session") {
        try {
          window.localStorage.setItem(STORAGE_KEY, data.session_id);
        } catch (e) {
          /* ignore */
        }
        return;
      }
      showTyping(false);
      appendMessage("bot", data.content, data.type === "handoff");
    };
    ws.onclose = function () {
      status.classList.remove("tcb-online");
    };
  }

  function send(text) {
    appendMessage("user", text);
    showTyping(true);
    var payload = JSON.stringify({ message: text });
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
    else {
      pending.push(payload);
      connect();
    }
  }

  // --- events -----------------------------------------------------------------

  var greeted = false;

  bubble.addEventListener("click", function () {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      connect();
      if (!greeted) {
        appendMessage("bot", greeting);
        greeted = true;
      }
      input.focus();
    }
  });

  root.querySelector(".tcb-close").addEventListener("click", function () {
    panel.hidden = true;
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    send(text);
  });
})();

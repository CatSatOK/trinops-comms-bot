"use strict";

const rows = document.getElementById("rows");
const transcript = document.getElementById("transcript");
const transcriptTitle = document.getElementById("transcript-title");
const transcriptMessages = document.getElementById("transcript-messages");

let conversations = [];
let activeFilter = "all";

async function load() {
  const response = await fetch("/conversations");
  conversations = await response.json();
  render();
}

function render() {
  const visible = conversations.filter(
    (c) => activeFilter === "all" || c.escalated
  );
  rows.innerHTML = "";
  for (const c of visible) {
    const tr = document.createElement("tr");
    tr.dataset.id = c.id;

    const started = document.createElement("td");
    started.textContent = new Date(c.started_at).toLocaleString();

    const session = document.createElement("td");
    session.className = "muted";
    session.textContent = c.session_id.slice(0, 8);

    const count = document.createElement("td");
    count.textContent = c.message_count;

    const status = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "badge " + (c.escalated ? "badge-escalated" : "badge-open");
    badge.textContent = c.escalated ? "ESCALATED" : "OPEN";
    status.appendChild(badge);

    const last = document.createElement("td");
    last.className = "muted";
    last.textContent = c.last_message || "";

    tr.append(started, session, count, status, last);
    tr.addEventListener("click", () => select(c.id, tr));
    rows.appendChild(tr);
  }
}

async function select(id, tr) {
  document.querySelectorAll("tbody tr").forEach((r) => r.classList.remove("selected"));
  tr.classList.add("selected");

  const response = await fetch(`/conversations/${id}`);
  const conversation = await response.json();

  transcriptTitle.textContent =
    `Session ${conversation.session_id.slice(0, 8)} — started ` +
    new Date(conversation.started_at).toLocaleString();
  transcriptMessages.innerHTML = "";

  for (const m of conversation.messages) {
    const div = document.createElement("div");
    div.className = `msg msg-${m.role}`;
    div.textContent = m.content;

    if (m.role === "ASSISTANT") {
      const meta = document.createElement("span");
      meta.className = "msg-meta";
      const source = document.createElement("span");
      source.className = `source source-${m.source}`;
      source.textContent = m.source;
      meta.appendChild(source);
      if (m.matched_question) {
        meta.append(`matched: ${m.matched_question}`);
      }
      div.appendChild(meta);
    }
    transcriptMessages.appendChild(div);
  }
  transcript.hidden = false;
}

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach((b) => b.classList.remove("active"));
    button.classList.add("active");
    activeFilter = button.dataset.filter;
    render();
  });
});

load();

/* Admin felület – kérdések, publikálás, élő diagram, reset. */

const questionsEl = document.getElementById("questions");
const form = document.getElementById("question-form");
const formMsg = document.getElementById("form-msg");

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function renderChart(q) {
  const total = q.total_votes;
  const rows = q.options.map((o) => {
    const pct = total ? Math.round((o.votes / total) * 100) : 0;
    return `<div class="bar-row">
      <div class="bar-label">${esc(o.text)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      <div class="bar-count">${o.votes} (${pct}%)</div>
    </div>`;
  }).join("");
  return `<div class="chart"><div class="chart-title">${total} szavazat</div>${rows}</div>`;
}

function render(state) {
  const qs = state.questions || [];
  if (!qs.length) {
    questionsEl.innerHTML = '<p class="muted">Még nincs kérdés. Hozz létre egyet fent!</p>';
    return;
  }
  questionsEl.innerHTML = qs.map((q) => {
    const body = q.is_active
      ? renderChart(q)
      : '<p class="muted">Nem publikált. A szavazás indításához kattints a publikálás gombra.</p>';
    const btn = q.is_active
      ? '<button class="btn" disabled>✔ Aktív</button>'
      : `<button class="btn" data-publish="${q.id}">Publikálás</button>`;
    return `<div class="question ${q.is_active ? "active" : ""}">
      <h3>${esc(q.text)} <span class="badge ${q.type}">${q.type}</span></h3>
      ${body}
      <div class="row">${btn}</div>
    </div>`;
  }).join("");

  questionsEl.querySelectorAll("[data-publish]").forEach((b) => {
    b.addEventListener("click", () => publish(Number(b.dataset.publish)));
  });
}

async function refresh() {
  try {
    const resp = await fetch("/admin/api/questions");
    render(await resp.json());
  } catch (e) { /* a szerver még nem válaszol */ }
}

async function publish(id) {
  try {
    await fetch(`/admin/api/questions/${id}/publish`, { method: "POST" });
  } finally {
    await refresh();
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = document.getElementById("q-text").value.trim();
  const type = document.getElementById("q-type").value;
  const options = document.getElementById("q-options").value
    .split("\n").map((s) => s.trim()).filter(Boolean);
  formMsg.textContent = "…";
  const resp = await fetch("/admin/api/questions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, type, options }),
  });
  if (resp.ok) {
    formMsg.textContent = "Kérdés létrehozva.";
    form.reset();
  } else {
    const data = await resp.json().catch(() => ({}));
    formMsg.textContent = "Hiba: " + (data.detail || resp.status);
  }
  await refresh();
});

document.getElementById("reset-btn").addEventListener("click", async () => {
  if (!confirm("Biztosan törölsz MINDEN kérdést és szavazatot?")) return;
  await fetch("/admin/api/reset", { method: "POST" });
  await refresh();
});

refresh();
const es = new EventSource("/events/admin");
es.addEventListener("state", (e) => {
  try { render(JSON.parse(e.data)); } catch (err) { /* érvénytelen üzenet */ }
});
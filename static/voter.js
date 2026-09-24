/* Résztvevői felület – aktív kérdés, szavazat, élő váltás SSE-vel. */

const screens = {
  waiting: document.getElementById("screen-waiting"),
  question: document.getElementById("screen-question"),
  thanks: document.getElementById("screen-thanks"),
};
const qText = document.getElementById("q-text");
const qHint = document.getElementById("q-hint");
const qOptions = document.getElementById("q-options");
const voteBtn = document.getElementById("vote-btn");
const voteMsg = document.getElementById("vote-msg");

function show(name) {
  Object.entries(screens).forEach(([key, el]) => {
    el.classList.toggle("hidden", key !== name);
  });
}

function buildOptions(q) {
  qOptions.innerHTML = "";
  for (const opt of q.options) {
    const label = document.createElement("label");
    label.className = "option";
    const input = document.createElement("input");
    input.type = q.type === "multi" ? "checkbox" : "radio";
    input.name = "option";
    input.value = String(opt.id);
    input.addEventListener("change", updateSelected);
    const span = document.createElement("span");
    span.textContent = opt.text;
    label.append(input, span);
    qOptions.appendChild(label);
  }
  updateSelected();
}

function updateSelected() {
  const picked = qOptions.querySelectorAll("input:checked");
  voteBtn.disabled = picked.length === 0;
}

function render(state) {
  const q = state.active_question;
  if (!q) { show("waiting"); return; }
  if (state.voted) { show("thanks"); return; }
  qText.textContent = q.text;
  qHint.textContent = q.type === "multi"
    ? "Több választ is megjelölhetsz."
    : "Válassz egyet, majd küldd el a szavazatod.";
  buildOptions(q);
  show("question");
}

voteBtn.addEventListener("click", async () => {
  const option_ids = Array.from(
    qOptions.querySelectorAll("input:checked"), (i) => Number(i.value)
  );
  if (!option_ids.length) return;
  voteBtn.disabled = true;
  voteMsg.textContent = "";
  try {
    const resp = await fetch("/api/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ option_ids }),
    });
    if (resp.ok || resp.status === 409) {
      show("thanks"); // 409: már szavazott – ugyanaz a végállapot
    } else {
      const data = await resp.json().catch(() => ({}));
      voteMsg.textContent = "Hiba: " + (data.detail || resp.status);
      voteBtn.disabled = false;
    }
  } catch (err) {
    voteMsg.textContent = "Hálózati hiba – próbáld újra.";
    voteBtn.disabled = false;
  }
});

async function refresh() {
  try {
    const resp = await fetch("/api/state");
    render(await resp.json());
  } catch (e) { /* szerver még nem elérhető */ }
}

const es = new EventSource("/events/participant");
es.addEventListener("state", (e) => {
  try { render(JSON.parse(e.data)); } catch (err) { /* érvénytelen üzenet */ }
});
es.onopen = refresh; // újracsatlakozáskor teljes állapot

refresh();
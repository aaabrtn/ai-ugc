// Reuses `el`, `formatDate`, `switchTab` from app.js/products.js (all three JS
// files are loaded as classic scripts on the same page, sharing one scope).

const GENERATIONS_API_BASE = "/api/generations";
const CHARACTERS_API_BASE = "/api/characters";

const scriptListView = el("script-list-view");
const scriptFormView = el("script-form-view");
const scriptDetailView = el("script-detail-view");
const scriptListEl = el("script-list");
const scriptEmptyState = el("script-empty-state");
const scriptForm = el("script-form");
const scriptFormError = el("script-form-error");
const scriptCharacterSelect = el("sf-character");
const scriptProductSelect = el("sf-product");
const scriptSubmitBtn = el("script-submit-btn");

const STAGE_LABELS = {
  draft: "Draft",
  blocked: "Blocked",
  prompt_generated: "Draft — needs review",
  approved: "Approved",
};

const CHECK_ICONS = { pass: "✓", fail: "✕", manual: "!" };

const VIDEO_STATUS_LABELS = {
  not_started: "Not started",
  waiting: "Queued",
  queuing: "Queued",
  generating: "Generating…",
  success: "Complete",
  fail: "Failed",
};

// ---------- View switching ----------

function showScriptList() {
  stopPolling();
  scriptFormView.hidden = true;
  scriptDetailView.hidden = true;
  scriptListView.hidden = false;
  loadScripts();
}

function showScriptForm() {
  stopPolling();
  scriptListView.hidden = true;
  scriptDetailView.hidden = true;
  scriptFormView.hidden = false;
  resetScriptForm();
  loadScriptFormOptions();
}

function showScriptDetail(script) {
  scriptListView.hidden = true;
  scriptFormView.hidden = true;
  scriptDetailView.hidden = false;
  renderScriptDetail(script);
}

el("new-script-btn").addEventListener("click", showScriptForm);
el("script-empty-new-btn").addEventListener("click", showScriptForm);
el("script-cancel-btn").addEventListener("click", showScriptList);
el("script-detail-back-btn").addEventListener("click", showScriptList);

// ---------- List ----------

async function loadScripts() {
  const res = await fetch(GENERATIONS_API_BASE);
  const scripts = await res.json();
  scriptListEl.innerHTML = "";
  scriptEmptyState.hidden = scripts.length > 0;
  for (const script of scripts) {
    scriptListEl.appendChild(renderScriptCard(script));
  }
}

function renderScriptCard(script) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.addEventListener("click", () => showScriptDetail(script));

  const thumb = document.createElement("div");
  if (script.product.thumbnail_url) {
    thumb.className = "thumb";
    const img = document.createElement("img");
    img.src = script.product.thumbnail_url;
    thumb.appendChild(img);
  } else {
    thumb.className = "thumb";
    thumb.textContent = "No photo";
  }

  const body = document.createElement("div");
  body.className = "job-card-body";

  const title = document.createElement("h3");
  title.textContent = `${script.character.name} × ${script.product.name}`;

  const meta = document.createElement("p");
  meta.className = "job-card-url";
  meta.textContent = formatDate(script.created_at);

  const badge = document.createElement("span");
  if (script.stage === "approved" && script.video_status !== "not_started") {
    badge.className = "badge " + (script.video_status === "success" ? "badge-ok" : script.video_status === "fail" ? "badge-fail" : "badge-muted");
    badge.textContent = "Video: " + (VIDEO_STATUS_LABELS[script.video_status] || script.video_status);
  } else {
    badge.className = "badge " + (script.stage === "blocked" ? "badge-fail" : script.stage === "approved" ? "badge-ok" : "badge-muted");
    badge.textContent = STAGE_LABELS[script.stage] || script.stage;
  }

  body.append(title, meta, badge);
  card.append(thumb, body);
  return card;
}

// ---------- Create form ----------

function resetScriptForm() {
  scriptForm.reset();
  scriptFormError.hidden = true;
}

async function loadScriptFormOptions() {
  const [charactersRes, productsRes] = await Promise.all([
    fetch(CHARACTERS_API_BASE),
    fetch(PRODUCTS_API_BASE),
  ]);
  const characters = await charactersRes.json();
  const products = (await productsRes.json()).filter((p) => p.fetch_status === "success");

  scriptCharacterSelect.innerHTML = "";
  if (!characters.length) {
    const opt = document.createElement("option");
    opt.textContent = "Create a character first";
    opt.disabled = true;
    opt.selected = true;
    scriptCharacterSelect.appendChild(opt);
  } else {
    for (const c of characters) {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.name;
      scriptCharacterSelect.appendChild(opt);
    }
  }

  scriptProductSelect.innerHTML = "";
  if (!products.length) {
    const opt = document.createElement("option");
    opt.textContent = "Add a product first";
    opt.disabled = true;
    opt.selected = true;
    scriptProductSelect.appendChild(opt);
  } else {
    for (const p of products) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      scriptProductSelect.appendChild(opt);
    }
  }

  scriptSubmitBtn.disabled = !characters.length || !products.length;
}

scriptForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  scriptFormError.hidden = true;

  const characterId = scriptCharacterSelect.value;
  const productId = scriptProductSelect.value;
  if (!characterId || !productId) {
    showScriptFormError("Choose a character and a product.");
    return;
  }

  const fd = new FormData();
  fd.append("character_id", characterId);
  fd.append("product_id", productId);

  scriptSubmitBtn.disabled = true;
  try {
    const res = await fetch(GENERATIONS_API_BASE, { method: "POST", body: fd });
    if (!res.ok) {
      showScriptFormError(await extractScriptError(res));
      return;
    }
    const script = await res.json();
    showScriptDetail(script);
  } finally {
    scriptSubmitBtn.disabled = false;
  }
});

async function extractScriptError(res) {
  try {
    const body = await res.json();
    return body.detail || "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

function showScriptFormError(message) {
  scriptFormError.textContent = message;
  scriptFormError.hidden = false;
}

// ---------- Detail ----------

let currentScript = null;

function renderScriptDetail(script) {
  currentScript = script;
  el("script-detail-eyebrow").textContent = script.character.name;
  el("script-detail-title").textContent = script.product.name;
  el("script-detail-date").textContent = "Created " + formatDate(script.created_at);

  renderPromptSection(script);
  renderVideoSection(script);
}

function renderPromptSection(script) {
  const generateSection = el("script-detail-generate-section");
  const promptSection = el("script-detail-prompt-section");

  if (script.stage === "draft") {
    generateSection.hidden = false;
    promptSection.hidden = true;
    return;
  }

  generateSection.hidden = true;
  promptSection.hidden = false;

  const stageBadge = el("script-detail-stage-badge");
  stageBadge.textContent = STAGE_LABELS[script.stage] || script.stage;
  stageBadge.className =
    "badge " + (script.stage === "blocked" ? "badge-fail" : script.stage === "approved" ? "badge-ok" : "badge-muted");

  const checklist = el("script-detail-checklist");
  checklist.innerHTML = "";
  for (const check of script.sop_check_results) {
    const item = document.createElement("div");
    item.className = `checklist-item ${check.status}`;

    const icon = document.createElement("span");
    icon.className = "checklist-icon";
    icon.textContent = CHECK_ICONS[check.status] || "?";

    const body = document.createElement("div");
    body.className = "checklist-body";
    const label = document.createElement("p");
    label.className = "checklist-label";
    label.textContent = check.label;
    const detail = document.createElement("p");
    detail.className = "checklist-detail";
    detail.textContent = check.detail;
    body.append(label, detail);

    item.append(icon, body);
    checklist.appendChild(item);
  }

  const promptTextarea = el("script-detail-prompt-text");
  const approveBtn = el("script-approve-btn");

  if (script.stage === "blocked") {
    promptTextarea.hidden = true;
    approveBtn.hidden = true;
  } else {
    promptTextarea.hidden = false;
    promptTextarea.value = script.generated_prompt;
    approveBtn.hidden = false;
    approveBtn.textContent = script.stage === "approved" ? "Approved ✓" : "Approve Prompt";
    approveBtn.disabled = script.stage === "approved";
  }
}

let pollTimer = null;
let pollAttempt = 0;

function stopPolling() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
  pollAttempt = 0;
}

function renderVideoSection(script) {
  const section = el("script-detail-video-section");
  stopPolling();

  if (script.stage !== "approved") {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const badge = el("script-video-status-badge");
  const hint = el("script-video-hint");
  const player = el("script-video-player");
  const submitBtn = el("script-submit-video-btn");

  badge.textContent = VIDEO_STATUS_LABELS[script.video_status] || script.video_status;
  badge.className =
    "badge " +
    (script.video_status === "success" ? "badge-ok" : script.video_status === "fail" ? "badge-fail" : "badge-muted");

  if (script.video_status === "not_started") {
    hint.textContent = "Submits the approved prompt, the character, and its setting/garment reference photos to KIE.";
    submitBtn.hidden = false;
    submitBtn.disabled = false;
    submitBtn.textContent = "Generate Video";
    player.hidden = true;
  } else if (script.video_status === "success") {
    hint.textContent = "Done.";
    submitBtn.hidden = true;
    player.hidden = false;
    player.src = script.video_url;
  } else if (script.video_status === "fail") {
    hint.textContent = script.video_error || "Generation failed.";
    submitBtn.hidden = false;
    submitBtn.disabled = false;
    submitBtn.textContent = "Try Again";
    player.hidden = true;
  } else {
    // waiting / queuing / generating
    hint.textContent = "This can take a few minutes — status updates automatically.";
    submitBtn.hidden = true;
    player.hidden = true;
    schedulePoll(script.id);
  }
}

function schedulePoll(scriptId) {
  const delay = Math.min(3000 * Math.pow(1.4, pollAttempt), 15000);
  pollAttempt += 1;
  pollTimer = setTimeout(async () => {
    try {
      const res = await fetch(`${GENERATIONS_API_BASE}/${scriptId}/video-status`);
      if (!res.ok) {
        // transient poll failure -- keep retrying rather than treating it as final
        schedulePoll(scriptId);
        return;
      }
      const script = await res.json();
      if (currentScript && currentScript.id === script.id) {
        currentScript = script;
        renderVideoSection(script);
      }
    } catch {
      schedulePoll(scriptId);
    }
  }, delay);
}

el("script-submit-video-btn").addEventListener("click", async () => {
  if (!currentScript) return;
  const btn = el("script-submit-video-btn");
  btn.disabled = true;
  btn.textContent = "Submitting…";
  try {
    const res = await fetch(`${GENERATIONS_API_BASE}/${currentScript.id}/submit-video`, { method: "POST" });
    if (!res.ok) {
      alert(await extractScriptError(res));
      btn.disabled = false;
      btn.textContent = "Generate Video";
      return;
    }
    const script = await res.json();
    currentScript = script;
    renderVideoSection(script);
  } catch {
    btn.disabled = false;
    btn.textContent = "Generate Video";
  }
});

async function runGenerate(button) {
  if (!currentScript) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    const res = await fetch(`${GENERATIONS_API_BASE}/${currentScript.id}/generate`, { method: "POST" });
    if (!res.ok) {
      alert(await extractScriptError(res));
      return;
    }
    const script = await res.json();
    renderScriptDetail(script);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

el("script-generate-first-btn").addEventListener("click", (e) => runGenerate(e.currentTarget));
el("script-generate-btn").addEventListener("click", (e) => {
  if (!confirm("Regenerate this prompt? Any edits you've made will be discarded.")) return;
  runGenerate(e.currentTarget);
});

el("script-approve-btn").addEventListener("click", async () => {
  if (!currentScript) return;
  const btn = el("script-approve-btn");
  const promptText = el("script-detail-prompt-text").value;
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const fd = new FormData();
    fd.append("edited_prompt", promptText);
    const res = await fetch(`${GENERATIONS_API_BASE}/${currentScript.id}/approve`, { method: "PUT", body: fd });
    if (!res.ok) {
      alert(await extractScriptError(res));
      return;
    }
    const script = await res.json();
    renderScriptDetail(script);
  } finally {
    btn.disabled = false;
  }
});

el("script-delete-btn").addEventListener("click", async () => {
  if (!currentScript) return;
  if (!confirm("Delete this script? This cannot be undone.")) return;
  const res = await fetch(`${GENERATIONS_API_BASE}/${currentScript.id}`, { method: "DELETE" });
  if (res.ok) {
    showScriptList();
  } else {
    alert("Failed to delete script.");
  }
});

// Scripts is the app's home view, so load it immediately rather than waiting
// for a tab click.
loadScripts();

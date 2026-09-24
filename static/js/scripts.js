// Reuses `el`, `formatDate`, `switchTab` from app.js/products.js (all three JS
// files are loaded as classic scripts on the same page, sharing one scope).

const GENERATIONS_API_BASE = "/api/generations";
const CHARACTERS_API_BASE = "/api/characters";

const scriptFormView = el("script-form-view");
const scriptDetailView = el("script-detail-view");
const scriptForm = el("script-form");
const scriptFormError = el("script-form-error");
const scriptCharacterSelect = el("sf-character");
const scriptProductSelect = el("sf-product");
const scriptSubmitBtn = el("script-submit-btn");
const scriptCreateAndGenerateBtn = el("script-create-and-generate-btn");

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

function showScriptForm() {
  scriptDetailView.hidden = true;
  scriptFormView.hidden = false;
  resetScriptForm();
  loadScriptFormOptions();
}

function showScriptDetail(script) {
  scriptFormView.hidden = true;
  scriptDetailView.hidden = false;
  renderScriptDetail(script);
}

el("script-cancel-btn").addEventListener("click", showScriptForm);
el("script-detail-back-btn").addEventListener("click", showScriptForm);

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

scriptCreateAndGenerateBtn.addEventListener("click", async () => {
  scriptFormError.hidden = true;

  const characterId = scriptCharacterSelect.value;
  const productId = scriptProductSelect.value;
  if (!characterId || !productId) {
    showScriptFormError("Choose a character and a product.");
    return;
  }

  const originalText = scriptCreateAndGenerateBtn.textContent;
  scriptCreateAndGenerateBtn.disabled = true;
  scriptSubmitBtn.disabled = true;

  try {
    const fd = new FormData();
    fd.append("character_id", characterId);
    fd.append("product_id", productId);
    let res = await fetch(GENERATIONS_API_BASE, { method: "POST", body: fd });
    if (!res.ok) {
      showScriptFormError(await extractScriptError(res));
      return;
    }
    let script = await res.json();
    currentScript = script;
    // Switch to the detail view right away so each step's progress (stage
    // badge, then video status) is visible live, not just the final result.
    showScriptDetail(script);

    script = await generateApproveAndSubmit(script, {
      onStep: (s) => { currentScript = s; renderScriptDetail(s); },
    });
    currentScript = script;
    renderScriptDetail(script);
  } catch (e) {
    if (e instanceof StepError) {
      currentScript = e.script;
      renderScriptDetail(e.script);
    } else {
      alert(e.message);
    }
  } finally {
    scriptCreateAndGenerateBtn.disabled = false;
    scriptCreateAndGenerateBtn.textContent = originalText;
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

  const failedCheck = script.sop_check_results.find((c) => c.status === "fail");
  const item = document.createElement("div");
  const icon = document.createElement("span");
  icon.className = "checklist-icon";
  const body = document.createElement("div");
  body.className = "checklist-body";
  const label = document.createElement("p");
  label.className = "checklist-label";

  if (failedCheck) {
    item.className = "checklist-item fail";
    icon.textContent = CHECK_ICONS.fail;
    label.textContent = failedCheck.label;
    const detail = document.createElement("p");
    detail.className = "checklist-detail";
    detail.textContent = failedCheck.detail;
    body.append(label, detail);
  } else {
    item.className = "checklist-item pass";
    icon.textContent = CHECK_ICONS.pass;
    label.textContent = "Video prompts SOP followed or confirmed.";
    body.append(label);
  }

  item.append(icon, body);
  checklist.appendChild(item);

  const visionCostLine = el("script-detail-vision-cost");
  if (script.vision_cost_usd !== null && script.vision_cost_usd !== undefined) {
    visionCostLine.hidden = false;
    visionCostLine.textContent = `AI cost so far: ${formatCost(script.vision_cost_usd)}`;
  } else {
    visionCostLine.hidden = true;
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

// Tracks background status-polling per generation (scriptId -> setTimeout id),
// independent of which view is currently open. A video submitted to KIE keeps
// generating on KIE's servers regardless of what the browser is showing, so
// polling must not stop just because the user switched tabs or navigated back
// to the Generator's blank form -- otherwise the app loses track of it, the
// database is never updated to "success", and it silently never appears in
// History even though the video may have actually finished.
const activePolls = new Map();

// Generations currently mid-submit-video-call. The one-click flows
// (generateApproveAndSubmit) re-render the video section right after the
// approve step, before the submit-video call has actually started — at that
// instant stage is "approved" and video_status is still "not_started", which
// is exactly the state that normally shows a live, clickable "Generate
// Video" button. Without this guard a click in that brief window fires a
// second, independent submission (the backend now also refuses a second
// submit-video call as a hard guard, but this stops the button from ever
// appearing clickable in the first place).
const submittingVideoIds = new Set();

function stopPolling(scriptId) {
  const timer = activePolls.get(scriptId);
  if (timer) clearTimeout(timer);
  activePolls.delete(scriptId);
}

function schedulePoll(scriptId, attempt = 0) {
  if (activePolls.has(scriptId)) return; // already being tracked
  activePolls.set(scriptId, null); // reserve the slot before the first tick
  pollTick(scriptId, attempt);
}

function pollTick(scriptId, attempt) {
  const delay = Math.min(3000 * Math.pow(1.4, attempt), 15000);
  const timer = setTimeout(async () => {
    try {
      const res = await fetch(`${GENERATIONS_API_BASE}/${scriptId}/video-status`);
      if (!res.ok) {
        pollTick(scriptId, attempt + 1);
        return;
      }
      const script = await res.json();
      if (script.video_status === "success" || script.video_status === "fail") {
        activePolls.delete(scriptId);
      } else {
        pollTick(scriptId, attempt + 1);
      }
      // Only touch the DOM if this generation's detail page happens to be open.
      if (currentScript && currentScript.id === script.id) {
        currentScript = script;
        renderVideoSection(script);
      }
    } catch {
      pollTick(scriptId, attempt + 1);
    }
  }, delay);
  activePolls.set(scriptId, timer);
}

async function resumeInProgressPolls() {
  // Runs once on load: picks back up any generation left mid-flight from a
  // previous visit (e.g. the tab was switched or the page was reloaded while
  // a video was still generating), instead of leaving it stuck and untracked.
  const IN_PROGRESS = ["waiting", "queuing", "generating"];
  try {
    const res = await fetch(GENERATIONS_API_BASE);
    if (!res.ok) return;
    const scripts = await res.json();
    for (const script of scripts) {
      if (IN_PROGRESS.includes(script.video_status)) {
        schedulePoll(script.id);
      }
    }
  } catch {
    // best-effort -- reopening that script's detail page also resumes polling
  }
}

function renderVideoSection(script) {
  const section = el("script-detail-video-section");

  if (script.stage !== "approved") {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const badge = el("script-video-status-badge");
  const hint = el("script-video-hint");
  const videoResult = el("script-video-result");
  const submitBtn = el("script-submit-video-btn");

  badge.textContent = VIDEO_STATUS_LABELS[script.video_status] || script.video_status;
  badge.className =
    "badge " +
    (script.video_status === "success" ? "badge-ok" : script.video_status === "fail" ? "badge-fail" : "badge-muted");

  videoResult.innerHTML = "";
  videoResult.hidden = true;

  if (script.video_status === "not_started" && submittingVideoIds.has(script.id)) {
    hint.textContent = "Submitting to KIE…";
    submitBtn.hidden = true;
  } else if (script.video_status === "not_started") {
    hint.textContent = "Submits the approved prompt, the character, and its setting/garment reference photos to KIE.";
    submitBtn.hidden = false;
    submitBtn.disabled = false;
    submitBtn.textContent = "Generate Video";
  } else if (script.video_status === "success") {
    hint.textContent = "Done — also saved to History.";
    submitBtn.hidden = true;
    videoResult.hidden = false;
    videoResult.appendChild(buildVideoResultRow(script));
  } else if (script.video_status === "fail") {
    hint.textContent = script.video_error || "Generation failed.";
    submitBtn.hidden = false;
    submitBtn.disabled = false;
    submitBtn.textContent = "Try Again";
  } else {
    // waiting / queuing / generating
    hint.textContent = "This can take a few minutes — status updates automatically.";
    submitBtn.hidden = true;
    schedulePoll(script.id);
  }
}

function formatCost(usd) {
  if (usd === null || usd === undefined) return null;
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

// Vision cost is exact (real Anthropic token usage). KIE cost is a configured
// estimate (see KIE_CREDITS_PER_VIDEO in .env) since KIE's API has no
// per-task price field -- labelled "~" throughout to keep that honest.
function buildCostLine(script) {
  const visionKnown = script.vision_cost_usd !== null && script.vision_cost_usd !== undefined;
  const kieUsdKnown = script.kie_usd_cost !== null && script.kie_usd_cost !== undefined;
  const kieCreditsKnown = script.kie_credits_cost !== null && script.kie_credits_cost !== undefined;
  if (!visionKnown && !kieCreditsKnown) return null;

  const detailParts = [];
  if (visionKnown) detailParts.push(`AI ${formatCost(script.vision_cost_usd)}`);
  if (kieUsdKnown) {
    detailParts.push(`video ~${formatCost(script.kie_usd_cost)}`);
  } else if (kieCreditsKnown) {
    detailParts.push(`video ~${script.kie_credits_cost} credits`);
  }

  const p = document.createElement("p");
  p.className = "video-result-cost";
  const totalKnown = script.total_cost_usd !== null && script.total_cost_usd !== undefined;
  p.textContent = totalKnown
    ? `Total: ~${formatCost(script.total_cost_usd)} (${detailParts.join(" + ")})`
    : detailParts.join(" + ");
  return p;
}

function buildDownloadLink(script, className) {
  const downloadLink = document.createElement("a");
  downloadLink.className = className;
  downloadLink.href = script.video_url;
  downloadLink.download = `${script.character.name}-${script.product.name}`.replace(/[^\w.-]+/g, "-") + ".mp4";
  downloadLink.textContent = "Download";
  return downloadLink;
}

// Single-line total, no Anthropic/KIE split — used on History cards, where a
// full breakdown is more detail than useful at a glance.
function buildTotalCostLine(script) {
  if (script.total_cost_usd === null || script.total_cost_usd === undefined) return null;
  const p = document.createElement("p");
  p.className = "video-result-cost";
  p.textContent = `Total AI cost: ~${formatCost(script.total_cost_usd)}`;
  return p;
}

// Builds the compact result video (plus a download link and cost breakdown)
// shown on the script detail page once a video finishes. Just the video
// itself, kept small — character/product are already identified elsewhere
// (the script's own title/eyebrow), so repeating their thumbnails here would
// just be noise.
function buildVideoResultRow(script) {
  const block = document.createElement("div");
  block.className = "video-result-block";

  const videoItem = document.createElement("div");
  videoItem.className = "video-result-player";
  const video = document.createElement("video");
  video.controls = true;
  video.src = script.video_url;
  videoItem.append(video, buildDownloadLink(script, "btn btn-ghost btn-sm"));
  block.appendChild(videoItem);

  const costLine = buildCostLine(script);
  if (costLine) block.appendChild(costLine);

  return block;
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

// Carries the last successfully-reached script state, so a failure partway
// through still leaves the caller able to render exactly where things stopped
// rather than the stale pre-call state.
class StepError extends Error {
  constructor(message, script) {
    super(message);
    this.script = script;
  }
}

// Runs generate -> (unless blocked) approve as-is -> submit-video, as one
// sequence. Shared by both the script detail page's one-click button and the
// "Generate Video" button on the create-script form. onStatus fires before
// each step (for a progress label); onStep fires after each step succeeds
// (so the caller can keep its own currentScript / render in sync live).
async function generateApproveAndSubmit(script, { onStatus, onStep } = {}) {
  onStatus?.("Generating prompt…");
  let res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/generate`, { method: "POST" });
  if (!res.ok) throw new StepError(await extractScriptError(res), script);
  script = await res.json();
  onStep?.(script);

  if (script.stage === "blocked") {
    // No current check actually blocks (the one that did, the content-boundary
    // rule, was removed) — this is just defensive: if a check ever becomes
    // blocking again, this never auto-approves/submits past it.
    return script;
  }

  onStatus?.("Approving…");
  const fd = new FormData();
  fd.append("edited_prompt", script.generated_prompt);
  res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/approve`, { method: "PUT", body: fd });
  if (!res.ok) throw new StepError(await extractScriptError(res), script);
  script = await res.json();
  // Mark as "about to submit" before the render below, so it never exposes a
  // live, clickable Generate Video button in the gap before the submit-video
  // call actually starts (see submittingVideoIds above).
  submittingVideoIds.add(script.id);
  onStep?.(script);

  onStatus?.("Submitting video…");
  try {
    res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/submit-video`, { method: "POST" });
    if (!res.ok) throw new StepError(await extractScriptError(res), script);
    script = await res.json();
  } finally {
    submittingVideoIds.delete(script.id);
  }
  onStep?.(script);

  return script;
}

async function runGenerateAndSubmitVideo(button) {
  if (!currentScript) return;
  const otherBtn = el("script-generate-first-btn");
  const originalText = button.textContent;
  button.disabled = true;
  otherBtn.disabled = true;

  try {
    const script = await generateApproveAndSubmit(currentScript, {
      onStatus: (text) => { button.textContent = text; },
      onStep: (s) => { currentScript = s; },
    });
    currentScript = script;
    renderScriptDetail(script);
  } catch (e) {
    if (e instanceof StepError) {
      currentScript = e.script;
      renderScriptDetail(e.script);
    }
    alert(e.message);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
    otherBtn.disabled = false;
  }
}

el("script-generate-first-btn").addEventListener("click", (e) => runGenerate(e.currentTarget));
el("script-generate-and-video-btn").addEventListener("click", (e) => runGenerateAndSubmitVideo(e.currentTarget));
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
    stopPolling(currentScript.id);
    showScriptForm();
  } else {
    alert("Failed to delete script.");
  }
});

// ---------- History ----------

const historyListEl = el("history-list");
const historyEmptyState = el("history-empty-state");
const historySummaryEl = el("history-summary");

async function loadHistory() {
  const res = await fetch(GENERATIONS_API_BASE);
  const scripts = await res.json();
  const finished = scripts.filter((s) => s.video_status === "success");
  historyListEl.innerHTML = "";
  historyEmptyState.hidden = finished.length > 0;
  for (const script of finished) {
    historyListEl.appendChild(renderHistoryCard(script));
  }
  renderHistorySummary(finished);
}

function scriptDate(script) {
  // Same naive-UTC handling as formatDate: server timestamps have no offset.
  return new Date(script.created_at.endsWith("Z") ? script.created_at : `${script.created_at}Z`);
}

function costSummaryLine(label, group) {
  const known = group.filter((s) => s.total_cost_usd !== null && s.total_cost_usd !== undefined);
  if (!known.length) return `${label}: no cost data yet for ${group.length} video${group.length === 1 ? "" : "s"}`;
  const total = known.reduce((sum, s) => sum + s.total_cost_usd, 0);
  const coverage = known.length === group.length ? "" : ` (cost known for ${known.length} of ${group.length})`;
  return `${label}: ~${formatCost(total)} across ${group.length} video${group.length === 1 ? "" : "s"}${coverage}`;
}

function renderHistorySummary(finished) {
  if (!finished.length) {
    historySummaryEl.hidden = true;
    return;
  }
  const now = new Date();
  const thisMonth = finished.filter((s) => {
    const d = scriptDate(s);
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  });

  historySummaryEl.hidden = false;
  historySummaryEl.innerHTML = "";
  const monthLine = document.createElement("p");
  monthLine.textContent = costSummaryLine("This month", thisMonth);
  const totalLine = document.createElement("p");
  totalLine.textContent = costSummaryLine("All time", finished);
  historySummaryEl.append(monthLine, totalLine);
}

function formatDateTime(isoString) {
  // Same naive-UTC handling as formatDate: server timestamps have no offset.
  const d = new Date(isoString.endsWith("Z") ? isoString : `${isoString}Z`);
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function renderHistoryCard(script) {
  const card = document.createElement("div");
  card.className = "history-card";

  const video = document.createElement("video");
  video.controls = true;
  video.src = script.video_url;
  card.appendChild(video);

  const title = document.createElement("h3");
  title.textContent = `${script.character.name} × ${script.product.name}`;
  card.appendChild(title);

  // Date *and* time, not just date — outfits repeated across characters/products
  // otherwise produce identically-titled cards with no way to tell them apart.
  const date = document.createElement("p");
  date.className = "job-card-url";
  date.textContent = formatDateTime(script.created_at);
  card.appendChild(date);

  const costLine = buildTotalCostLine(script);
  if (costLine) card.appendChild(costLine);

  const actions = document.createElement("div");
  actions.className = "history-card-actions";

  const viewBtn = document.createElement("button");
  viewBtn.type = "button";
  viewBtn.className = "btn btn-ghost btn-sm";
  viewBtn.textContent = "Open script";
  viewBtn.addEventListener("click", () => {
    switchTab("scripts");
    showScriptDetail(script);
  });

  actions.append(viewBtn, buildDownloadLink(script, "btn btn-primary btn-sm"));
  card.appendChild(actions);

  return card;
}

// The Generator is the app's home view, so show the form immediately rather
// than waiting for a tab click. Past generations live in History instead.
showScriptForm();

// Pick back up any generation still mid-flight from before this page load.
resumeInProgressPolls();

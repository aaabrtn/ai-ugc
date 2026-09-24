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
const sfAspectRatioSelect = el("sf-aspect-ratio");
const sfResolutionSelect = el("sf-resolution");
const sfCostEstimate = el("sf-cost-estimate");
const sfProgress = el("sf-progress");

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
el("script-detail-back-btn").addEventListener("click", showScriptForm);

// ---------- Create form ----------

function resetScriptForm() {
  scriptForm.reset();
  scriptFormError.hidden = true;
  sfProgress.hidden = true;
  sfProgress.innerHTML = "";
  updateCostEstimate();
}

function selectedDuration() {
  return scriptForm.querySelector('input[name="sf-duration"]:checked')?.value || "8";
}

async function updateCostEstimate() {
  const duration = selectedDuration();
  const resolution = sfResolutionSelect.value;
  try {
    const res = await fetch(
      `${GENERATIONS_API_BASE}/cost-estimate?duration=${encodeURIComponent(duration)}&resolution=${encodeURIComponent(resolution)}`,
    );
    const data = await res.json();
    if (data.credits === null || data.credits === undefined) {
      sfCostEstimate.textContent = "Estimated cost: unknown for this combination.";
      return;
    }
    const usdText = data.usd !== null && data.usd !== undefined ? ` (~${formatCost(data.usd)})` : "";
    sfCostEstimate.textContent = `Estimated cost: ~${data.credits} credits${usdText}`;
  } catch {
    sfCostEstimate.textContent = "Estimated cost: couldn't load.";
  }
}

scriptForm.querySelectorAll('input[name="sf-duration"]').forEach((input) => {
  input.addEventListener("change", updateCostEstimate);
});
sfResolutionSelect.addEventListener("change", updateCostEstimate);

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

function buildCreateGenerationFormData(characterId, productId) {
  const fd = new FormData();
  fd.append("character_id", characterId);
  fd.append("product_id", productId);
  fd.append("duration", selectedDuration());
  fd.append("aspect_ratio", sfAspectRatioSelect.value);
  fd.append("resolution", sfResolutionSelect.value);
  return fd;
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

  scriptSubmitBtn.disabled = true;
  try {
    const res = await fetch(GENERATIONS_API_BASE, {
      method: "POST",
      body: buildCreateGenerationFormData(characterId, productId),
    });
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

// ---------- Inline chronological progress (Generate Video, in place) ----------
// Builds out below the form as each stage actually happens -- no navigation,
// no prompt/script text shown, just what's currently running and what's done.

function addProgressStep(label) {
  const row = document.createElement("div");
  row.className = "sf-progress-step pending";

  const icon = document.createElement("span");
  icon.className = "sf-progress-icon";
  icon.appendChild(document.createElement("span")).className = "sf-progress-spinner";

  const body = document.createElement("div");
  body.className = "sf-progress-body";
  const labelEl = document.createElement("p");
  labelEl.className = "sf-progress-label";
  labelEl.textContent = label;
  body.appendChild(labelEl);

  row.append(icon, body);
  sfProgress.hidden = false;
  sfProgress.appendChild(row);
  return { row, icon, body, labelEl };
}

function markStepDone(step, newLabel) {
  step.row.classList.remove("pending");
  step.row.classList.add("done");
  step.icon.textContent = "✓";
  if (newLabel) step.labelEl.textContent = newLabel;
}

function markStepFailed(step, detail) {
  step.row.classList.remove("pending");
  step.row.classList.add("fail");
  step.icon.textContent = "✕";
  if (detail) {
    const detailEl = document.createElement("p");
    detailEl.className = "sf-progress-detail";
    detailEl.textContent = detail;
    step.body.appendChild(detailEl);
  }
}

scriptCreateAndGenerateBtn.addEventListener("click", async () => {
  scriptFormError.hidden = true;

  const characterId = scriptCharacterSelect.value;
  const productId = scriptProductSelect.value;
  if (!characterId || !productId) {
    showScriptFormError("Choose a character and a product.");
    return;
  }

  scriptCreateAndGenerateBtn.disabled = true;
  scriptSubmitBtn.disabled = true;
  sfProgress.innerHTML = "";
  sfProgress.hidden = false;

  const scriptStep = addProgressStep("Writing the script and prompt…");

  try {
    let res = await fetch(GENERATIONS_API_BASE, {
      method: "POST",
      body: buildCreateGenerationFormData(characterId, productId),
    });
    if (!res.ok) {
      markStepFailed(scriptStep, await extractScriptError(res));
      return;
    }
    let script = await res.json();

    res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/generate`, { method: "POST" });
    if (!res.ok) {
      markStepFailed(scriptStep, await extractScriptError(res));
      return;
    }
    script = await res.json();

    if (script.stage === "blocked") {
      // Defensive only -- no current SOP check actually blocks (see the
      // comment on generateApproveAndSubmit's own blocked-stage check).
      markStepFailed(scriptStep, "Blocked by an SOP check.");
      return;
    }

    const approveFd = new FormData();
    approveFd.append("edited_prompt", script.generated_prompt);
    res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/approve`, { method: "PUT", body: approveFd });
    if (!res.ok) {
      markStepFailed(scriptStep, await extractScriptError(res));
      return;
    }
    script = await res.json();
    markStepDone(scriptStep);

    const submitStep = addProgressStep("Submitting to KIE…");
    res = await fetch(`${GENERATIONS_API_BASE}/${script.id}/submit-video`, { method: "POST" });
    if (!res.ok) {
      markStepFailed(submitStep, await extractScriptError(res));
      return;
    }
    script = await res.json();
    markStepDone(submitStep);

    const genStep = addProgressStep("Generating your video — this can take a few minutes…");
    const finalScript = await awaitVideoCompletion(script.id);

    if (finalScript.video_status === "success") {
      markStepDone(genStep, "Video generated.");
      const doneStep = addProgressStep("Completed");
      const viewBtn = document.createElement("button");
      viewBtn.type = "button";
      viewBtn.className = "btn btn-primary btn-sm";
      viewBtn.textContent = "View in History";
      viewBtn.addEventListener("click", () => switchTab("history"));
      doneStep.body.appendChild(viewBtn);
      markStepDone(doneStep);
    } else {
      markStepFailed(genStep, finalScript.video_error || "Generation failed.");
    }
  } catch (e) {
    markStepFailed(scriptStep, e.message || "Something went wrong.");
  } finally {
    scriptCreateAndGenerateBtn.disabled = false;
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

const IN_PROGRESS_VIDEO_STATUSES = ["waiting", "queuing", "generating"];

// Tracks background status-polling per generation (scriptId -> setTimeout id),
// independent of which view is currently open. A video submitted to KIE keeps
// generating on KIE's servers regardless of what the browser is showing, so
// polling must not stop just because the user switched tabs or navigated back
// to the Generator's blank form -- otherwise the app loses track of it, the
// database is never updated to "success", and it silently never appears in
// History even though the video may have actually finished. The server also
// now polls KIE for every in-progress generation on its own (app/background.py),
// so a finished video reaches History even if no browser was open at all --
// this client-side polling is just for a responsive UI when one is.
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

// Per-scriptId subscribers notified on every poll tick, not just when that
// script's detail page happens to be open — this is what lets the inline
// Generate Video flow on the Generator form `await` a result without a
// second, competing polling loop of its own.
const pollListeners = new Map();

function onPollUpdate(scriptId, callback) {
  if (!pollListeners.has(scriptId)) pollListeners.set(scriptId, new Set());
  pollListeners.get(scriptId).add(callback);
  return () => pollListeners.get(scriptId)?.delete(callback);
}

function awaitVideoCompletion(scriptId) {
  return new Promise((resolve) => {
    const unsubscribe = onPollUpdate(scriptId, (script) => {
      if (script.video_status === "success" || script.video_status === "fail") {
        unsubscribe();
        resolve(script);
      }
    });
    schedulePoll(scriptId);
  });
}

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
      const listeners = pollListeners.get(scriptId);
      if (listeners) for (const cb of Array.from(listeners)) cb(script);
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
  try {
    const res = await fetch(GENERATIONS_API_BASE);
    if (!res.ok) return;
    const scripts = await res.json();
    for (const script of scripts) {
      if (IN_PROGRESS_VIDEO_STATUSES.includes(script.video_status)) {
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

// Vision cost is exact (real Anthropic token usage). KIE cost is looked up
// from its published credit table for the settings actually used (duration,
// resolution), since KIE's task-status API has no per-task price field --
// labelled "~" throughout to keep that honest.
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

// Listener unsubscribes from the most recent loadHistory() call, so that
// re-rendering History (e.g. switching tabs back and forth) doesn't pile up
// duplicate "refresh when this one finishes" subscriptions.
let historyPollUnsubscribes = [];

async function loadHistory() {
  const res = await fetch(GENERATIONS_API_BASE);
  const scripts = await res.json();
  // Already newest-first from the API.
  const finished = scripts.filter((s) => s.video_status === "success");
  const inProgress = scripts.filter((s) => IN_PROGRESS_VIDEO_STATUSES.includes(s.video_status));
  historyListEl.innerHTML = "";
  historyEmptyState.hidden = finished.length > 0 || inProgress.length > 0;

  historyPollUnsubscribes.forEach((unsubscribe) => unsubscribe());
  historyPollUnsubscribes = [];

  // Generations keep running on KIE's servers (and the app's own background
  // poller keeps checking on them) even with no browser open at all -- this
  // section is just so there's somewhere in the UI to see that, instead of
  // navigating back to a blank Generator form and wondering whether
  // anything happened. Watching each one here refreshes History the moment
  // it finishes, without needing to flip tabs to notice.
  if (inProgress.length) {
    const section = document.createElement("div");
    section.className = "history-date-group";
    const heading = document.createElement("h3");
    heading.className = "history-date-heading";
    heading.textContent = "In progress";
    const cardsEl = document.createElement("div");
    cardsEl.className = "history-date-cards";
    for (const script of inProgress) {
      cardsEl.appendChild(renderInProgressCard(script));
      historyPollUnsubscribes.push(onPollUpdate(script.id, () => loadHistory()));
      schedulePoll(script.id);
    }
    section.append(heading, cardsEl);
    historyListEl.appendChild(section);
  }

  // Grouped up front (rather than streamed) so each day's heading can show
  // that day's total cost, which requires knowing the whole group first.
  for (const group of groupByDate(finished)) {
    const groupEl = document.createElement("div");
    groupEl.className = "history-date-group";

    const heading = document.createElement("h3");
    heading.className = "history-date-heading";
    const headingLabel = document.createElement("span");
    headingLabel.textContent = formatDateHeading(group.scripts[0]);
    heading.appendChild(headingLabel);
    const dayBadge = buildDayCostBadge(group.scripts);
    if (dayBadge) heading.appendChild(dayBadge);

    const cardsEl = document.createElement("div");
    cardsEl.className = "history-date-cards";
    for (const script of group.scripts) {
      cardsEl.appendChild(renderHistoryCard(script));
    }

    groupEl.append(heading, cardsEl);
    historyListEl.appendChild(groupEl);
  }

  renderHistorySummary(finished);
}

// Pre-groups the newest-first list into per-day buckets (still newest-first,
// both across and within days), so each day's full cost total is known
// before that day's heading is built.
function groupByDate(finished) {
  const groups = [];
  let currentKey = null;
  let currentGroup = null;
  for (const script of finished) {
    const key = dateKey(script);
    if (key !== currentKey) {
      currentKey = key;
      currentGroup = { key, scripts: [] };
      groups.push(currentGroup);
    }
    currentGroup.scripts.push(script);
  }
  return groups;
}

function buildDayCostBadge(scripts) {
  const known = scripts.filter((s) => s.total_cost_usd !== null && s.total_cost_usd !== undefined);
  if (!known.length) return null;
  const total = known.reduce((sum, s) => sum + s.total_cost_usd, 0);
  const badge = document.createElement("span");
  badge.className = "history-date-cost";
  badge.textContent = `~${formatCost(total)}`;
  return badge;
}

function scriptDate(script) {
  // Same naive-UTC handling as formatDate: server timestamps have no offset.
  return new Date(script.created_at.endsWith("Z") ? script.created_at : `${script.created_at}Z`);
}

function dateKey(script) {
  const d = scriptDate(script);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function formatDateHeading(script) {
  return scriptDate(script).toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

// Doubles as this generation's ID on History cards: DD-MM-YY-HH-MM of when
// it was created, unique enough at a glance (down to the minute) without
// needing a separate generated name or UUID fragment.
function formatGenerationId(isoString) {
  const d = new Date(isoString.endsWith("Z") ? isoString : `${isoString}Z`);
  const pad = (n) => String(n).padStart(2, "0");
  const day = pad(d.getDate());
  const month = pad(d.getMonth() + 1);
  const year = pad(d.getFullYear() % 100);
  const hour = pad(d.getHours());
  const minute = pad(d.getMinutes());
  return `${day}-${month}-${year}-${hour}-${minute}`;
}

function costSummaryLine(label, group) {
  const known = group.filter((s) => s.total_cost_usd !== null && s.total_cost_usd !== undefined);
  if (!known.length) return `${label}: no cost data yet for ${group.length} video${group.length === 1 ? "" : "s"}`;
  const total = known.reduce((sum, s) => sum + s.total_cost_usd, 0);
  const coverage = known.length === group.length ? "" : ` (cost known for ${known.length} of ${group.length})`;
  return `${label}: ~${formatCost(total)} across ${group.length} video${group.length === 1 ? "" : "s"}${coverage}`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function renderHistorySummary(finished) {
  if (!finished.length) {
    historySummaryEl.hidden = true;
    return;
  }
  const now = new Date();
  const last7 = finished.filter((s) => now - scriptDate(s) <= 7 * DAY_MS);
  const last30 = finished.filter((s) => now - scriptDate(s) <= 30 * DAY_MS);

  historySummaryEl.hidden = false;
  historySummaryEl.innerHTML = "";
  const totalLine = document.createElement("p");
  totalLine.className = "history-summary-total";
  totalLine.textContent = costSummaryLine("Total", finished);
  const last30Line = document.createElement("p");
  last30Line.textContent = costSummaryLine("Last 30 days", last30);
  const last7Line = document.createElement("p");
  last7Line.textContent = costSummaryLine("Last 7 days", last7);
  historySummaryEl.append(totalLine, last30Line, last7Line);
}

function renderHistoryCard(script) {
  const card = document.createElement("div");
  card.className = "history-card";

  const video = document.createElement("video");
  video.controls = true;
  video.src = script.video_url;
  card.appendChild(video);

  // DD-MM-YY-HH-MM of when this generation was created -- its ID, unique and
  // simple, instead of the character/product name (which repeats across
  // cards whenever the same outfit gets generated more than once).
  const title = document.createElement("h3");
  title.className = "history-card-id";
  title.textContent = formatGenerationId(script.created_at);
  card.appendChild(title);

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

function formatVideoStatusLabel(status) {
  if (status === "generating") return "Generating…";
  return "Queued on KIE…"; // waiting / queuing
}

function renderInProgressCard(script) {
  const card = document.createElement("div");
  card.className = "history-card history-card-pending";

  const status = document.createElement("p");
  status.className = "history-card-status";
  const spinner = document.createElement("span");
  spinner.className = "sf-progress-spinner";
  status.append(spinner, document.createTextNode(formatVideoStatusLabel(script.video_status)));
  card.appendChild(status);

  const title = document.createElement("h3");
  title.className = "history-card-id";
  title.textContent = formatGenerationId(script.created_at);
  card.appendChild(title);

  const sub = document.createElement("p");
  sub.className = "history-card-sub";
  sub.textContent = `${script.character.name} × ${script.product.name}`;
  card.appendChild(sub);

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
  actions.appendChild(viewBtn);
  card.appendChild(actions);

  return card;
}

// The Generator is the app's home view, so show the form immediately rather
// than waiting for a tab click. Past generations live in History instead.
showScriptForm();

// Pick back up any generation still mid-flight from before this page load.
resumeInProgressPolls();

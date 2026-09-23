// Reuses `el` and `fileListFrom` from app.js (both files are loaded as classic
// scripts on the same page, so their top-level declarations share one scope).

const JOBS_API_BASE = "/api/jobs";
const CHARACTERS_API_BASE = "/api/characters";

const jobListView = el("job-list-view");
const jobFormView = el("job-form-view");
const jobDetailView = el("job-detail-view");
const jobListEl = el("job-list");
const jobEmptyState = el("job-empty-state");
const jobForm = el("job-form");
const jobFormError = el("job-form-error");
const jobCharacterSelect = el("jf-character");
const jobSourceUrlInput = el("jf-source-url");
const jobManualImagesInput = el("jf-manual-images");
const jobImagesDropzone = el("job-images-dropzone");
const jobSubmitBtn = el("job-submit-btn");

const METHOD_LABELS = {
  structured_data: "found via the page's structured product data",
  html_scrape: "found by scanning the page's HTML",
  headless_browser: "found by rendering the page in a browser",
  manual_upload: "manually uploaded photos",
};

// ---------- Tabs ----------

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-action").forEach((btn) => {
    btn.hidden = btn.dataset.tab !== tab;
  });
  el("characters-tab").hidden = tab !== "characters";
  el("products-tab").hidden = tab !== "products";
  if (tab === "products") {
    showJobList();
  }
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ---------- View switching ----------

function showJobList() {
  jobFormView.hidden = true;
  jobDetailView.hidden = true;
  jobListView.hidden = false;
  loadJobs();
}

function showJobForm() {
  jobListView.hidden = true;
  jobDetailView.hidden = true;
  jobFormView.hidden = false;
  resetJobForm();
  loadCharacterOptions();
}

function showJobDetail(job) {
  jobListView.hidden = true;
  jobFormView.hidden = true;
  jobDetailView.hidden = false;
  renderJobDetail(job);
}

el("new-job-btn").addEventListener("click", showJobForm);
el("job-empty-new-btn").addEventListener("click", showJobForm);
el("job-cancel-btn").addEventListener("click", showJobList);
el("job-detail-back-btn").addEventListener("click", showJobList);

// ---------- List ----------

async function loadJobs() {
  const res = await fetch(JOBS_API_BASE);
  const jobs = await res.json();
  jobListEl.innerHTML = "";
  jobEmptyState.hidden = jobs.length > 0;
  for (const job of jobs) {
    jobListEl.appendChild(renderJobCard(job));
  }
}

function renderJobCard(job) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.addEventListener("click", () => showJobDetail(job));

  const thumb = document.createElement("div");
  if (job.fetch_status === "success" && job.images.length) {
    thumb.className = "thumb";
    const img = document.createElement("img");
    img.src = job.images[0].url;
    thumb.appendChild(img);
  } else if (job.fetch_status === "failed") {
    thumb.className = "thumb failed";
    thumb.textContent = "!";
  } else {
    thumb.className = "thumb";
    thumb.textContent = "No photo";
  }

  const body = document.createElement("div");
  body.className = "job-card-body";

  const title = document.createElement("h3");
  title.textContent = job.product_title || job.character.name;

  const url = document.createElement("p");
  url.className = "job-card-url";
  url.textContent = `${job.source_url || "Manual upload"} · ${formatDate(job.created_at)}`;

  const badge = document.createElement("span");
  if (job.fetch_status === "failed") {
    badge.className = "badge badge-fail";
    badge.textContent = "Failed";
  } else if (job.stage === "approved") {
    badge.className = "badge badge-ok";
    badge.textContent = "Approved";
  } else if (job.stage === "blocked") {
    badge.className = "badge badge-fail";
    badge.textContent = "Blocked";
  } else if (job.stage === "prompt_generated") {
    badge.className = "badge badge-muted";
    badge.textContent = "Draft prompt";
  } else {
    badge.className = "badge badge-ok";
    badge.textContent = "Fetched";
  }

  body.append(title, url, badge);
  card.append(thumb, body);
  return card;
}

function formatDate(isoString) {
  // Server timestamps are naive UTC (no offset in the string) -- append "Z" so the
  // browser doesn't misinterpret them as local time.
  const d = new Date(isoString.endsWith("Z") ? isoString : `${isoString}Z`);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

// ---------- Form ----------

async function loadCharacterOptions() {
  const res = await fetch(CHARACTERS_API_BASE);
  const characters = await res.json();
  jobCharacterSelect.innerHTML = "";
  if (!characters.length) {
    const opt = document.createElement("option");
    opt.textContent = "Create a character first";
    opt.disabled = true;
    opt.selected = true;
    jobCharacterSelect.appendChild(opt);
    jobSubmitBtn.disabled = true;
    return;
  }
  jobSubmitBtn.disabled = false;
  for (const c of characters) {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = c.name;
    jobCharacterSelect.appendChild(opt);
  }
}

function resetJobForm() {
  jobForm.reset();
  jobFormError.hidden = true;
  el("job-images-pending").innerHTML = "";
  jobManualImagesInput.value = "";
}

function renderJobPendingFiles() {
  const container = el("job-images-pending");
  container.innerHTML = "";
  const files = Array.from(jobManualImagesInput.files);
  files.forEach((file, idx) => {
    const thumb = document.createElement("div");
    thumb.className = "image-thumb";

    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-btn";
    removeBtn.textContent = "×";
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const remaining = files.filter((_, i) => i !== idx);
      jobManualImagesInput.files = fileListFrom(remaining);
      renderJobPendingFiles();
    });

    thumb.append(img, removeBtn);
    container.appendChild(thumb);
  });
}

jobImagesDropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  jobImagesDropzone.classList.add("dragover");
});
jobImagesDropzone.addEventListener("dragleave", (e) => {
  if (e.target === jobImagesDropzone) jobImagesDropzone.classList.remove("dragover");
});
jobImagesDropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  jobImagesDropzone.classList.remove("dragover");
  const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
  if (!dropped.length) return;
  const merged = Array.from(jobManualImagesInput.files).concat(dropped);
  jobManualImagesInput.files = fileListFrom(merged);
  renderJobPendingFiles();
});
jobManualImagesInput.addEventListener("change", renderJobPendingFiles);

jobForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  jobFormError.hidden = true;

  const characterId = jobCharacterSelect.value;
  const sourceUrl = jobSourceUrlInput.value.trim();
  const hasManualImages = jobManualImagesInput.files.length > 0;

  if (!characterId) {
    showJobFormError("Choose a character.");
    return;
  }
  if (!sourceUrl && !hasManualImages) {
    showJobFormError("Provide a product URL, or attach product photos manually.");
    return;
  }

  const fd = new FormData();
  fd.append("character_id", characterId);
  fd.append("source_url", sourceUrl);
  for (const file of jobManualImagesInput.files) fd.append("manual_images", file);

  jobSubmitBtn.disabled = true;
  jobSubmitBtn.textContent = sourceUrl ? "Fetching…" : "Saving…";
  try {
    const res = await fetch(JOBS_API_BASE, { method: "POST", body: fd });
    if (!res.ok) {
      showJobFormError(await extractJobError(res));
      return;
    }
    const job = await res.json();
    showJobDetail(job);
  } finally {
    jobSubmitBtn.disabled = false;
    jobSubmitBtn.textContent = "Fetch Product";
  }
});

async function extractJobError(res) {
  try {
    const body = await res.json();
    return body.detail || "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

function showJobFormError(message) {
  jobFormError.textContent = message;
  jobFormError.hidden = false;
}

// ---------- Detail ----------

let currentJob = null;

function renderJobDetail(job) {
  currentJob = job;
  el("job-detail-eyebrow").textContent = job.character.name;
  el("job-detail-title").textContent = job.product_title || (job.source_url || "Manually uploaded product");
  el("job-detail-date").textContent = "Fetched " + formatDate(job.created_at);

  const rerunBtn = el("job-rerun-btn");
  rerunBtn.hidden = !job.source_url;

  const banner = el("job-detail-banner");
  if (job.fetch_status === "failed") {
    banner.className = "banner banner-error";
    banner.textContent = job.fetch_error;
    banner.hidden = false;
  } else if (job.fetch_error) {
    // success, but with a note (e.g. URL failed, fell back to manual photos)
    banner.className = "banner banner-info";
    banner.textContent = job.fetch_error;
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }

  const methodBadge = el("job-detail-method");
  if (job.fetch_method_used) {
    methodBadge.textContent = METHOD_LABELS[job.fetch_method_used] || job.fetch_method_used;
    methodBadge.hidden = false;
  } else {
    methodBadge.hidden = true;
  }

  const imagesContainer = el("job-detail-images");
  imagesContainer.innerHTML = "";
  if (job.images.length) {
    for (const img of job.images) {
      const thumb = document.createElement("div");
      thumb.className = "image-thumb";
      const imgTag = document.createElement("img");
      imgTag.src = img.url;
      thumb.appendChild(imgTag);
      imagesContainer.appendChild(thumb);
    }
  } else {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "No photos were fetched for this product.";
    imagesContainer.appendChild(p);
  }

  const infoSection = el("job-detail-product-info");
  const descriptionEl = el("job-detail-description");
  if (job.product_description) {
    descriptionEl.textContent = job.product_description;
    infoSection.hidden = false;
  } else {
    infoSection.hidden = true;
  }

  renderPromptSection(job);
}

const STAGE_LABELS = {
  blocked: "Blocked",
  prompt_generated: "Draft — needs review",
  approved: "Approved",
};

const CHECK_ICONS = { pass: "✓", fail: "✕", manual: "!" };

function renderPromptSection(job) {
  const generateSection = el("job-detail-generate-section");
  const promptSection = el("job-detail-prompt-section");

  if (job.stage === "fetched") {
    generateSection.hidden = false;
    promptSection.hidden = true;
    return;
  }

  generateSection.hidden = true;
  promptSection.hidden = false;

  const stageBadge = el("job-detail-stage-badge");
  stageBadge.textContent = STAGE_LABELS[job.stage] || job.stage;
  stageBadge.className = "badge " + (job.stage === "blocked" ? "badge-fail" : job.stage === "approved" ? "badge-ok" : "badge-muted");

  const checklist = el("job-detail-checklist");
  checklist.innerHTML = "";
  for (const check of job.sop_check_results) {
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

  const promptTextarea = el("job-detail-prompt-text");
  const approveBtn = el("job-approve-btn");

  if (job.stage === "blocked") {
    promptTextarea.hidden = true;
    approveBtn.hidden = true;
  } else {
    promptTextarea.hidden = false;
    promptTextarea.value = job.generated_prompt;
    approveBtn.hidden = false;
    approveBtn.textContent = job.stage === "approved" ? "Approved ✓" : "Approve Prompt";
    approveBtn.disabled = job.stage === "approved";
  }
}

async function runGenerate(button) {
  if (!currentJob) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Generating…";
  try {
    const res = await fetch(`${JOBS_API_BASE}/${currentJob.id}/generate`, { method: "POST" });
    if (!res.ok) {
      alert(await extractJobError(res));
      return;
    }
    const job = await res.json();
    renderJobDetail(job);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

el("job-generate-first-btn").addEventListener("click", (e) => runGenerate(e.currentTarget));
el("job-generate-btn").addEventListener("click", (e) => {
  if (!confirm("Regenerate this prompt? Any edits you've made will be discarded.")) return;
  runGenerate(e.currentTarget);
});

el("job-approve-btn").addEventListener("click", async () => {
  if (!currentJob) return;
  const btn = el("job-approve-btn");
  const promptText = el("job-detail-prompt-text").value;
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const fd = new FormData();
    fd.append("edited_prompt", promptText);
    const res = await fetch(`${JOBS_API_BASE}/${currentJob.id}/approve`, { method: "PUT", body: fd });
    if (!res.ok) {
      alert(await extractJobError(res));
      return;
    }
    const job = await res.json();
    renderJobDetail(job);
  } finally {
    btn.disabled = false;
  }
});

el("job-delete-btn").addEventListener("click", async () => {
  if (!currentJob) return;
  if (!confirm("Delete this product? This cannot be undone.")) return;
  const res = await fetch(`${JOBS_API_BASE}/${currentJob.id}`, { method: "DELETE" });
  if (res.ok) {
    showJobList();
  } else {
    alert("Failed to delete product.");
  }
});

el("job-rerun-btn").addEventListener("click", async () => {
  if (!currentJob || !currentJob.source_url) return;
  if (!confirm("Re-fetch this product from its URL as a new entry? The current one is kept as-is.")) return;
  const btn = el("job-rerun-btn");
  btn.disabled = true;
  btn.textContent = "Re-running…";
  try {
    const fd = new FormData();
    fd.append("character_id", currentJob.character_id);
    fd.append("source_url", currentJob.source_url);
    const res = await fetch(JOBS_API_BASE, { method: "POST", body: fd });
    if (!res.ok) {
      alert(await extractJobError(res));
      return;
    }
    const job = await res.json();
    showJobDetail(job);
  } finally {
    btn.disabled = false;
    btn.textContent = "Re-run…";
  }
});

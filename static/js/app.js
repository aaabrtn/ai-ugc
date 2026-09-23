const API_BASE = "/api/characters";

const el = (id) => document.getElementById(id);

const listView = el("character-list-view");
const formView = el("character-form-view");
const listEl = el("character-list");
const emptyState = el("empty-state");
const form = el("character-form");
const formEyebrow = el("form-eyebrow");
const formError = el("form-error");
const deleteBtn = el("delete-btn");
const unlockSettingBtn = el("unlock-setting-btn");
const settingLockBadge = el("setting-lock-badge");

const identityDropzone = el("identity-dropzone");
const identityInput = el("f-identity-images");
const settingDropzone = el("setting-dropzone");
const settingInput = el("f-setting-images");

let currentCharacter = null; // full character object when editing, null when creating
let settingUnlocked = false; // whether the locked setting dropzone is currently editable
let removedImageIds = new Set();

// ---------- View switching ----------

function showList() {
  formView.hidden = true;
  listView.hidden = false;
  loadCharacters();
}

function showForm() {
  listView.hidden = true;
  formView.hidden = false;
}

// ---------- List ----------

async function loadCharacters() {
  const res = await fetch(API_BASE);
  const characters = await res.json();
  listEl.innerHTML = "";
  emptyState.hidden = characters.length > 0;
  for (const c of characters) {
    listEl.appendChild(renderCard(c));
  }
}

function renderCard(c) {
  const card = document.createElement("div");
  card.className = "character-card";
  card.addEventListener("click", () => openEditForm(c.id));

  const thumb = document.createElement("div");
  thumb.className = "thumb";
  if (c.identity_images.length) {
    const img = document.createElement("img");
    img.src = c.identity_images[0].url;
    thumb.appendChild(img);
  } else {
    thumb.textContent = "No photo";
  }

  const name = document.createElement("h3");
  name.textContent = c.name;

  const excerpt = document.createElement("p");
  excerpt.className = "char-excerpt";
  excerpt.textContent = c.characteristics || "";

  card.append(thumb, name, excerpt);
  return card;
}

// ---------- Drag-and-drop file inputs ----------

function fileListFrom(files) {
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(f);
  return dt.files;
}

function pendingContainerFor(inputEl) {
  return inputEl === identityInput ? el("identity-pending") : el("setting-pending");
}

function renderPendingFiles(inputEl) {
  const container = pendingContainerFor(inputEl);
  container.innerHTML = "";
  const files = Array.from(inputEl.files);
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
      inputEl.files = fileListFrom(remaining);
      renderPendingFiles(inputEl);
    });

    thumb.append(img, removeBtn);
    container.appendChild(thumb);
  });
}

function setupDropzone(dropzoneEl, inputEl) {
  dropzoneEl.addEventListener("dragover", (e) => {
    if (inputEl.disabled) return;
    e.preventDefault();
    dropzoneEl.classList.add("dragover");
  });
  dropzoneEl.addEventListener("dragleave", (e) => {
    if (e.target === dropzoneEl) dropzoneEl.classList.remove("dragover");
  });
  dropzoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzoneEl.classList.remove("dragover");
    if (inputEl.disabled) return;
    const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
    if (!dropped.length) return;
    const merged = Array.from(inputEl.files).concat(dropped);
    inputEl.files = fileListFrom(merged);
    renderPendingFiles(inputEl);
  });
  inputEl.addEventListener("change", () => renderPendingFiles(inputEl));
}

setupDropzone(identityDropzone, identityInput);
setupDropzone(settingDropzone, settingInput);

function renderExistingImages(containerId, images, dropzoneEl) {
  const container = el(containerId);
  container.innerHTML = "";
  for (const img of images) {
    const thumb = document.createElement("div");
    thumb.className = "image-thumb";
    thumb.dataset.imageId = img.id;

    const imgTag = document.createElement("img");
    imgTag.src = img.url;
    imgTag.alt = img.original_filename;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-btn";
    removeBtn.textContent = "×";
    removeBtn.title = "Remove image";
    removeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (removedImageIds.has(img.id)) {
        removedImageIds.delete(img.id);
        thumb.classList.remove("marked-removed");
      } else {
        removedImageIds.add(img.id);
        thumb.classList.add("marked-removed");
      }
    });

    thumb.append(imgTag, removeBtn);
    container.appendChild(thumb);
  }
}

// ---------- Form ----------

function resetForm() {
  form.reset();
  el("character-id").value = "";
  formEyebrow.textContent = "New Character";
  deleteBtn.hidden = true;
  formError.hidden = true;
  currentCharacter = null;
  settingUnlocked = true; // new characters: setting dropzone starts editable
  removedImageIds = new Set();

  el("identity-images-existing").innerHTML = "";
  el("identity-pending").innerHTML = "";
  el("setting-images-existing").innerHTML = "";
  el("setting-pending").innerHTML = "";
  identityInput.value = "";
  settingInput.value = "";

  settingLockBadge.hidden = true;
  unlockSettingBtn.hidden = true;
  setSettingLocked(false);
}

function setSettingLocked(locked) {
  settingInput.disabled = locked;
  settingDropzone.classList.toggle("locked", locked);
}

function openNewForm() {
  resetForm();
  showForm();
}

async function openEditForm(id) {
  const res = await fetch(`${API_BASE}/${id}`);
  if (!res.ok) {
    alert("Could not load character.");
    return;
  }
  const c = await res.json();
  resetForm();
  currentCharacter = c;

  el("character-id").value = c.id;
  formEyebrow.textContent = "Editing";
  deleteBtn.hidden = false;

  el("f-name").value = c.name;
  el("f-characteristics").value = c.characteristics;

  renderExistingImages("identity-images-existing", c.identity_images, identityDropzone);
  renderExistingImages("setting-images-existing", c.setting_images, settingDropzone);

  if (c.setting_locked) {
    settingLockBadge.hidden = false;
    unlockSettingBtn.hidden = false;
    settingUnlocked = false;
    setSettingLocked(true);
  } else {
    settingUnlocked = true;
    setSettingLocked(false);
  }

  showForm();
}

unlockSettingBtn.addEventListener("click", () => {
  const confirmed = confirm(
    "This will change the look of all future videos with this character. Continue editing the locked setting?"
  );
  if (confirmed) {
    settingUnlocked = true;
    setSettingLocked(false);
  }
});

el("new-character-btn").addEventListener("click", openNewForm);
el("empty-new-btn").addEventListener("click", openNewForm);
el("cancel-btn").addEventListener("click", showList);

deleteBtn.addEventListener("click", async () => {
  if (!currentCharacter) return;
  if (!confirm(`Delete character "${currentCharacter.name}"? This cannot be undone.`)) return;
  const res = await fetch(`${API_BASE}/${currentCharacter.id}`, { method: "DELETE" });
  if (res.ok) {
    showList();
  } else {
    alert("Failed to delete character.");
  }
});

function activeImageCount(existingContainerId, inputEl) {
  const remaining = Array.from(el(existingContainerId).querySelectorAll(".image-thumb")).filter(
    (t) => !removedImageIds.has(t.dataset.imageId)
  ).length;
  return remaining + inputEl.files.length;
}

function buildFormData() {
  const fd = new FormData();
  fd.append("name", el("f-name").value.trim());
  fd.append("characteristics", el("f-characteristics").value);
  for (const file of identityInput.files) fd.append("identity_images", file);
  for (const file of settingInput.files) fd.append("setting_images", file);
  return fd;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;

  const name = el("f-name").value.trim();
  if (!name) {
    showFormError("Name is required.");
    return;
  }
  if (activeImageCount("identity-images-existing", identityInput) < 1) {
    showFormError("At least one character reference photo is required.");
    return;
  }
  if (activeImageCount("setting-images-existing", settingInput) < 1) {
    showFormError("At least one settings reference photo is required.");
    return;
  }

  const fd = buildFormData();
  let url = API_BASE;
  let method = "POST";

  if (currentCharacter) {
    url = `${API_BASE}/${currentCharacter.id}`;
    method = "PUT";
    fd.append("confirm_setting_change", settingUnlocked ? "true" : "false");
    fd.append("remove_image_ids", Array.from(removedImageIds).join(","));
  }

  const res = await fetch(url, { method, body: fd });

  if (res.status === 409) {
    const body = await res.json();
    const confirmed = confirm(body.detail + "\n\nProceed with this change?");
    if (confirmed) {
      fd.set("confirm_setting_change", "true");
      settingUnlocked = true;
      const retry = await fetch(url, { method, body: fd });
      if (!retry.ok) {
        showFormError(await extractError(retry));
        return;
      }
      showList();
    }
    return;
  }

  if (!res.ok) {
    showFormError(await extractError(res));
    return;
  }

  showList();
});

async function extractError(res) {
  try {
    const body = await res.json();
    return body.detail || "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

function showFormError(message) {
  formError.textContent = message;
  formError.hidden = false;
}

loadCharacters();

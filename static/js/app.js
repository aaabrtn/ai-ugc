const API_BASE = "/api/characters";

const el = (id) => document.getElementById(id);

const listView = el("character-list-view");
const formView = el("character-form-view");
const listEl = el("character-list");
const emptyState = el("empty-state");
const form = el("character-form");
const formTitle = el("form-title");
const formError = el("form-error");
const deleteBtn = el("delete-btn");
const unlockSettingBtn = el("unlock-setting-btn");
const settingLockBadge = el("setting-lock-badge");
const settingDescriptionInput = el("f-setting-description");
const settingImagesInput = el("f-setting-images");

let currentCharacter = null; // full character object when editing, null when creating
let settingUnlocked = false; // whether the locked setting fields are currently editable
let removedImageIds = new Set();

function showList() {
  formView.hidden = true;
  listView.hidden = false;
  loadCharacters();
}

function showForm() {
  listView.hidden = true;
  formView.hidden = false;
}

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
    img.style.width = "100%";
    img.style.height = "100%";
    img.style.objectFit = "cover";
    thumb.appendChild(img);
  } else {
    thumb.textContent = "No image";
  }

  const name = document.createElement("h3");
  name.textContent = c.name;

  const badge = document.createElement("span");
  badge.className = "badge " + (c.consent_status === "cleared" ? "badge-cleared" : "badge-internal");
  badge.textContent = c.consent_status === "cleared" ? "Cleared" : "Internal only";

  card.append(thumb, name, badge);
  return card;
}

function resetForm() {
  form.reset();
  el("character-id").value = "";
  formTitle.textContent = "New Character";
  deleteBtn.hidden = true;
  formError.hidden = true;
  currentCharacter = null;
  settingUnlocked = true; // new characters: setting fields start editable
  removedImageIds = new Set();
  el("identity-images-existing").innerHTML = "";
  el("setting-images-existing").innerHTML = "";
  settingLockBadge.hidden = true;
  unlockSettingBtn.hidden = true;
  setSettingFieldsDisabled(false);
}

function setSettingFieldsDisabled(disabled) {
  settingDescriptionInput.disabled = disabled;
  settingImagesInput.disabled = disabled;
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
  formTitle.textContent = `Edit ${c.name}`;
  deleteBtn.hidden = false;

  el("f-name").value = c.name;
  el("f-consent-status").value = c.consent_status;
  el("f-face-shape").value = c.face_shape;
  el("f-hair-color").value = c.hair_color;
  el("f-hair-style").value = c.hair_style;
  el("f-hair-texture").value = c.hair_texture;
  el("f-skin-tone").value = c.skin_tone;
  el("f-eyes").value = c.eyes;
  el("f-build").value = c.build;
  el("f-signature-accessories").value = c.signature_accessories;
  el("f-tattoos").value = c.tattoos;
  el("f-default-expression").value = c.default_expression;
  el("f-characteristics-notes").value = c.characteristics_notes;
  el("f-setting-description").value = c.setting_description;
  el("f-movement-notes").value = c.movement_notes;

  renderExistingImages("identity-images-existing", c.identity_images);
  renderExistingImages("setting-images-existing", c.setting_images);

  if (c.setting_locked) {
    settingLockBadge.hidden = false;
    unlockSettingBtn.hidden = false;
    settingUnlocked = false;
    setSettingFieldsDisabled(true);
  } else {
    settingUnlocked = true;
    setSettingFieldsDisabled(false);
  }

  showForm();
}

function renderExistingImages(containerId, images) {
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
    removeBtn.addEventListener("click", () => {
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

unlockSettingBtn.addEventListener("click", () => {
  const confirmed = confirm(
    "This will change the look of all future videos with this character. Continue editing the locked setting?"
  );
  if (confirmed) {
    settingUnlocked = true;
    setSettingFieldsDisabled(false);
  }
});

el("new-character-btn").addEventListener("click", openNewForm);
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

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  formError.hidden = true;

  const name = el("f-name").value.trim();
  if (!name) {
    showFormError("Name is required.");
    return;
  }
  if (!currentCharacter && !settingDescriptionInput.value.trim()) {
    showFormError("Setting description is required for a new character.");
    return;
  }

  const fd = new FormData();
  fd.append("name", name);
  fd.append("consent_status", el("f-consent-status").value);
  fd.append("face_shape", el("f-face-shape").value);
  fd.append("hair_color", el("f-hair-color").value);
  fd.append("hair_style", el("f-hair-style").value);
  fd.append("hair_texture", el("f-hair-texture").value);
  fd.append("skin_tone", el("f-skin-tone").value);
  fd.append("eyes", el("f-eyes").value);
  fd.append("build", el("f-build").value);
  fd.append("signature_accessories", el("f-signature-accessories").value);
  fd.append("tattoos", el("f-tattoos").value);
  fd.append("default_expression", el("f-default-expression").value);
  fd.append("characteristics_notes", el("f-characteristics-notes").value);
  fd.append("setting_description", settingDescriptionInput.value);
  fd.append("movement_notes", el("f-movement-notes").value);

  for (const file of el("f-identity-images").files) {
    fd.append("identity_images", file);
  }
  for (const file of settingImagesInput.files) {
    fd.append("setting_images", file);
  }

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
      return;
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

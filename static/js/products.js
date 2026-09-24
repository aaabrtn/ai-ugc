// Reuses `el` and `fileListFrom` from app.js (all three JS files are loaded as
// classic scripts on the same page, so their top-level declarations share one
// scope). Defines `formatDate` and `switchTab`, reused by scripts.js.

const PRODUCTS_API_BASE = "/api/products";

const productListView = el("product-list-view");
const productFormView = el("product-form-view");
const productDetailView = el("product-detail-view");
const productListEl = el("product-list");
const productEmptyState = el("product-empty-state");
const productForm = el("product-form");
const productFormError = el("product-form-error");
const productSourceUrlInput = el("pf-source-url");
const productManualImagesInput = el("pf-manual-images");
const productFormDropzone = el("product-form-dropzone");
const productSubmitBtn = el("product-submit-btn");
const productDetailForm = el("product-detail-form");
const productDetailError = el("product-detail-error");
const pdAddImagesInput = el("pd-add-images");
const pdImagesDropzone = el("pd-images-dropzone");

const METHOD_LABELS = {
  structured_data: "found via the page's structured product data",
  html_scrape: "found by scanning the page's HTML",
  headless_browser: "found by rendering the page in a browser",
  manual_upload: "manually uploaded photos",
};

function formatDate(isoString) {
  // Server timestamps are naive UTC (no offset in the string) -- append "Z" so the
  // browser doesn't misinterpret them as local time.
  const d = new Date(isoString.endsWith("Z") ? isoString : `${isoString}Z`);
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

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
  el("scripts-tab").hidden = tab !== "scripts";
  el("history-tab").hidden = tab !== "history";
  if (tab === "characters") {
    loadCharacters();
  } else if (tab === "products") {
    showProductList();
  } else if (tab === "scripts") {
    showScriptForm();
  } else if (tab === "history") {
    loadHistory();
  }
  // Deliberately no stopPolling() here -- a video generating on KIE keeps
  // going regardless of which tab is open, so background status-checking
  // must too (see resumeInProgressPolls/schedulePoll in scripts.js).
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

// ---------- View switching ----------

function showProductList() {
  productFormView.hidden = true;
  productDetailView.hidden = true;
  productListView.hidden = false;
  loadProducts();
}

function showProductForm() {
  productListView.hidden = true;
  productDetailView.hidden = true;
  productFormView.hidden = false;
  resetProductForm();
}

function showProductDetail(product) {
  productListView.hidden = true;
  productFormView.hidden = true;
  productDetailView.hidden = false;
  renderProductDetail(product);
}

el("new-product-btn").addEventListener("click", showProductForm);
el("product-empty-new-btn").addEventListener("click", showProductForm);
el("product-form-cancel-btn").addEventListener("click", showProductList);
el("product-detail-back-btn").addEventListener("click", showProductList);

// ---------- List ----------

async function loadProducts() {
  const res = await fetch(PRODUCTS_API_BASE);
  const products = await res.json();
  productListEl.innerHTML = "";
  productEmptyState.hidden = products.length > 0;
  for (const product of products) {
    productListEl.appendChild(renderProductCard(product));
  }
}

function renderProductCard(product) {
  const card = document.createElement("div");
  card.className = "job-card";
  card.addEventListener("click", () => showProductDetail(product));

  const thumb = document.createElement("div");
  if (product.fetch_status === "success" && product.images.length) {
    thumb.className = "thumb";
    const img = document.createElement("img");
    img.src = product.images[0].url;
    thumb.appendChild(img);
  } else if (product.fetch_status === "failed") {
    thumb.className = "thumb failed";
    thumb.textContent = "!";
  } else {
    thumb.className = "thumb";
    thumb.textContent = "No photo";
  }

  const body = document.createElement("div");
  body.className = "job-card-body";

  const title = document.createElement("h3");
  title.textContent = product.name;

  const url = document.createElement("p");
  url.className = "job-card-url";
  url.textContent = `${product.source_url || "Manual upload"} · ${formatDate(product.created_at)}`;

  const badge = document.createElement("span");
  badge.className = "badge " + (product.fetch_status === "success" ? "badge-ok" : "badge-fail");
  badge.textContent = product.fetch_status === "success" ? "Fetched" : "Failed";

  body.append(title, url, badge);
  card.append(thumb, body);
  return card;
}

// ---------- Create form ----------

function resetProductForm() {
  productForm.reset();
  productFormError.hidden = true;
  el("product-form-pending").innerHTML = "";
  productManualImagesInput.value = "";
}

function renderProductFormPending() {
  const container = el("product-form-pending");
  container.innerHTML = "";
  const files = Array.from(productManualImagesInput.files);
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
      productManualImagesInput.files = fileListFrom(remaining);
      renderProductFormPending();
    });

    thumb.append(img, removeBtn);
    container.appendChild(thumb);
  });
}

productFormDropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  productFormDropzone.classList.add("dragover");
});
productFormDropzone.addEventListener("dragleave", (e) => {
  if (e.target === productFormDropzone) productFormDropzone.classList.remove("dragover");
});
productFormDropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  productFormDropzone.classList.remove("dragover");
  const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
  if (!dropped.length) return;
  const merged = Array.from(productManualImagesInput.files).concat(dropped);
  productManualImagesInput.files = fileListFrom(merged);
  renderProductFormPending();
});
productManualImagesInput.addEventListener("change", renderProductFormPending);

productForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  productFormError.hidden = true;

  const sourceUrl = productSourceUrlInput.value.trim();
  const hasManualImages = productManualImagesInput.files.length > 0;

  if (!sourceUrl && !hasManualImages) {
    showProductFormError("Provide a product URL, or attach product photos manually.");
    return;
  }

  const fd = new FormData();
  fd.append("source_url", sourceUrl);
  for (const file of productManualImagesInput.files) fd.append("manual_images", file);

  productSubmitBtn.disabled = true;
  productSubmitBtn.textContent = sourceUrl ? "Fetching…" : "Saving…";
  try {
    const res = await fetch(PRODUCTS_API_BASE, { method: "POST", body: fd });
    if (!res.ok) {
      showProductFormError(await extractProductError(res));
      return;
    }
    const product = await res.json();
    showProductDetail(product);
  } finally {
    productSubmitBtn.disabled = false;
    productSubmitBtn.textContent = "Fetch Product";
  }
});

async function extractProductError(res) {
  try {
    const body = await res.json();
    return body.detail || "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

function showProductFormError(message) {
  productFormError.textContent = message;
  productFormError.hidden = false;
}

// ---------- Detail / edit ----------

let currentProduct = null;

function renderProductDetail(product) {
  currentProduct = product;
  productDetailError.hidden = true;
  el("product-id").value = product.id;
  el("pd-name").value = product.name;
  el("pd-date").textContent = "Added " + formatDate(product.created_at);

  const banner = el("product-detail-banner");
  if (product.fetch_status === "failed") {
    banner.className = "banner banner-error";
    banner.textContent = product.fetch_error;
    banner.hidden = false;
  } else if (product.fetch_error) {
    banner.className = "banner banner-info";
    banner.textContent = product.fetch_error;
    banner.hidden = false;
  } else {
    banner.hidden = true;
  }

  const methodBadge = el("pd-method");
  if (product.fetch_method_used) {
    methodBadge.textContent = METHOD_LABELS[product.fetch_method_used] || product.fetch_method_used;
    methodBadge.hidden = false;
  } else {
    methodBadge.hidden = true;
  }

  renderProductImages(product);

  const descSection = el("pd-description-section");
  if (product.description) {
    el("pd-description").textContent = product.description;
    descSection.hidden = false;
  } else {
    descSection.hidden = true;
  }

  el("pd-additional-context").value = product.additional_context;

  const sourceSection = el("pd-source-section");
  if (product.source_url) {
    el("pd-source-url").textContent = product.source_url;
    sourceSection.hidden = false;
  } else {
    sourceSection.hidden = true;
  }
}

function renderProductImages(product) {
  const container = el("pd-images-existing");
  container.innerHTML = "";
  for (const img of product.images) {
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
    removeBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (product.images.length <= 1) {
        alert("Product must keep at least one photo.");
        return;
      }
      if (!confirm("Remove this photo?")) return;
      const res = await fetch(`${PRODUCTS_API_BASE}/${product.id}/images/${img.id}`, { method: "DELETE" });
      if (!res.ok) {
        alert(await extractProductError(res));
        return;
      }
      const updated = await res.json();
      currentProduct = updated;
      renderProductImages(updated);
    });

    thumb.append(imgTag, removeBtn);
    container.appendChild(thumb);
  }
}

pdAddImagesInput.addEventListener("change", async () => {
  if (!currentProduct || !pdAddImagesInput.files.length) return;
  const fd = new FormData();
  for (const file of pdAddImagesInput.files) fd.append("images", file);
  const res = await fetch(`${PRODUCTS_API_BASE}/${currentProduct.id}/images`, { method: "POST", body: fd });
  pdAddImagesInput.value = "";
  if (!res.ok) {
    alert(await extractProductError(res));
    return;
  }
  const updated = await res.json();
  currentProduct = updated;
  renderProductImages(updated);
});

pdImagesDropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  pdImagesDropzone.classList.add("dragover");
});
pdImagesDropzone.addEventListener("dragleave", (e) => {
  if (e.target === pdImagesDropzone) pdImagesDropzone.classList.remove("dragover");
});
pdImagesDropzone.addEventListener("drop", async (e) => {
  e.preventDefault();
  pdImagesDropzone.classList.remove("dragover");
  if (!currentProduct) return;
  const dropped = Array.from(e.dataTransfer.files).filter((f) => f.type.startsWith("image/"));
  if (!dropped.length) return;
  const fd = new FormData();
  for (const file of dropped) fd.append("images", file);
  const res = await fetch(`${PRODUCTS_API_BASE}/${currentProduct.id}/images`, { method: "POST", body: fd });
  if (!res.ok) {
    alert(await extractProductError(res));
    return;
  }
  const updated = await res.json();
  currentProduct = updated;
  renderProductImages(updated);
});

productDetailForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentProduct) return;
  productDetailError.hidden = true;

  const name = el("pd-name").value.trim();
  if (!name) {
    productDetailError.textContent = "Name is required.";
    productDetailError.hidden = false;
    return;
  }

  const fd = new FormData();
  fd.append("name", name);
  fd.append("additional_context", el("pd-additional-context").value);

  const res = await fetch(`${PRODUCTS_API_BASE}/${currentProduct.id}`, { method: "PUT", body: fd });
  if (!res.ok) {
    productDetailError.textContent = await extractProductError(res);
    productDetailError.hidden = false;
    return;
  }
  showProductList();
});

el("product-delete-btn").addEventListener("click", async () => {
  if (!currentProduct) return;
  if (!confirm(`Delete product "${currentProduct.name}"? This cannot be undone.`)) return;
  const res = await fetch(`${PRODUCTS_API_BASE}/${currentProduct.id}`, { method: "DELETE" });
  if (res.ok) {
    showProductList();
  } else {
    alert("Failed to delete product.");
  }
});

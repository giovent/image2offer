const fileInput = document.getElementById("file-input");
const dropZone = document.getElementById("drop-zone");
const dropLabel = document.getElementById("drop-label");
const runBtn = document.getElementById("run-btn");
const loadExampleBtn = document.getElementById("load-example-btn");
const traceList = document.getElementById("trace-list");
const statusText = document.getElementById("status-text");
const wipIndicator = document.getElementById("wip-indicator");
const offerCountryInput = document.getElementById("offer-country");
const previewPanel = document.getElementById("preview-panel");
const selectedPreview = document.getElementById("selected-preview");
const recentResultsContainer = document.getElementById("recent-results");

let selectedFile = null;
let activeEventSource = null;
let selectedPreviewUrl = null;
const recentResults = [];
const MAX_RECENT_RESULTS = 20;

function formatTimestamp(isoTimestamp) {
  return new Date(isoTimestamp).toLocaleString();
}

function formatUnitPriceNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Number(value.toFixed(3)).toString();
}

function deriveUnitPriceFromFirstOffer(result) {
  const firstOffer = Array.isArray(result) ? result[0] : null;
  if (!firstOffer || typeof firstOffer !== "object") {
    return null;
  }

  const directPricePerQuantity = firstOffer.prices_per_quantities?.[0];
  const directUnit = firstOffer.units?.[0];
  const directValue = formatUnitPriceNumber(directPricePerQuantity);
  if (directValue && typeof directUnit === "string" && directUnit.trim()) {
    return `${directValue} ${directUnit.trim()}`;
  }

  const offerPrice = firstOffer.offer_price;
  const offerCurrency = typeof firstOffer.offer_currency === "string" ? firstOffer.offer_currency.trim() : "";
  const firstProduct = Array.isArray(firstOffer.offer_products) ? firstOffer.offer_products[0] : null;
  const quantities = Array.isArray(firstProduct?.quantities) ? firstProduct.quantities : [];
  const units = Array.isArray(firstProduct?.units) ? firstProduct.units : [];
  const quantity = quantities[0];
  const unit = units[0];
  if (
    typeof offerPrice !== "number" ||
    !Number.isFinite(offerPrice) ||
    quantities.length !== 1 ||
    units.length !== 1 ||
    typeof quantity !== "number" ||
    !Number.isFinite(quantity) ||
    quantity <= 0 ||
    typeof unit !== "string" ||
    !unit.trim() ||
    !offerCurrency
  ) {
    return null;
  }

  const derivedValue = formatUnitPriceNumber(offerPrice / quantity);
  if (!derivedValue) {
    return null;
  }
  return `${derivedValue} ${offerCurrency}/${unit.trim()}`;
}

function parseCountryFromExampleFilename(filename) {
  const stem = (filename || "").replace(/\.[^.]+$/, "");
  const parts = stem.split("_");
  return parts[2]?.trim()?.toLowerCase() || "unknown";
}

function addTraceLine(text) {
  const item = document.createElement("li");
  item.textContent = text;
  traceList.appendChild(item);
  traceList.scrollTop = traceList.scrollHeight;
}

function resetOutput() {
  traceList.innerHTML = "";
}

function setWorking(isWorking) {
  runBtn.disabled = isWorking;
  loadExampleBtn.disabled = isWorking;
  wipIndicator.classList.toggle("hidden", !isWorking);
}

function revokeSelectedPreview() {
  if (!selectedPreviewUrl) {
    return;
  }
  URL.revokeObjectURL(selectedPreviewUrl);
  selectedPreviewUrl = null;
}

function setSelectedFile(file) {
  selectedFile = file;
  dropLabel.textContent = file
    ? `Selected: ${file.name || "clipboard-image"} (${Math.round(file.size / 1024)} KB)`
    : "Drop image here, click to upload, or paste from clipboard";

  revokeSelectedPreview();
  if (file) {
    selectedPreviewUrl = URL.createObjectURL(file);
    selectedPreview.src = selectedPreviewUrl;
    previewPanel.classList.remove("hidden");
  } else {
    selectedPreview.removeAttribute("src");
    previewPanel.classList.add("hidden");
  }
}

function renderRecentResults() {
  recentResultsContainer.innerHTML = "";
  if (recentResults.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-history";
    empty.textContent = "No processed images yet.";
    recentResultsContainer.appendChild(empty);
    return;
  }

  for (const item of recentResults) {
    const row = document.createElement("article");
    row.className = "history-item";

    const imageWrap = document.createElement("div");
    imageWrap.className = "history-image-wrap";
    const image = document.createElement("img");
    image.className = "history-image";
    image.src = item.imageUrl;
    image.alt = `Preview for ${item.fileName}`;
    imageWrap.appendChild(image);

    const content = document.createElement("div");
    content.className = "history-content";

    const meta = document.createElement("div");
    meta.className = "history-meta";

    const fileName = document.createElement("strong");
    fileName.textContent = item.fileName;

    const details = document.createElement("span");
    details.textContent = `${formatTimestamp(item.createdAt)} \u00b7 country: ${item.offerCountry}`;

    const badge = document.createElement("span");
    badge.className = `history-status ${item.status}`;
    badge.textContent = item.status;

    meta.append(fileName, details, badge);

    const unitPriceText = item.status === "success" ? deriveUnitPriceFromFirstOffer(item.result) : null;
    const unitPriceBox = document.createElement("div");
    if (unitPriceText) {
      unitPriceBox.className = "history-unit-price";
      unitPriceBox.textContent = unitPriceText;
    }

    const payload = document.createElement("pre");
    payload.className = "history-json";
    payload.textContent = item.status === "success"
      ? JSON.stringify(item.result, null, 2)
      : JSON.stringify({ error: item.error || "Unknown error" }, null, 2);

    if (unitPriceText) {
      content.append(meta, unitPriceBox, payload);
    } else {
      content.append(meta, payload);
    }
    row.append(imageWrap, content);
    recentResultsContainer.appendChild(row);
  }
}

function addRecentResult(record) {
  recentResults.unshift(record);
  while (recentResults.length > MAX_RECENT_RESULTS) {
    const removed = recentResults.pop();
    if (removed?.imageUrl) {
      URL.revokeObjectURL(removed.imageUrl);
    }
  }
  renderRecentResults();
}

async function startJob() {
  if (!selectedFile) {
    statusText.textContent = "Please select an image first.";
    return;
  }

  if (activeEventSource) {
    activeEventSource.close();
  }

  resetOutput();
  setWorking(true);
  statusText.textContent = "Submitting image...";

  const offerCountry = offerCountryInput.value.trim() || "unknown";
  const submittedImageUrl = URL.createObjectURL(selectedFile);
  const submittedFileName = selectedFile.name || "clipboard-image";
  let finalized = false;
  let latestResult = null;

  const form = new FormData();
  form.append("image", selectedFile);
  form.append("offer_country", offerCountry);

  try {
    const createRes = await fetch("/api/jobs", {
      method: "POST",
      body: form,
    });
    if (!createRes.ok) {
      const err = await createRes.json();
      throw new Error(err.detail || "Could not create job.");
    }
    const { job_id: jobId } = await createRes.json();
    statusText.textContent = "Job started.";
    addTraceLine(`[Job ${jobId}] Waiting for events...`);

    activeEventSource = new EventSource(`/api/jobs/${jobId}/events`);

    activeEventSource.addEventListener("status", (event) => {
      const data = JSON.parse(event.data);
      statusText.textContent = `${data.status}: ${data.message}`;
      addTraceLine(`[Status] ${data.message}`);
      if (!finalized && (data.status === "success" || data.status === "error")) {
        addRecentResult({
          fileName: submittedFileName,
          imageUrl: submittedImageUrl,
          createdAt: new Date().toISOString(),
          offerCountry,
          status: data.status,
          result: latestResult,
          error: data.status === "error" ? data.message : null,
        });
        finalized = true;
      }
      if (data.status === "success" || data.status === "error") {
        setWorking(false);
        activeEventSource?.close();
      }
    });

    activeEventSource.addEventListener("trace", (event) => {
      const data = JSON.parse(event.data);
      addTraceLine(data.message);
    });

    activeEventSource.addEventListener("result", (event) => {
      const data = JSON.parse(event.data);
      latestResult = data.result;
      addTraceLine("[Result] Final JSON received.");
    });

    activeEventSource.addEventListener("error", (event) => {
      if (event?.data) {
        const data = JSON.parse(event.data);
        addTraceLine(`[Error] ${data.message}`);
        statusText.textContent = `error: ${data.message}`;
        if (!finalized) {
          addRecentResult({
            fileName: submittedFileName,
            imageUrl: submittedImageUrl,
            createdAt: new Date().toISOString(),
            offerCountry,
            status: "error",
            result: null,
            error: data.message,
          });
          finalized = true;
        }
      } else {
        addTraceLine("[Error] Event stream closed.");
      }
      setWorking(false);
      activeEventSource?.close();
    });
  } catch (err) {
    statusText.textContent = `error: ${err.message}`;
    addRecentResult({
      fileName: submittedFileName,
      imageUrl: submittedImageUrl,
      createdAt: new Date().toISOString(),
      offerCountry,
      status: "error",
      result: null,
      error: err.message,
    });
    setWorking(false);
  }
}

async function loadRandomExample() {
  if (runBtn.disabled) {
    return;
  }

  statusText.textContent = "Loading random example...";
  try {
    const metaRes = await fetch("/api/examples/random");
    if (!metaRes.ok) {
      const err = await metaRes.json();
      throw new Error(err.detail || "Could not load example metadata.");
    }
    const { url, filename, country } = await metaRes.json();
    const imageRes = await fetch(url);
    if (!imageRes.ok) {
      throw new Error("Example image could not be fetched.");
    }

    const blob = await imageRes.blob();
    const inferredType = blob.type || "image/png";
    const fileName = filename || "example-image";
    const file = new File([blob], fileName, { type: inferredType });
    setSelectedFile(file);
    offerCountryInput.value = country || parseCountryFromExampleFilename(fileName);
    statusText.textContent = `Loaded example: ${fileName}`;
  } catch (err) {
    statusText.textContent = `error: ${err.message}`;
  }
}

fileInput.addEventListener("change", (event) => {
  const [file] = event.target.files || [];
  if (file) setSelectedFile(file);
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("dragging");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragging"));
dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
  const [file] = event.dataTransfer.files || [];
  if (file) {
    setSelectedFile(file);
  }
});

document.addEventListener("paste", (event) => {
  const items = event.clipboardData?.items || [];
  for (const item of items) {
    if (item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        setSelectedFile(file);
        statusText.textContent = "Image pasted from clipboard.";
      }
      break;
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !runBtn.disabled) {
    event.preventDefault();
    startJob();
  }
});

runBtn.addEventListener("click", startJob);
loadExampleBtn.addEventListener("click", loadRandomExample);

window.addEventListener("beforeunload", () => {
  revokeSelectedPreview();
  for (const item of recentResults) {
    if (item.imageUrl) {
      URL.revokeObjectURL(item.imageUrl);
    }
  }
});

const fileInput = document.getElementById("file-input");
const dropZone = document.getElementById("drop-zone");
const dropLabel = document.getElementById("drop-label");
const runBtn = document.getElementById("run-btn");
const traceList = document.getElementById("trace-list");
const resultJson = document.getElementById("result-json");
const statusText = document.getElementById("status-text");
const wipIndicator = document.getElementById("wip-indicator");
const offerCountryInput = document.getElementById("offer-country");

let selectedFile = null;
let activeEventSource = null;

function addTraceLine(text) {
  const item = document.createElement("li");
  item.textContent = text;
  traceList.appendChild(item);
  traceList.scrollTop = traceList.scrollHeight;
}

function resetOutput() {
  traceList.innerHTML = "";
  resultJson.textContent = "Waiting for result...";
}

function setWorking(isWorking) {
  runBtn.disabled = isWorking;
  wipIndicator.classList.toggle("hidden", !isWorking);
}

function setSelectedFile(file) {
  selectedFile = file;
  dropLabel.textContent = file
    ? `Selected: ${file.name || "clipboard-image"} (${Math.round(file.size / 1024)} KB)`
    : "Drop image here, click to upload, or paste from clipboard";
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

  const form = new FormData();
  form.append("image", selectedFile);
  form.append("offer_country", offerCountryInput.value.trim() || "italy");

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
      if (data.status === "success" || data.status === "error") {
        setWorking(false);
      }
    });

    activeEventSource.addEventListener("trace", (event) => {
      const data = JSON.parse(event.data);
      addTraceLine(data.message);
    });

    activeEventSource.addEventListener("result", (event) => {
      const data = JSON.parse(event.data);
      resultJson.textContent = JSON.stringify(data.result, null, 2);
      addTraceLine("[Result] Final JSON received.");
    });

    activeEventSource.addEventListener("error", (event) => {
      if (event?.data) {
        const data = JSON.parse(event.data);
        addTraceLine(`[Error] ${data.message}`);
        statusText.textContent = `error: ${data.message}`;
      } else {
        addTraceLine("[Error] Event stream closed.");
      }
      setWorking(false);
      activeEventSource?.close();
    });
  } catch (err) {
    statusText.textContent = `error: ${err.message}`;
    resultJson.textContent = JSON.stringify({ error: err.message }, null, 2);
    setWorking(false);
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

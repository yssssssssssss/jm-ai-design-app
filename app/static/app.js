const fileInput = document.querySelector("#upload-files");
const fileList = document.querySelector("#selected-files");
const dropzone = document.querySelector("#upload-dropzone");
const filePickerButton = document.querySelector("#file-picker-button");

if (fileInput && fileList) {
  const renderSelectedFiles = () => {
    fileList.replaceChildren();
    for (const file of fileInput.files) {
      const item = document.createElement("li");
      item.textContent = file.name;
      fileList.appendChild(item);
    }
  };

  fileInput.addEventListener("change", renderSelectedFiles);
}

if (fileInput && filePickerButton) {
  filePickerButton.addEventListener("click", () => {
    fileInput.click();
  });
}

if (fileInput && fileList && dropzone) {
  const isFileDrag = (event) =>
    Array.from(event.dataTransfer?.types || []).includes("Files");
  const setDraggedFiles = (files) => {
    const transfer = new DataTransfer();
    for (const file of files) {
      transfer.items.add(file);
    }
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
  };

  for (const eventName of ["dragover", "drop"]) {
    document.addEventListener(eventName, (event) => {
      if (!isFileDrag(event)) {
        return;
      }
      event.preventDefault();
    });
  }

  for (const eventName of ["dragenter", "dragover"]) {
    dropzone.addEventListener(eventName, (event) => {
      if (!isFileDrag(event)) {
        return;
      }
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropzone.addEventListener(eventName, () => {
      dropzone.classList.remove("is-dragging");
    });
  }

  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    if (!event.dataTransfer?.files.length) {
      return;
    }
    setDraggedFiles(event.dataTransfer.files);
  });
}

const detail = document.querySelector("[data-task-id]");

if (detail) {
  const taskId = detail.getAttribute("data-task-id");
  const status = document.querySelector("#task-status");

  const poll = async () => {
    const response = await fetch(`/tasks/${taskId}/status`);
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    if (status) {
      status.textContent = data.status;
      status.className = `status status-${data.status}`;
    }
    if (data.status === "queued" || data.status === "running") {
      window.setTimeout(poll, 2500);
      return;
    }
    window.location.reload();
  };

  if (status && (status.textContent === "queued" || status.textContent === "running")) {
    window.setTimeout(poll, 2500);
  }
}

const taskList = document.querySelector("[data-task-list='running']");

if (taskList && Number(taskList.getAttribute("data-task-count") || "0") > 0) {
  window.setTimeout(() => {
    window.location.reload();
  }, 5000);
}

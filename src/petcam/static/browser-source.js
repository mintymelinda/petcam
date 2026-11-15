// DOM references and retry configuration
const RETRY_DELAY_MS = 3000;
const image = document.getElementById("stream");
const status = document.getElementById("status");

// Stream lifecycle handlers
function handleStreamLoad() {
  image.dataset.ready = "1";
  status.hidden = true;
}

function handleStreamError() {
  image.removeAttribute("data-ready");
  status.hidden = false;
  status.textContent =
    "Camera stream unavailable. Check that the camera is running and MJPEG mode is enabled. Retrying...";

  window.setTimeout(retryStream, RETRY_DELAY_MS);
}

function retryStream() {
  image.src = "/stream?retry=" + Date.now();
}

// Event wiring
image.addEventListener("load", handleStreamLoad);
image.addEventListener("error", handleStreamError);

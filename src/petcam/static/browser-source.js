const image=document.getElementById("stream"),
status=document.getElementById("status");
image.onload=()=>{
  image.dataset.ready="1";
  status.hidden=true
};
image.onerror=()=>{
  image.removeAttribute("data-ready");
  status.hidden=false;
  status.textContent="Camera stream unavailable. Check that the camera is running and MJPEG mode is enabled. Retrying...";
  setTimeout(()=>{
    image.src="/stream?retry="+Date.now()
  },
  3000)
}

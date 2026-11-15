const $=id=>document.getElementById(id);
let inventory=[], activeConfig=null, captureStatus= {
}, rtmpSettings= {
  enabled:false
};
$("first-run-form").onsubmit=async event=> {
  event.preventDefault();
  const password=$("setup-password").value, confirmation=$("setup-password-confirm").value, message=$("setup-message"), button=$("setup-submit");
  if(password!==confirmation) {
    message.textContent="The passwords do not match.";
    return
  }
  button.disabled=true;
  message.textContent="Creating administrator account…";
  try {
    const response=await fetch("/api/setup",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify( {
        password, password_confirmation:confirmation
      })
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||"Initial setup failed");
    message.textContent="Administrator account created. Opening PetCam…";
    location.reload()
  }
  catch(error) {
    message.textContent=error.message;
    button.disabled=false
  }
};
let csrfToken=null;
let loginPromise=null;
async function login() {
  if(loginPromise)return loginPromise;
  loginPromise=(async()=> {
    const setupResponse=await fetch("/api/setup/status",  {
      cache:"no-store"
    });
    const setupState=await setupResponse.json();
    if(!setupResponse.ok)throw Error(setupState.error||"Unable to check initial setup");
    if(!setupState.configured)throw Error("Create the administrator password in the welcome panel before signing in.");
    return await new Promise((resolve, reject)=> {
      const dialog=$("login-dialog"), form=$("login-form"), password=$("login-password"), message=$("login-message"), button=$("login-submit");
      let settled=false;
      const finish=(error, data)=> {
        if(settled)return;
        settled=true;
        password.value="";
        dialog.close();
        if(error)reject(error);
        else resolve(data)
      };
      form.onsubmit=async event=> {
        event.preventDefault();
        button.disabled=true;
        message.textContent="Signing in…";
        try {
          const response=await fetch("/api/login",  {
            method:"POST", headers: {
              "Content-Type":"application/json"
            }, body:JSON.stringify( {
              password:password.value
            })
          });
          const data=await response.json();
          if(!response.ok)throw Error(data.error||"Sign-in failed");
          csrfToken=data.csrf_token;
          finish(null, data)
        }
        catch(error) {
          message.textContent=error.message;
          password.value="";
          password.focus();
          button.disabled=false
        }
      };
      dialog.oncancel=event=> {
        event.preventDefault();
        finish(Error("Sign-in cancelled"))
      };
      password.setAttribute("type", "password");
      password.type="password";
      password.setAttribute("autocomplete", "current-password");
      dialog.showModal();
      password.focus()
    })
  })();
  try {
    return await loginPromise
  }
  finally {
    loginPromise=null
  }
}
async function request(path, options= {
}) {
  const headers=new Headers(options.headers|| {
  });
  if(options.method&&options.method.toUpperCase()!=="GET"&&!csrfToken) {
    let session=await fetch("/api/session");
    if(session.status===401) {
      await login()
    }
    else {
      const state=await session.json();
      if(!session.ok)throw Error(state.error||session.statusText);
      csrfToken=state.csrf_token
    }
  }
  if(options.method&&options.method.toUpperCase()!=="GET"&&csrfToken)headers.set("X-PetCam-CSRF", csrfToken);
  let r=await fetch(path,  {
    ...options, headers
  });
  if(r.status===401) {
    await login();
    if(options.method&&options.method.toUpperCase()!=="GET"&&csrfToken)headers.set("X-PetCam-CSRF", csrfToken);
    r=await fetch(path,  {
      ...options, headers
    })
  }
  const d=await r.json();
  if(!r.ok)throw Error(d.error||r.statusText);
  return d
}
const tabButtons=[...document.querySelectorAll("[data-tab]")];
function activateTab(name, moveFocus=false) {
  const selected=tabButtons.find(button=>button.dataset.tab===name);
  if(!selected)return;
  for(const button of tabButtons) {
    const active=button===selected;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex=active?0:-1;
    const panel=$(button.getAttribute("aria-controls"));
    panel.hidden=!active;
    panel.classList.toggle("active", active);
  }
  if(moveFocus)selected.focus();
}
for(const button of tabButtons) {
  button.addEventListener("click", ()=>activateTab(button.dataset.tab));
  button.addEventListener("keydown", event=> {
    const index=tabButtons.indexOf(button);
    let next=null;
    if(event.key==="ArrowRight")next=(index+1)%tabButtons.length;
    else if(event.key==="ArrowLeft")next=(index-1+tabButtons.length)%tabButtons.length;
    else if(event.key==="Home")next=0;
    else if(event.key==="End")next=tabButtons.length-1;
    if(next!==null) {
      event.preventDefault();
      activateTab(tabButtons[next].dataset.tab, true)
    }
  });
}
activateTab("camera");
refreshRTMP();
function modesFor(camera) {
  return camera.kind==="usb"?camera.modes.filter(m=>["MJPG", "MJPEG", "JPEG", "YUYV", "YVYU", "UYVY", "YUV420", "YVU420", "RGB565", "RGB24", "GREY", "H264"].includes(m.format)):camera.modes
}
function selectedCaptureMode() {
  try {
    return JSON.parse($("mode").value)
  }
  catch(error) {
    return null
  }
}
function h264ModeSelectedOrActive() {
  return (activeConfig?.SOURCE==="usb"&&activeConfig?.FORMAT==="H264")||captureStatus.active_capture_format==="H264"||selectedCaptureMode()?.format==="H264"
}
function syncOutputModeControls() {
  const forced=h264ModeSelectedOrActive();
  $("rtmp-enabled").checked=forced||!!rtmpSettings.enabled;
  $("rtmp-enabled").disabled=forced;
  $("save-rtmp").disabled=forced;
  document.querySelectorAll("[data-browser-feed-link]").forEach(link=> {
    link.closest("p").hidden=forced
  });
  $("h264-mode-note").hidden=!forced
}
function projectedPixelRate(mode) {
  return mode.width*mode.height*mode.fps
}
function exceedsPerformanceBudget(camera, mode) {
  if(mode.format==="H264")return false;
  const budget=Number(camera?.hardware_budget_pixels_per_second||0);
  return budget>0&&projectedPixelRate(mode)>budget
}
function confirmPerformanceOverride(camera, mode) {
  if(!exceedsPerformanceBudget(camera, mode))return false;
  const estimate=projectedPixelRate(mode), budget=Number(camera.hardware_budget_pixels_per_second);
  return confirm("Performance warning: this capture mode is estimated at "+estimate.toLocaleString()+" pixels/second, above the "+camera.hardware_tier+" device guideline of "+budget.toLocaleString()+" pixels/second. It may cause low frame rates, dropped frames, or an unresponsive camera stream. Use this mode anyway?")
}
function showSelectedModeWarning() {
  const c=inventory[+$("camera").value], raw=$("mode").value;
  if(!c||!raw)return;
  const mode=JSON.parse(raw);
  if(exceedsPerformanceBudget(c, mode))$("message").textContent="Performance warning: this capture mode exceeds the estimated "+c.hardware_tier+" device budget. You can still apply it after confirming the warning.";
  else $("message").textContent=mode.format==="H264"?"H.264 selected. The HTTP Browser Source will be disabled and OBS RTSP output will be forced on.":"Selected mode is within the estimated device performance budget.";
  syncOutputModeControls()
}
function activeCameraMatches(camera, config) {
  if(!config)return false;
  if(config.SOURCE==="usb")return camera.kind==="usb"&&(config.USB_PHYSICAL_PATH?camera.physical_path===config.USB_PHYSICAL_PATH:camera.device===config.DEVICE);
  if(config.SOURCE==="csi")return camera.kind==="csi"&&(config.CSI_DEVICE_PATH?camera.device_path===config.CSI_DEVICE_PATH:String(camera.camera)===String(config.CAMERA));
  return false
}
function fillModes(preferred=null) {
  const c=inventory[+$("camera").value];
  $("mode").replaceChildren();
  if(!c)return;
  let matched=false;
  for(const m of modesFor(c)) {
    let fps=m.fps?.length?m.fps:[m.fps_range?.max||30];
    if(c.kind==="usb")fps=fps.filter(Number.isInteger);
    if(preferred&&preferred.width===m.width&&preferred.height===m.height&&(preferred.format||"CSI")===(m.format||"CSI")&&!fps.some(f=>Math.abs(f-preferred.fps)<0.1))fps=[...fps, preferred.fps];
    for(const f of fps) {
      const mode= {
        format:m.format||"CSI", width:m.width, height:m.height, fps:f
      };
      const o=document.createElement("option");
      o.value=JSON.stringify(mode);
      o.textContent=`${m.width}×${m.height} · ${f} fps · ${m.format||"CSI"}`+(exceedsPerformanceBudget(c, mode)?" · ⚠ above device estimate":"");
      if(preferred&&mode.width===preferred.width&&mode.height===preferred.height&&mode.format===(preferred.format||"CSI")&&Math.abs(mode.fps-preferred.fps)<0.1) {
        o.selected=true;
        matched=true
      }
      $("mode").append(o)
    }
  }
  if(preferred&&!matched) {
    const mode= {
      format:preferred.format||"CSI", width:preferred.width, height:preferred.height, fps:Number(preferred.fps)
    };
    const o=document.createElement("option");
    o.value=JSON.stringify(mode);
    o.textContent=`${mode.width}×${mode.height} · ${mode.fps} fps · ${mode.format} (saved setting; not currently advertised)`;
    o.selected=true;
    $("mode").prepend(o)
  }
  $("mode").onchange=showSelectedModeWarning;
  showSelectedModeWarning()
}
function renderCaptureStatus() {
  const fps=Number(captureStatus.latest_captured_fps), configured=activeConfig?.FPS, format=captureStatus.active_capture_format;
  if(Number.isFinite(fps)&&fps>0) {
    $("capture-rate").textContent="Actual captured rate: "+fps.toFixed(1).replace(/\.0$/, "")+" FPS"+(format?" · "+format:"")+(configured&&configured!=="auto"?" · configured: "+configured+" FPS":"")+(captureStatus.active_resolution?" · "+captureStatus.active_resolution:(activeConfig?.RESOLUTION&&activeConfig.RESOLUTION!=="auto"?" · "+activeConfig.RESOLUTION:""))+(captureStatus.capture_mode==="native_h264_csi"?" · CSI hardware encoder": "")
  }
  else $("capture-rate").textContent="Actual captured rate: not currently reported"+(format?" · "+format:"")
}
async function refreshLiveStatus() {
  try {
    const d=await request("/api/live-status");
    refreshStatistics(d);
    captureStatus=d.capture_status|| {
    };
    renderCaptureStatus();
    syncOutputModeControls();
    const updated=new Date(d.capture_status_updated_at*1000);
    $("capture-status-freshness").textContent="Capture status refreshes every 5 seconds · last updated "+updated.toLocaleTimeString()
  }
  catch(error) {
    $("capture-status-freshness").textContent="Live status unavailable: "+error.message
  }
}
async function refreshSystemInfo() {
  try {
    const data=await request("/api/system");
    $("installed-version").textContent="Installed version: "+(data.installed_version||"unknown")
  }
  catch(error) {
    $("installed-version").textContent="Installed version unavailable: "+error.message
  }
}
async function refreshRTMP() {
  try {
    const data=await request("/api/rtmp");
    rtmpSettings=data.config|| {
      enabled:false
    };
    syncOutputModeControls();
    let sourceLabel="";
    if(data.status?.source==="native_h264"||data.status?.source==="native_h264_csi")sourceLabel=data.status.source==="native_h264_csi"?"CSI hardware H.264 stream copy":"native H.264 stream copy";
    else if(data.status?.source==="mjpeg_copy")sourceLabel="MJPEG packet copy";
    let statusText="OBS RTSP feed: "+(data.status?.state||"stopped")+".";
    if(data.status?.active) {
      statusText="OBS RTSP feed is running";
      if(sourceLabel)statusText+=" ("+sourceLabel+")";
      statusText+="."
    }
    $("rtmp-status").textContent=statusText
  }
  catch(error) {
    $("rtmp-status").textContent="OBS feed status unavailable: "+error.message
  }
}
async function saveRTMP() {
  if(h264ModeSelectedOrActive()) {
    syncOutputModeControls();
    return
  }
  const data= {
    enabled:$("rtmp-enabled").checked
  };
  $("save-rtmp").disabled=true;
  $("rtmp-status").textContent="Saving OBS output settings…";
  try {
    const result=await request("/api/rtmp",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify(data)
    });
    let sourceLabel="";
    if(result.status?.source==="native_h264")sourceLabel="native H.264 stream copy";
    else if(result.status?.source==="mjpeg_copy")sourceLabel="MJPEG packet copy";
    let statusText="Settings saved; OBS feed: "+(result.status?.state||"stopped")+".";
    if(result.status?.active) {
      statusText="OBS feed started";
      if(sourceLabel)statusText+=" ("+sourceLabel+")";
      statusText+="."
    }
    $("rtmp-status").textContent=statusText
  }
  catch(error) {
    $("rtmp-status").textContent="Unable to save OBS output settings: "+error.message
  }
  finally {
    $("save-rtmp").disabled=false
  }
}
$("save-rtmp").onclick=saveRTMP;
$("refresh-rtmp").onclick=refreshRTMP;
function renderStatCards(root, items) {
  root.replaceChildren();
  for(const [label, value] of items) {
    const card=document.createElement("div"), name=document.createElement("small"), reading=document.createElement("strong");
    card.style.cssText="background:#1a1d22;border:1px solid #383e47;border-radius:8px;padding:.7rem;min-width:0";
    name.className="muted";
    name.textContent=label;
    reading.style.cssText="display:block;font-size:1.05rem;overflow-wrap:anywhere;margin-top:.2rem";
    reading.textContent=value===null||value===undefined||value===""?"Not available":String(value);
    card.append(name, reading);
    root.append(card)
  }
}
async function refreshStatistics(data=null) {
  try {
    const d=data||await request("/api/live-status"), capture=d.capture_status|| {
    }, stream=d.stream_metrics|| {
    }, network=d.network_status|| {
    }, clients=stream.clients||[], system=d.system_metrics|| {
    }, wifi=network.wifi|| {
    };
    const fps=capture.latest_captured_fps, delivered=clients.length?Math.max(...clients.map(client=>Number(client.average_fps||client.window_fps||0))):null, signal=wifi.signal_dbm, rtmp=d.rtmp_output_status|| {
    };
    const bars=!wifi.connected?0:signal===null||signal===undefined?null:signal>=-50?4:signal>=-60?3:signal>=-67?2:signal>=-75?1:0;
    const labels=["none", "weak", "poor", "good", "excellent"];
    const reception=bars===null?"unknown":labels[bars];
    const metrics=[["Camera FPS", fps?Number(fps).toFixed(1):"Not reported"], ["OBS Feed FPS (RTSP)", rtmp.active&&rtmp.fps!==null&&rtmp.fps!==undefined&&Number.isFinite(Number(rtmp.fps))?Number(rtmp.fps).toFixed(1):rtmp.enabled?(rtmp.state==="stalled"?"No recent output telemetry":rtmp.state):"Disabled"], ["MJPEG delivered FPS (forwarded JPEG FPS)", delivered===null?"No active viewers":delivered.toFixed(1)], ["Wi-Fi signal", reception+(signal===null||signal===undefined?"":" · "+signal+" dBm")+" · "+(bars===null?"—":"▮".repeat(bars)+"▯".repeat(4-bars))], ["CPU", system.cpu_percent===null||system.cpu_percent===undefined?"Not available":Number(system.cpu_percent).toFixed(1)+"%"], ["Memory", system.memory_used_mb===undefined?"Not available":system.memory_used_mb+" / "+system.memory_total_mb+" MiB"], ["Network Up / Down", network.tx_mbps===undefined?"Not available":Number(network.tx_mbps).toFixed(2)+" / "+Number(network.rx_mbps||0).toFixed(2)+" Mbps"]];
    renderStatCards($("system-health-grid"), metrics);
    $("statistics-updated").textContent="Updated "+new Date(d.capture_status_updated_at*1000).toLocaleTimeString()+" · OBS feed: "+(rtmp.enabled?(rtmp.state||"starting"):"disabled")+"; MJPEG delivery is measured separately."
  }
  catch(error) {
    $("statistics-updated").textContent="Statistics unavailable: "+error.message
  }
}
$("refresh-statistics").onclick=refreshStatistics;
async function refresh() {
  $("message").textContent="Scanning connected cameras…";
  try {
    const d=await request("/api/cameras");
    inventory=d.cameras;
    activeConfig=d.active_config;
    captureStatus=d.capture_status|| {
    };
    $("camera").replaceChildren();
    inventory.forEach((c, i)=> {
      const o=document.createElement("option");
      o.value=i;
      o.textContent=c.label;
      $("camera").append(o)
    });
    const activeIndex=inventory.findIndex(c=>activeCameraMatches(c, activeConfig));
    if(activeIndex>=0) {
      $("camera").value=String(activeIndex);
      $("camera").options[activeIndex].textContent+=" · current"
    }
    if(!inventory.length)$("message").textContent="No supported cameras detected. Connect a USB or CSI camera and refresh.";
    else {
      const selected=activeIndex>=0?activeConfig:null;
      const selectedCamera=activeIndex>=0?inventory[activeIndex]:null;
      const currentResolution=selected&&selected.RESOLUTION!=="auto"?selected.RESOLUTION:captureStatus.active_resolution;
      const currentFps=selected&&selected.FPS!=="auto"?Number(selected.FPS):Number(captureStatus.latest_captured_fps);
      let currentFormat=selected&&selected.FORMAT!=="auto"?selected.FORMAT:(captureStatus.active_capture_format||"CSI");
      if(currentFormat==="MJPEG"||currentFormat==="JPEG")currentFormat="MJPG";
      if(selectedCamera?.kind==="csi")currentFormat="CSI";
      const preferred=currentResolution&&currentResolution!=="auto"&&Number.isFinite(currentFps)&&currentFps>0? {
        width:Number(currentResolution.split("x")[0]), height:Number(currentResolution.split("x")[1]), fps:currentFps, format:currentFormat
      }
      :null;
      $("message").textContent=inventory.length+" camera(s) found. Current saved camera settings are selected.";
      fillModes(preferred)
    }
    syncOutputModeControls();
    renderCaptureStatus();
    await refreshCameraControls()
  }
  catch(e) {
    $("message").textContent=e.message
  }
}
function cameraControlLabel(name) {
  const labels= {
    auto_exposure:"Auto exposure", exposure_time_absolute:"Exposure time", exposure_dynamic_framerate:"Dynamic framerate", white_balance_automatic:"Automatic white balance", white_balance_temperature:"White balance temperature", power_line_frequency:"Power-line frequency", backlight_compensation:"Backlight compensation", focus_automatic_continuous:"Continuous autofocus", focus_absolute:"Focus"
  };
  return labels[name]||name.replaceAll("_", " ").replace(/\b\w/g, letter=>letter.toUpperCase())
}
const pendingCameraControlChanges=new Map();
function updateCameraControlDirtyState(control, input, applyButton) {
  const value=control.type==="bool"?(input.checked?1:0):Number(input.value), original=Number(control.value);
  if(control.value!==null&&Number.isFinite(original)&&value===original)pendingCameraControlChanges.delete(control.name);
  else pendingCameraControlChanges.set(control.name, value);
  applyButton.disabled=pendingCameraControlChanges.size===0
}
async function applyCameraControlChanges() {
  const button=$("apply-camera-controls"), status=$("camera-controls-status");
  if(!pendingCameraControlChanges.size)return;
  button.disabled=true;
  status.textContent="Applying camera control changes…";
  try {
    for(const [name, value] of pendingCameraControlChanges) {
      await request("/api/camera-controls",  {
        method:"POST", headers: {
          "Content-Type":"application/json"
        }, body:JSON.stringify( {
          name, value
        })
      });
      pendingCameraControlChanges.delete(name)
    }
    status.textContent="Camera controls updated.";
    await refreshCameraControls()
  }
  catch(error) {
    status.textContent="Could not apply all camera controls: "+error.message;
    button.disabled=pendingCameraControlChanges.size===0
  }
}
async function refreshCameraControls() {
  const root=$("camera-controls-list"), status=$("camera-controls-status"), applyButton=$("apply-camera-controls");
  pendingCameraControlChanges.clear();
  applyButton.disabled=true;
  root.replaceChildren();
  root.style.cssText="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:.45rem";
  status.textContent="Reading active camera controls…";
  try {
    const data=await request("/api/camera-controls");
    if(!data.supported) {
      status.textContent=data.message||"Camera controls are unavailable.";
      root.textContent="";
      return
    }
    status.textContent="Controls for "+data.label+" · "+data.device;
    if(!data.controls.length) {
      root.textContent="This camera did not report any controls.";
      return
    }
    for(const control of data.controls) {
      const row=document.createElement("div"), heading=document.createElement("div"), label=document.createElement("label"), details=document.createElement("small"), editor=document.createElement("div");
      row.style.cssText="border:1px solid #383e47;border-radius:.5rem;padding:.45rem .6rem;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.2rem .65rem;align-items:center";
      heading.style.minWidth="0";
      label.style.margin="0";
      label.textContent=cameraControlLabel(control.name);
      details.className="muted";
      details.style.cssText="display:block;font-size:.78rem;line-height:1.25";
      const isMenu=control.type==="menu"||control.type==="intmenu", isBoolean=control.type==="bool", menuOption=value=>control.menu.find(option=>option.value===value), booleanLabel=value=>value===null?"unknown":Number(value)===1?"Enabled":"Disabled", defaultLabel=control.default===null?"unavailable":(isBoolean?booleanLabel(control.default):control.default);
      details.textContent="Current: "+(isMenu?(menuOption(control.value)?.label??"unknown"):(isBoolean?booleanLabel(control.value):(control.value===null?"unknown":control.value)))+(isMenu?" · Default: "+(menuOption(control.default)?.label??"unavailable")+" · Available: "+control.menu.map(option=>option.label).join(", "):" · Default: "+defaultLabel+(control.min!==null&&control.max!==null?" · Range: "+control.min+"–"+control.max:""))+(control.writable?"":" · Currently unavailable");
      editor.className="row";
      editor.style.cssText="align-items:center;gap:.4rem;justify-content:flex-end";
      let input, output, isRange=false;
      if(isBoolean) {
        input=document.createElement("input");
        input.type="checkbox";
        input.checked=Number(control.value)===1;
        input.indeterminate=control.value===null;
        input.disabled=!control.writable
      }
      else if(isMenu) {
        input=document.createElement("select");
        if(control.value===null) {
          const unknown=document.createElement("option");
          unknown.value="";
          unknown.textContent="Unknown";
          unknown.disabled=true;
          input.append(unknown)
        }
        for(const option of control.menu) {
          const choice=document.createElement("option");
          choice.value=option.value;
          choice.textContent=option.label;
          input.append(choice)
        }
        input.value=control.value===null?"":String(control.value);
        input.disabled=!control.writable;
        input.style.maxWidth="10rem"
      }
      else if(control.type==="int"&&control.value!==null&&control.min!==null&&control.max!==null&&control.max-control.min<=10000) {
        isRange=true;
        input=document.createElement("input");
        input.type="range";
        input.min=control.min;
        input.max=control.max;
        input.step=control.step;
        input.value=control.value;
        input.disabled=!control.writable;
        input.style.maxWidth="8rem";
        output=document.createElement("output");
        output.textContent=input.value;
        input.oninput=()=> {
          output.textContent=input.value;
          updateCameraControlDirtyState(control, input, applyButton);
          if(advancedApplyHandle)clearTimeout(advancedApplyHandle);
          advancedApplyHandle=setTimeout(()=> {
            if(pendingCameraControlChanges.size)applyCameraControlChanges()
          }, 800)
        }
      }
      else {
        input=document.createElement("input");
        input.type="number";
        if(control.min!==null)input.min=control.min;
        if(control.max!==null)input.max=control.max;
        input.step=control.step;
        input.value=control.value??"";
        input.placeholder=control.value===null?"Unknown":"";
        input.disabled=!control.writable;
        input.style.width="6rem"
      }
      if(output)editor.append(input, output);
      else editor.append(input);
      if(control.writable&&!isRange)input.addEventListener("change", ()=> {
        updateCameraControlDirtyState(control, input, applyButton);
        if(advancedApplyHandle)clearTimeout(advancedApplyHandle);
        advancedApplyHandle=setTimeout(()=> {
          if(pendingCameraControlChanges.size)applyCameraControlChanges()
        }, 800)
      });
      heading.append(label, details);
      row.append(heading, editor);
      if(control.name==="exposure_dynamic_framerate") {
        const note=document.createElement("small");
        note.className="muted";
        note.style.gridColumn="1 / -1";
        note.textContent="When enabled, the camera may lower its delivered frame rate to accommodate exposure. Disable it if you need a stable frame-rate target.";
        row.append(note)
      }
      root.append(row)
    }
  }
  catch(error) {
    status.textContent="Camera controls unavailable: "+error.message
  }
}
$("apply-camera-controls").onclick=applyCameraControlChanges;
$("refresh-camera-controls").onclick=refreshCameraControls;
let advancedPollHandle=null, advancedApplyHandle=null;
const advancedDialog=$("advanced-camera-dialog");
$("advanced-camera-open").onclick=()=> {
  advancedDialog.showModal();
  refreshCameraControls();
  if(advancedPollHandle)clearInterval(advancedPollHandle);
  advancedPollHandle=setInterval(()=> {
    if(pendingCameraControlChanges.size===0)refreshCameraControls()
  }, 60000)
};
$("advanced-camera-close").onclick=()=>advancedDialog.close();
advancedDialog.addEventListener("close", ()=> {
  if(advancedPollHandle) {
    clearInterval(advancedPollHandle);
    advancedPollHandle=null
  }
  if(advancedApplyHandle) {
    clearTimeout(advancedApplyHandle);
    advancedApplyHandle=null
  }
});
$("refresh").onclick=refresh;
$("camera").onchange=()=> {
  fillModes();
  syncOutputModeControls()
};
$("apply").onclick=async()=> {
  const c=inventory[+$("camera").value], m=$("mode").value;
  if(!c||!m)return;
  const mode=JSON.parse(m), override=confirmPerformanceOverride(c, mode);
  if(exceedsPerformanceBudget(c, mode)&&!override)return;
  $("apply").disabled=true;
  $("message").textContent="Applying camera settings…";
  try {
    await request("/api/select",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify( {
        kind:c.kind, camera_id:c.id, device:c.device, physical_path:c.physical_path, device_path:c.device_path, camera:c.camera, mode, allow_performance_override:override
      })
    });
    await refresh();
    await refreshRTMP();
    $("message").textContent=mode.format==="H264"?"H.264 capture enabled. Use the OBS RTSP Media Source; the HTTP Browser Source is disabled.":"Camera settings saved. The live preview has been reconnected."
  }
  catch(e) {
    $("message").textContent=e.message
  }
  finally {
    $("apply").disabled=false
  }
};
$("logout").onclick=async()=> {
  try {
    await request("/api/logout",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:"{}"
    });
    csrfToken=null;
    location.reload()
  }
  catch(e) {
    alert(e.message)
  }
};
async function refreshTimelapse() {
  try {
    const d=await request("/api/timelapse");
    const c=d.config, s=d.status;
    $("timelapse-enabled").checked=c.enabled;
    $("timelapse-interval").value=c.interval_seconds;
    $("timelapse-start").value=c.schedule_start;
    $("timelapse-end").value=c.schedule_end;
    $("timelapse-retention").value=c.retention_days;
    $("timelapse-storage").value=c.max_storage_mb;
    $("timelapse-free").value=c.min_free_mb;
    $("timelapse-width").value=c.max_width;
    $("timelapse-quality").value=c.jpeg_quality;
    $("timelapse-path").value=c.storage_path;
    $("timelapse-status").textContent="Status: "+s.state+" · "+s.frames+" frames · "+Math.round(s.storage_bytes/1048576)+" MiB"+(s.last_capture_at?" · Last capture: "+s.last_capture_at:"")+(s.last_error?" · "+s.last_error:"")
  }
  catch(e) {
    $("timelapse-status").textContent="Timelapse status unavailable: "+e.message
  }
}
$("refresh-timelapse").onclick=refreshTimelapse;
$("save-timelapse").onclick=async()=> {
  const b=$("save-timelapse");
  b.disabled=true;
  try {
    await request("/api/timelapse",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify( {
        enabled:$("timelapse-enabled").checked, interval_seconds:Number($("timelapse-interval").value), schedule_start:$("timelapse-start").value, schedule_end:$("timelapse-end").value, retention_days:Number($("timelapse-retention").value), max_storage_mb:Number($("timelapse-storage").value), min_free_mb:Number($("timelapse-free").value), max_width:Number($("timelapse-width").value), jpeg_quality:Number($("timelapse-quality").value), storage_path:$("timelapse-path").value
      })
    });
    await refreshTimelapse()
  }
  catch(e) {
    $("timelapse-status").textContent=e.message
  }
  finally {
    b.disabled=false
  }
};
refreshTimelapse();
async function refreshMotion() {
  try {
    const d=await request("/api/motion"), c=d.config, s=d.status;
    $("motion-enabled").checked=c.enabled;
    $("motion-sensitivity").value=c.sensitivity;
    $("motion-min-change").value=c.minimum_changed_percent;
    $("motion-sample").value=c.sample_interval_seconds;
    $("motion-confirm").value=c.confirm_samples;
    $("motion-cooldown").value=c.min_event_interval_seconds;
    $("motion-quiet-enabled").checked=c.quiet_hours_enabled;
    $("motion-quiet-start").value=c.quiet_hours_start;
    $("motion-quiet-end").value=c.quiet_hours_end;
    $("motion-retention").value=c.retention_days;
    $("motion-storage").value=c.max_storage_mb;
    $("motion-free").value=c.min_free_mb;
    $("motion-status").textContent="Status: "+s.state+" · "+s.event_count+" events · "+s.snapshots+" snapshots · "+Math.round(s.storage_bytes/1048576)+" MiB"+(s.last_event_at?" · Last event: "+s.last_event_at:"")+(s.cpu_percent!==undefined?" · Worker CPU: "+s.cpu_percent+"%":"")+(s.peak_rss_kib!==undefined?" · Peak RAM: "+Math.round(s.peak_rss_kib/1024)+" MiB":"")+(s.last_error?" · "+s.last_error:"");
    const root=$("motion-events");
    root.replaceChildren();
    if(!s.events.length) {
      root.textContent="No motion events recorded.";
      return
    }
    for(const event of s.events) {
      const row=document.createElement("div"), img=document.createElement("img"), details=document.createElement("div"), time=document.createElement("div"), change=document.createElement("small");
      row.className="motion-event";
      img.src="/api/motion/events/"+encodeURIComponent(event.file);
      img.alt="Motion snapshot "+event.timestamp;
      time.textContent=event.timestamp;
      change.textContent="Changed pixels: "+event.changed_percent+"%";
      details.append(time, change);
      row.append(img, details);
      root.append(row)
    }
  }
  catch(e) {
    $("motion-status").textContent="Motion status unavailable: "+e.message
  }
}
$("refresh-motion").onclick=refreshMotion;
$("save-motion").onclick=async()=> {
  const b=$("save-motion");
  b.disabled=true;
  try {
    await request("/api/motion",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify( {
        enabled:$("motion-enabled").checked, sensitivity:Number($("motion-sensitivity").value), minimum_changed_percent:Number($("motion-min-change").value), sample_interval_seconds:Number($("motion-sample").value), confirm_samples:Number($("motion-confirm").value), min_event_interval_seconds:Number($("motion-cooldown").value), quiet_hours_enabled:$("motion-quiet-enabled").checked, quiet_hours_start:$("motion-quiet-start").value, quiet_hours_end:$("motion-quiet-end").value, retention_days:Number($("motion-retention").value), max_storage_mb:Number($("motion-storage").value), min_free_mb:Number($("motion-free").value)
      })
    });
    await refreshMotion()
  }
  catch(e) {
    $("motion-status").textContent=e.message
  }
  finally {
    b.disabled=false
  }
};
refreshMotion();
setInterval(refreshMotion, 15000);
async function refreshLightSensor() {
  try {
    const d=await request("/api/light-sensor"), c=d.config, s=d.status;
    $("light-sensor-enabled").checked=c.ENABLED;
    $("light-bright-threshold").value=c.BRIGHT_THRESHOLD_LUX;
    $("light-dark-threshold").value=c.DARK_THRESHOLD_LUX;
    const reading=s.illuminance_lux===undefined?"No lux reading":s.illuminance_lux+" lx";
    $("light-sensor-status").textContent="Status: "+s.state+" · "+reading+(s.error?" · "+s.error:"")
  }
  catch(e) {
    $("light-sensor-status").textContent="Light sensor status unavailable: "+e.message
  }
}
$("refresh-light-sensor").onclick=refreshLightSensor;
$("save-light-sensor").onclick=async()=> {
  const b=$("save-light-sensor");
  b.disabled=true;
  try {
    await request("/api/light-sensor",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:JSON.stringify( {
        ENABLED:$("light-sensor-enabled").checked, BRIGHT_THRESHOLD_LUX:Number($("light-bright-threshold").value), DARK_THRESHOLD_LUX:Number($("light-dark-threshold").value)
      })
    });
    await refreshLightSensor()
  }
  catch(e) {
    $("light-sensor-status").textContent=e.message
  }
  finally {
    b.disabled=false
  }
};
refreshLightSensor();
setInterval(refreshLightSensor, 10000);
async function refreshDiagnostics() {
  try {
    const d=await request("/api/diagnostics");
    const layers=d.layers|| {
    };
    const failed=Object.entries(layers).filter(([k, v])=>v&&(v.healthy===false||v.reachable===false||v.resolved===false||v.available===false));
    $("diagnostic-summary").textContent=failed.length?failed.map(([k])=>k.replaceAll("_", " ")+": attention needed").join(" · "):"Local camera, listener, and network checks look healthy.";
    const urls=(d.obs_browser_source_urls||[]).join("\n");
    $("diagnostic-details").textContent="OBS URL(s): "+urls+"\n"+(d.problems||[]).join("\n")+"\n"+d.remote_client_note
  }
  catch(e) {
    $("diagnostic-summary").textContent="Diagnostics unavailable: "+e.message
  }
}
$("refresh-diagnostics").onclick=refreshDiagnostics;
refreshDiagnostics();
$("download-support-bundle").onclick=async()=> {
  const b=$("download-support-bundle");
  b.disabled=true;
  try {
    let r=await fetch("/api/support-bundle");
    if(r.status===401) {
      await login();
      r=await fetch("/api/support-bundle")
    }
    if(!r.ok)throw Error("Support bundle request failed ("+r.status+")");
    const blob=await r.blob(), url=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=url;
    a.download="petcam-support.tar.gz";
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url)
  }
  catch(e) {
    $("diagnostic-summary").textContent="Support bundle failed: "+e.message
  }
  finally {
    b.disabled=false
  }
};
async function refreshHealth() {
  try {
    const h=await request("/api/health");
    $("health-state").textContent="Status: "+h.state.replaceAll("_", " ");
    $("health-reason").textContent=h.reason||"No active issue reported.";
    $("health-details").textContent="Recoveries: "+(h.recovery_count||0)+" · Last checked: "+(h.last_checked_at||"not yet")+(h.last_recovery_at?" · Last recovery: "+h.last_recovery_at:"")
  }
  catch(e) {
    $("health-state").textContent="Health status unavailable";
    $("health-reason").textContent=e.message
  }
}
$("refresh-health").onclick=refreshHealth;
refresh();
refreshLiveStatus();
setInterval(refreshLiveStatus, 5000);
refreshSystemInfo();
refreshHealth();
setInterval(refreshHealth, 30000);
const autoCheck=$("auto-check");
autoCheck.checked=localStorage.getItem("petcam-auto-update-check")==="true";
autoCheck.onchange=()=>localStorage.setItem("petcam-auto-update-check", String(autoCheck.checked));
let updateAvailable=false, updateBusy=false;
let updatePollTimer=null, updatePollInFlight=false;
function scheduleUpdatePoll(delay=2000) {
  if(updatePollTimer)clearTimeout(updatePollTimer);
  updatePollTimer=setTimeout(updateStatus, delay)
}
async function updateStatus() {
  if(updatePollInFlight)return;
  updatePollInFlight=true;
  try {
    const s=await request("/api/update/status"), wasBusy=updateBusy;
    updateBusy=!!s.active;
    const labels= {
      starting:"Starting", checking:"Checking release", downloading:"Downloading", staging:"Staging files", installing:"Installing", restarting:"Restarting services", authenticating:"Verifying signed release", verifying:"Verifying installation", complete:"Complete", failed:"Failed", idle:"Idle"
    };
    $("update-state").textContent=(labels[s.stage]||s.stage||"Unknown")+(s.active?"…":"");
    const detail=s.message||"No update has been run yet.";
    const stamp=s.updated_at?new Date(s.updated_at*1000).toLocaleTimeString():"";
    $("update-message").textContent=detail+(stamp?" · Updated "+stamp:"")+(s.warning?" · Warning: "+s.warning:"");
    $("update-logs").textContent=s.logs||s.log_warning||"No installer output is available.";
    if(s.active) {
      $("install-update").disabled=true;
      $("check-updates").disabled=true;
      scheduleUpdatePoll(2000)
    }
    else {
      $("check-updates").disabled=false;
      $("install-update").hidden=!updateAvailable;
      $("install-update").disabled=!updateAvailable;
      if(wasBusy) {
        updateBusy=false;
        await refreshSystemInfo();
        if(s.stage==="complete")await checkUpdates()
      }
    }
  }
  catch(e) {
    $("update-state").textContent=updateBusy?"Reconnecting…":"Status unavailable";
    $("update-message").textContent=updateBusy?"The manager connection was interrupted. The installer may still be running; reconnecting automatically.":("Unable to read installer status: "+e.message);
    if(updateBusy)scheduleUpdatePoll(2500);
  }
  finally {
    updatePollInFlight=false
  }
}
async function checkUpdates() {
  const b=$("check-updates");
  updateAvailable=false;
  $("install-update").hidden=true;
  b.disabled=true;
  $("update-message").textContent="Checking signed release metadata…";
  try {
    const d=await request("/api/update/check");
    updateAvailable=d.update_available;
    $("install-update").hidden=!updateAvailable;
    if(d.status==="no-complete-release") {
      $("update-state").textContent="No complete release";
      $("update-message").textContent="No complete signed PetCam release is currently available. Incomplete releases are skipped automatically; try again later."
    }
    else {
      $("update-state").textContent=updateAvailable?"Update available":"Up to date";
      $("update-message").textContent=updateAvailable?"A verified application release is available. Review the notes before installing.":"This device is running the latest published PetCam application."
    }
    $("release-notes").textContent=(d.releases||[]).find(r=>r.update_available)?.release_notes||((d.releases||[])[0]?.release_notes)||"No release notes provided by the latest verified release.";
    const releaseList=(d.releases||[]).map(r=>r.version+" · "+Math.ceil(r.archive_size/1048576)+" MiB"+(r.update_available?" · update":" · installed/current")+(r.release_notes?"\n"+r.release_notes:"")).join("\n\n");
    $("update-details").textContent="Installed: "+(d.installed_version||"unknown")+" · Newest valid: "+(d.available_version||"none")+"\n\nRecent verified releases\n"+(releaseList||"No complete signed releases found.");
    $("install-update").disabled=!updateAvailable||updateBusy
  }
  catch(e) {
    $("update-state").textContent="Check failed";
    $("update-message").textContent=e.message
  }
  finally {
    b.disabled=false
  }
}
$("check-updates").onclick=checkUpdates;
async function installUpdate() {
  if(!updateAvailable||updateBusy)return;
  $("update-confirmation").hidden=true;
  $("install-update").disabled=true;
  $("check-updates").disabled=true;
  updateBusy=true;
  $("update-message").textContent="Starting verified update…";
  try {
    await request("/api/update/install",  {
      method:"POST", headers: {
        "Content-Type":"application/json"
      }, body:"{}"
    });
    $("update-state").textContent="Starting…";
    $("update-message").textContent="The update has been accepted. Progress is saved on the device; this page will reconnect automatically if the manager restarts.";
    scheduleUpdatePoll(500)
  }
  catch(e) {
    $("update-message").textContent="The start request did not complete: "+e.message+" Checking whether the updater started…";
    scheduleUpdatePoll(500)
  }
}
$("install-update").onclick=()=> {
  if(!updateAvailable||updateBusy)return;
  $("update-confirmation").hidden=false;
  $("confirm-update-install").focus()
};
$("cancel-update-install").onclick=()=> {
  $("update-confirmation").hidden=true;
  $("install-update").focus()
};
$("confirm-update-install").onclick=installUpdate;
if(autoCheck.checked)checkUpdates();
updateStatus();
(async()=> {
  try {
    const response=await fetch("/api/setup/status",  {
      cache:"no-store"
    });
    const state=await response.json();
    if(!response.ok)throw Error(state.error||"Unable to check setup status");
    if(!state.configured) {
      document.body.classList.add("setup-required");
      $("first-run").hidden=false
    }
  }
  catch(error) {
    $("setup-message").textContent=error.message
  }
})();

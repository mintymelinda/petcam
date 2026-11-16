// Shared authentication and CSRF-aware API client.
let csrfToken = null;
let loginPromise = null;
async function login() {
  if (loginPromise) return loginPromise;
  loginPromise = (async () => {
    const setupResponse = await fetch("/api/setup/status", {
      cache: "no-store",
    });
    const setupState = await setupResponse.json();
    if (!setupResponse.ok)
      throw Error(setupState.error || "Unable to check initial setup");
    if (!setupState.configured)
      throw Error(
        "Create the administrator password in the welcome panel before signing in.",
      );
    return await new Promise((resolve, reject) => {
      const dialog = $("login-dialog"),
        form = $("login-form"),
        password = $("login-password"),
        message = $("login-message"),
        button = $("login-submit");
      let settled = false;
      const finish = (error, data) => {
        if (settled) return;
        settled = true;
        password.value = "";
        dialog.close();
        if (error) reject(error);
        else resolve(data);
      };
      form.onsubmit = async (event) => {
        event.preventDefault();
        button.disabled = true;
        message.textContent = "Signing in…";
        try {
          const response = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: password.value }),
          });
          const data = await response.json();
          if (!response.ok) throw Error(data.error || "Sign-in failed");
          csrfToken = data.csrf_token;
          finish(null, data);
        } catch (error) {
          message.textContent = error.message;
          password.value = "";
          password.focus();
          button.disabled = false;
        }
      };
      dialog.oncancel = (event) => {
        event.preventDefault();
        finish(Error("Sign-in cancelled"));
      };
      password.setAttribute("type", "password");
      password.type = "password";
      password.setAttribute("autocomplete", "current-password");
      dialog.showModal();
      password.focus();
    });
  })();
  try {
    return await loginPromise;
  } finally {
    loginPromise = null;
  }
}
async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.method && options.method.toUpperCase() !== "GET" && !csrfToken) {
    let session = await fetch("/api/session");
    if (session.status === 401) {
      await login();
    } else {
      const state = await session.json();
      if (!session.ok) throw Error(state.error || session.statusText);
      csrfToken = state.csrf_token;
    }
  }
  if (options.method && options.method.toUpperCase() !== "GET" && csrfToken)
    headers.set("X-PetCam-CSRF", csrfToken);
  let r = await fetch(path, { ...options, headers });
  if (r.status === 401) {
    await login();
    if (options.method && options.method.toUpperCase() !== "GET" && csrfToken)
      headers.set("X-PetCam-CSRF", csrfToken);
    r = await fetch(path, { ...options, headers });
  }
  const d = await r.json();
  if (!r.ok) throw Error(d.error || r.statusText);
  return d;
}

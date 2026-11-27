(() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

  const getSelectedLanguage = () => {
    const select = document.getElementById("chatLanguage");
    const candidate = select?.value || (() => {
      try {
        return window.localStorage.getItem("satya_chat_language");
      } catch (_error) {
        return null;
      }
    })();
    return candidate === "kn" || candidate === "hi" ? candidate : "en";
  };

  const localizedRequestFailure = (status, language) => {
    if (language === "kn") return `ವಿನಂತಿ ವಿಫಲವಾಗಿದೆ (${status}).`;
    if (language === "hi") return `अनुरोध विफल रहा (${status})।`;
    return `Request failed (${status}).`;
  };

  window.Satya = {
    async request(url, options = {}) {
      const language = getSelectedLanguage();
      const headers = new Headers(options.headers || {});
      if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
      }
      if (!headers.has("X-Satya-Language")) {
        headers.set("X-Satya-Language", language);
      }
      if (options.method && options.method.toUpperCase() !== "GET") {
        headers.set("X-CSRFToken", csrfToken);
      }
      const response = await fetch(url, { credentials: "same-origin", ...options, headers });
      const contentType = response.headers.get("content-type") || "";
      const body = contentType.includes("application/json") ? await response.json() : null;
      if (!response.ok) {
        throw new Error(body?.error || localizedRequestFailure(response.status, language));
      }
      return body;
    },
    escape(value) {
      const node = document.createElement("span");
      node.textContent = value ?? "";
      return node.innerHTML;
    },
    formatDate(value) {
      if (!value) return "—";
      const date = new Date(value);
      return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric"
      });
    },
    notify(message, type = "success") {
      const container = document.getElementById("satyaToastContainer");
      if (!container || !window.bootstrap?.Toast) return;
      const toast = document.createElement("div");
      toast.className = "toast satya-toast";
      toast.setAttribute("role", "status");
      toast.innerHTML = `<div class="toast-body"><i class="bi ${type === "error" ? "bi-exclamation-circle" : "bi-check-circle"}"></i><span></span><button type="button" class="btn-close ms-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
      toast.querySelector("span").textContent = message;
      container.append(toast);
      toast.addEventListener("hidden.bs.toast", () => toast.remove(), { once: true });
      window.bootstrap.Toast.getOrCreateInstance(toast, { delay: 3200 }).show();
    }
  };
})();

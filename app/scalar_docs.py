"""Scalar UI вместо Swagger + превью картинок из поля image_url в JSON-ответах."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

# Превью image_url только для POST /api/v1/craft в docs UI.
_IMAGE_URL_PREVIEW_SCRIPT = """
(function () {
  let previewTimer = null;
  let lastPreviewData = null;
  let previewModalRoot = null;

  const CRAFT_PATH = "/api/v1/craft";
  const RECIPES_PATH = "/api/v1/recipes";

  function pathOf(url) {
    try {
      return new URL(url, window.location.origin).pathname;
    } catch (_) {
      return String(url || "").split("?")[0];
    }
  }

  function parseFetchArgs(args) {
    const input = args[0];
    const init = args[1] || {};
    if (typeof input === "string") {
      return { url: input, method: (init.method || "GET").toUpperCase() };
    }
    if (input && typeof input === "object") {
      return {
        url: input.url || "",
        method: (init.method || input.method || "GET").toUpperCase(),
      };
    }
    return { url: "", method: "GET" };
  }

  function clearPreview() {
    lastPreviewData = null;
    previewModalRoot = null;
    document.querySelectorAll("[data-aichemi-image-preview]").forEach((node) => node.remove());
  }

  function isElementVisible(el) {
    if (!el || !document.body.contains(el)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function getActiveDialog() {
    const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(isElementVisible);
    if (!dialogs.length) return null;
    return dialogs[dialogs.length - 1];
  }

  function purgeOrphanPreviews() {
    const dialog = getActiveDialog();
    document.querySelectorAll("[data-aichemi-image-preview]").forEach((el) => {
      if (!dialog || !dialog.contains(el)) el.remove();
    });
    if (!dialog) {
      lastPreviewData = null;
      previewModalRoot = null;
    }
  }

  function isCraftTestDialog(dialog) {
    return !!dialog && dialog.textContent.includes("/api/v1/craft");
  }

  function isTestPanelOpen() {
    const dialog = getActiveDialog();
    return !!dialog && isCraftTestDialog(dialog);
  }

  function rememberPreview(payload) {
    if (!payload || typeof payload.image_url !== "string" || Array.isArray(payload)) return;
    lastPreviewData = payload;
    schedulePreview();
  }

  function handleCraftResponse(url, bodyText) {
    if (pathOf(url) !== CRAFT_PATH) return;
    try {
      rememberPreview(JSON.parse(bodyText));
    } catch (_) {}
  }

  function handleRecipesResponse(url) {
    if (pathOf(url) === RECIPES_PATH) clearPreview();
  }

  function buildPreviewBox(data) {
    const url = data.image_url;
    const absolute = url.startsWith("http") ? url : `${window.location.origin}${url}`;

    const box = document.createElement("div");
    box.dataset.aichemiImagePreview = absolute;
    box.style.cssText =
      "padding:12px 16px;margin:12px 0 0;border-top:1px solid var(--scalar-border-color,rgba(255,255,255,.12));";

    const caption = document.createElement("div");
    caption.textContent = "Preview изображения (только docs UI)";
    caption.style.cssText = "font-size:12px;opacity:.65;margin-bottom:8px;";

    const img = document.createElement("img");
    img.src = absolute;
    img.alt = data.result ? `Изображение: ${data.result}` : "Изображение результата";
    img.style.cssText =
      "display:block;max-width:min(100%,512px);border-radius:8px;border:1px solid var(--scalar-border-color,rgba(255,255,255,.12));";

    box.append(caption, img);
    return box;
  }

  function findMountPoint(data, dialog) {
    const needle = data.image_url;
    let best = null;
    let bestLen = Infinity;

    for (const el of dialog.querySelectorAll(".cm-editor, pre, code")) {
      const text = el.textContent || "";
      if (!text.includes(needle) || !text.includes("image_url")) continue;
      if (text.length >= bestLen) continue;
      best = el;
      bestLen = text.length;
    }

    if (!best) return null;

    return best.closest(".cm-editor")?.parentElement || best.parentElement;
  }

  function injectImagePreview(data) {
    if (!data || typeof data.image_url !== "string") return;

    const dialog = getActiveDialog();
    if (!dialog || !isCraftTestDialog(dialog)) {
      clearPreview();
      return;
    }

    const absolute = data.image_url.startsWith("http")
      ? data.image_url
      : `${window.location.origin}${data.image_url}`;

    if (dialog.querySelector(`[data-aichemi-image-preview="${absolute}"]`)) return;

    dialog.querySelectorAll("[data-aichemi-image-preview]").forEach((node) => node.remove());

    const mount = findMountPoint(data, dialog);
    if (!mount) return;

    mount.appendChild(buildPreviewBox(data));
    previewModalRoot = dialog;
  }

  function tryPreviewFromDom() {
    if (!lastPreviewData) return;
    if (!isTestPanelOpen()) {
      clearPreview();
      return;
    }
    injectImagePreview(lastPreviewData);
  }

  function schedulePreview() {
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(tryPreviewFromDom, 150);
    [350, 700, 1200, 2000, 3500].forEach((ms) =>
      window.setTimeout(tryPreviewFromDom, ms)
    );
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const { url } = parseFetchArgs(args);
    const response = await originalFetch(...args);
    try {
      if (!response.ok) return response;
      handleRecipesResponse(url);
      if (pathOf(url) === CRAFT_PATH) {
        const bodyText = await response.clone().text();
        handleCraftResponse(url, bodyText);
      }
    } catch (_) {}
    return response;
  };

  const xhrOpen = XMLHttpRequest.prototype.open;
  const xhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._aichemiMethod = method;
    this._aichemiUrl = url;
    return xhrOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function (...args) {
    this.addEventListener("load", function () {
      if (this.status < 200 || this.status >= 300) return;
      const url = this._aichemiUrl || "";
      handleRecipesResponse(url);
      handleCraftResponse(url, this.responseText || "");
    });
    return xhrSend.apply(this, args);
  };

  function setupModalCloseWatcher() {
    const observer = new MutationObserver(() => {
      purgeOrphanPreviews();
      if (!getActiveDialog()) clearPreview();
    });

    observer.observe(document.body, { childList: true, subtree: true });

    window.addEventListener("hashchange", clearPreview);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") window.setTimeout(clearPreview, 0);
    });
  }

  window.addEventListener("load", setupModalCloseWatcher);
})();
"""


def _patch_scalar_html(html: str) -> str:
    return html.replace(
        "<script>\n            Scalar.createApiReference",
        f"<script>\n            {_IMAGE_URL_PREVIEW_SCRIPT}\n            Scalar.createApiReference",
        1,
    )


def mount_scalar_docs(app: FastAPI) -> None:
    """Подключает Scalar на /docs; Swagger и ReDoc отключены в create_app()."""

    @app.get("/docs", include_in_schema=False)
    async def scalar_docs() -> HTMLResponse:
        base = get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=app.title,
        )
        response = HTMLResponse(_patch_scalar_html(base.body.decode()))
        response.headers["Cache-Control"] = "no-store"
        return response

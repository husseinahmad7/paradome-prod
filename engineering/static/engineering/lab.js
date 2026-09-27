/* Progressive enhancement only: every action also submits as an ordinary form. */
(() => {
  "use strict";
  const focusByRequest = new WeakMap();
  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const response = event.detail.xhr;
    if (event.detail.target.id !== "lab-state") return;
    // These responses contain escaped, server-rendered validation state.
    if ([400, 409, 422, 429].includes(response.status) && response.getResponseHeader("X-Lab-State") === "1") {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });
  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (!event.detail.elt.closest("#lab-state")) return;
    event.detail.elt.setAttribute("aria-busy", "true");
    const form = event.detail.elt;
    const operation = form.closest(".lab-operation");
    focusByRequest.set(event.detail.xhr, {
      operationId: operation ? operation.getAttribute("aria-labelledby") : null,
      key: form.querySelector('input[name="idempotency_key"]')?.value,
      replay: form.classList.contains("lab-replay-form"),
    });
  });
  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (!event.detail.elt.closest("#lab-state")) return;
    event.detail.elt.removeAttribute("aria-busy");
    // HTMX 1.7 omits `failed` for XHR network errors and timeouts.
    if (event.detail.failed || event.detail.error || event.detail.xhr.status === 0) {
      const status = document.getElementById("lab-update");
      if (!status) return;
      const message = document.createElement("p");
      message.className = "lab-notice is-error";
      const response = event.detail.xhr;
      if (response.status === 404) {
        message.textContent = "This run is unavailable or your session has ended. Return to Lab overview to start again.";
      } else if (response.status === 429) {
        const seconds = Number(response.getResponseHeader("Retry-After"));
        const wait = Number.isInteger(seconds) && seconds > 0 && seconds <= 86400
          ? `Wait ${seconds} seconds` : "Wait a little";
        message.textContent = `Too many attempts. ${wait} before trying again. Your saved records are unchanged; keep the same request key when retrying.`;
      } else {
        message.textContent = "The request did not finish successfully. Reload to check the saved state before trying again. Replaying the same request key is safe.";
      }
      status.replaceChildren(message);
      status.focus({preventScroll: false});
    }
  });
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id !== "lab-state") return;
    const status = document.getElementById("lab-update");
    const previous = focusByRequest.get(event.detail.xhr);
    focusByRequest.delete(event.detail.xhr);
    if (status && status.querySelector(".is-error")) {
      status.focus({preventScroll: false});
      return;
    }
    // The polite live region announces success without pulling mobile users
    // back to the page header. Restore keyboard focus in the updated operation.
    if (!previous) return;
    const currentState = document.getElementById("lab-state");
    if (!currentState) return;
    const operation = Array.from(currentState.querySelectorAll(".lab-operation")).find((item) =>
      (previous.operationId && item.getAttribute("aria-labelledby") === previous.operationId) ||
      (previous.key && item.querySelector('.lab-replay-form input[name="idempotency_key"]')?.value === previous.key)
    );
    if (!operation) return;
    operation.classList.add("is-updated");
    const next = previous.operationId
      ? operation.querySelector(previous.replay ? ".lab-replay-form button" : ".lab-delivery-form select, .lab-replay-form button")
      : document.getElementById(operation.getAttribute("aria-labelledby"));
    if (next) {
      next.focus({preventScroll: true});
      next.scrollIntoView({block: "nearest", behavior: "auto"});
    }
  });
})();

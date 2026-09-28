/* DOM event contracts only; these do not replace real-browser accessibility QA. */
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function harness() {
  const listeners = {};
  const state = {message: "", focused: false, focusPreventScroll: false, busy: false, visible: false, alertRole: ""};
  const classes = new Set(["is-success"]);
  const title = {textContent: "Lab updated"};
  const body = {
    textContent: "",
    setAttribute: (name, value) => { if (name === "role") state.alertRole = value; },
  };
  const status = {
    open: false,
    classList: {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    },
    querySelector: (selector) => selector === "#lab-toast-title" ? title : selector === "#lab-toast-message" ? body : null,
    show: () => { status.open = true; state.visible = true; },
    focus: (options) => { state.focused = true; state.focusPreventScroll = options.preventScroll; },
  };
  Object.defineProperty(state, "message", {get: () => body.textContent});
  const document = {
    body: {addEventListener: (name, callback) => { listeners[name] = callback; }},
    getElementById: () => status,
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "static/engineering/lab.js"), "utf8"), {document});
  const elt = {
    closest: (selector) => selector === "#lab-state" ? {} : null,
    querySelector: () => null,
    classList: {contains: () => false},
    setAttribute: () => { state.busy = true; },
    removeAttribute: () => { state.busy = false; },
  };
  function fire(name, details = {}) {
    const detail = {elt, xhr: {status: 200, getResponseHeader: () => null}, ...details};
    listeners[name]({detail});
    return detail;
  }
  return {state, fire, elt, status, document};
}

test("HTMX 1.7 network errors and timeouts announce recovery without failed flag", () => {
  for (const error of [undefined, "htmx:sendError", "htmx:timeout"]) {
    const {state, fire} = harness();
    fire("htmx:beforeRequest");
    assert.equal(state.busy, true);
    fire("htmx:afterRequest", {xhr: {status: 0}, error});
    assert.equal(state.busy, false);
    assert.match(state.message, /Reload to check the saved state/);
    assert.equal(state.focused, true);
    assert.equal(state.focusPreventScroll, true);
    assert.equal(state.visible, true);
    assert.equal(state.alertRole, "alert");
  }
});

test("unwrapped throttles announce bounded Retry-After and safe retry", () => {
  for (const [header, expected] of [["42", "Wait 42 seconds"], [null, "Wait a little"], ["<script>", "Wait a little"]]) {
    const {state, fire} = harness();
    fire("htmx:afterRequest", {failed: true, xhr: {status: 429, getResponseHeader: () => header}});
    assert.ok(state.message.includes(expected));
    assert.match(state.message, /keep the same request key/);
  }
});

test("validation fragments swap only with the lab marker", () => {
  const {fire} = harness();
  for (const marker of ["1", null]) {
    const detail = fire("htmx:beforeSwap", {target: {id: "lab-state"}, xhr: {status: 409, getResponseHeader: () => marker}});
    assert.equal(detail.shouldSwap, marker === "1" ? true : undefined);
  }
});

test("marked validation errors use the specific swapped toast, not a generic network error", () => {
  const {state, fire} = harness();
  fire("htmx:afterRequest", {failed: true, xhr: {status: 409, getResponseHeader: () => "1"}});
  assert.equal(state.visible, false);
  assert.equal(state.message, "");
});

test("successful responses and unrelated forms do not announce failure", () => {
  const {state, fire, elt} = harness();
  fire("htmx:afterRequest", {failed: false});
  assert.equal(state.message, "");
  elt.closest = () => null;
  fire("htmx:afterRequest", {failed: true, xhr: {status: 500}});
  assert.equal(state.message, "");
});

test("successful swaps keep focus in the matching operation instead of the global notice", () => {
  for (const action of ["submit", "deliver", "replay"]) {
    const {state, fire, elt, status, document} = harness();
    let highlighted = false;
    let focused = false;
    let scrolled = false;
    const control = {
      focus: (options) => { focused = options.preventScroll === true; },
      scrollIntoView: (options) => { scrolled = options.block === "nearest"; },
    };
    const operation = {
      getAttribute: () => "operation-example",
      classList: {add: (name) => { highlighted = name === "is-updated"; }},
      querySelector: (selector) => selector.includes("input[") ? {value: "same-key"} : control,
    };
    document.getElementById = (id) => id === "lab-update" ? status : id === "lab-state" ? {querySelectorAll: () => [operation]} : control;
    elt.closest = (selector) => selector === "#lab-state" ? {} : action === "submit" ? null : operation;
    elt.querySelector = () => ({value: "same-key"});
    elt.classList.contains = () => action === "replay";
    const xhr = {status: 200};
    fire("htmx:beforeRequest", {xhr});
    fire("htmx:afterSwap", {xhr, target: {id: "lab-state", querySelectorAll: () => { throw Error("The outerHTML event target may be detached"); }}});
    assert.equal(state.focused, false, action + " must not scroll to the global notice");
    assert.equal(focused, true, action);
    assert.equal(scrolled, true, action);
    assert.equal(highlighted, true, action);
  }
});

test("validation swaps retain deliberate focus on the error status", () => {
  const {state, fire, status} = harness();
  status.open = true;
  status.classList.add("is-error");
  fire("htmx:afterSwap", {target: {id: "lab-state"}});
  assert.equal(state.focused, true);
  assert.equal(state.focusPreventScroll, true);
});

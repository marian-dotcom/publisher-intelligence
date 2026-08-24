import "@testing-library/jest-dom/vitest";

// jsdom lacks <dialog> methods; provide minimal stubs for component tests.
if (typeof HTMLDialogElement !== "undefined") {
  HTMLDialogElement.prototype.showModal = HTMLDialogElement.prototype.showModal || (() => {});
  HTMLDialogElement.prototype.close = HTMLDialogElement.prototype.close || (() => {});
}

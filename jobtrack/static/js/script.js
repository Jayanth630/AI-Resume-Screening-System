document.addEventListener("click", (event) => {
  const dismissButton = event.target.closest(".flash-dismiss");
  if (dismissButton) {
    const toast = dismissButton.closest(".toast");
    if (toast) {
      toast.classList.add("is-leaving");
      toast.addEventListener("animationend", () => toast.remove(), { once: true });
    } else {
      dismissButton.closest(".flash").remove();
    }
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-confirm-delete]");
  if (form && !window.confirm(`Delete the application for ${form.dataset.confirmDelete}? This cannot be undone.`)) {
    event.preventDefault();
  }
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (event.defaultPrevented || form.dataset.confirmDelete || form.dataset.submitting === "true") {
    return;
  }

  const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
  if (!submitButton) {
    return;
  }

  form.dataset.submitting = "true";
  submitButton.classList.add("is-loading");
  submitButton.setAttribute("aria-disabled", "true");
  submitButton.setAttribute("aria-busy", "true");
});

document.querySelectorAll(".toast").forEach((toast) => {
  let dismissTimer;
  const dismiss = () => {
    toast.classList.add("is-leaving");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
  };
  const scheduleDismiss = () => {
    window.clearTimeout(dismissTimer);
    dismissTimer = window.setTimeout(dismiss, 6500);
  };

  toast.addEventListener("mouseenter", () => window.clearTimeout(dismissTimer));
  toast.addEventListener("mouseleave", scheduleDismiss);
  toast.addEventListener("focusin", () => window.clearTimeout(dismissTimer));
  toast.addEventListener("focusout", scheduleDismiss);
  scheduleDismiss();
});
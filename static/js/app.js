const anchors = document.querySelectorAll('a[href^="#"]');
anchors.forEach((anchor) => {
  anchor.addEventListener("click", (event) => {
    event.preventDefault();
    const target = document.querySelector(anchor.getAttribute("href"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

document.querySelectorAll(".flash-item").forEach((item) => {
  const closeBtn = item.querySelector(".flash-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => item.remove());
  }
});

const loadingOverlay = document.querySelector("#loading-overlay");
document.querySelectorAll("form.processing-form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!form.checkValidity()) {
      return;
    }
    if (loadingOverlay) {
      loadingOverlay.style.display = "flex";
      loadingOverlay.setAttribute("aria-hidden", "false");
    }
  });
});

function showConfirmModal(title, message, onConfirm) {
  const modal = document.getElementById('confirm-modal');
  const titleEl = document.getElementById('confirm-modal-title');
  const messageEl = document.getElementById('confirm-modal-message');
  const submitBtn = document.getElementById('confirm-modal-submit');

  titleEl.textContent = title;
  messageEl.textContent = message;

  submitBtn.onclick = () => {
    hideConfirmModal();
    onConfirm();
  };

  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('modal-open');
}

function hideConfirmModal() {
  const modal = document.getElementById('confirm-modal');
  modal.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('modal-open');
}

window.addEventListener("pageshow", () => {
  hideErrorModal();
  hideConfirmModal();
  if (loadingOverlay) {
    loadingOverlay.style.display = "none";
    loadingOverlay.setAttribute("aria-hidden", "true");
  }
});

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
  hideConfirmModal();
  if (loadingOverlay) {
    loadingOverlay.style.display = "none";
    loadingOverlay.setAttribute("aria-hidden", "true");
  }
});

// Escape text before inserting it with innerHTML (document text, errors, LLM output).
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Render the small Markdown subset LLMs commonly return (**bold**, *italic*,
// `code`, "- " / "* " / "1. " lists, paragraphs). Escapes first, so model
// output can never inject markup.
function renderAnswer(markdown) {
  const inline = (text) =>
    escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");

  const blocks = [];
  let list = null;
  String(markdown ?? "").split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    const item = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      const tag = /^\d/.test(line) ? "ol" : "ul";
      if (!list || list.tag !== tag) {
        list = { tag, items: [] };
        blocks.push(list);
      }
      list.items.push(inline(item[1]));
    } else if (line) {
      list = null;
      const last = blocks[blocks.length - 1];
      if (last && last.tag === "p") {
        last.lines.push(inline(line));
      } else {
        blocks.push({ tag: "p", lines: [inline(line)] });
      }
    } else {
      list = null;
      blocks.push({ tag: "break" });
    }
  });

  return blocks
    .map((b) => {
      if (b.tag === "p") return `<p>${b.lines.join("<br>")}</p>`;
      if (b.tag === "ul" || b.tag === "ol") {
        return `<${b.tag}>${b.items.map((i) => `<li>${i}</li>`).join("")}</${b.tag}>`;
      }
      return "";
    })
    .join("");
}

// Make a contract excerpt readable: escape it, start each numbered clause
// ("9.2 ...") on its own line, and bold section headings ("9. LIMITATION OF LIABILITY").
function formatExcerpt(text) {
  return escapeHtml(text)
    .replace(/(^|\s+)(\d{1,2}\.\s?[A-Z][A-Z &/,'-]{3,}[A-Z])(?=\s|$)/g, (m, pre, heading) =>
      `${pre ? "\n\n" : ""}<strong>${heading}</strong>`)
    .replace(/\s+(\d{1,2}\.\d{1,2})\s(?=\S)/g, "\n$1 ");
}

// Wrap case-insensitive matches of `query` in <mark>, touching only text
// between tags of already-escaped HTML (so markup is never broken).
function highlightMatches(html, query) {
  const q = String(query ?? "").trim();
  if (!q) return html;
  const pattern = new RegExp(escapeHtml(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  return html
    .split(/(<[^>]+>)/)
    .map((part) => (part.startsWith("<") ? part : part.replace(pattern, (m) => `<mark>${m}</mark>`)))
    .join("");
}

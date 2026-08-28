const app = document.getElementById("app");
const searchInput = document.getElementById("search");
const yearFilter = document.getElementById("year-filter");
const coverModal = document.getElementById("cover-modal");
const coverModalImg = document.getElementById("cover-modal-img");
const DEFAULT_YEAR = "2026";
let books = [];

function populateYearFilter() {
  const years = [...new Set(books.map((b) => b.year).filter(Boolean))].sort((a, b) => b - a);
  const options = [`<option value="all">Alla</option>`]
    .concat(years.map((y) => `<option value="${y}">${y}</option>`));
  yearFilter.innerHTML = options.join("");
  yearFilter.value = years.includes(Number(DEFAULT_YEAR)) ? DEFAULT_YEAR : "all";
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function coverSrc(coverUrl) {
  return coverUrl ? "/data/" + coverUrl : "";
}

function renderList() {
  const query = searchInput.value.trim().toLocaleLowerCase("sv-SE");
  const year = yearFilter.value;
  const visible = books
    .filter((b) => !b.hidden)
    .filter((b) => year === "all" || b.year === Number(year))
    .filter((b) => {
      if (!query) return true;
      const haystack = (b.title + " " + (b.authors || []).join(" ")).toLocaleLowerCase("sv-SE");
      return haystack.includes(query);
    });

  const countEl = `<div id="count">${visible.length} böcker</div>`;

  if (!visible.length) {
    app.innerHTML = countEl + `<div class="empty">Inga böcker hittades.</div>`;
    return;
  }

  const cards = visible.map((b) => `
    <a class="card" href="/book/${b.slug}/">
      <div class="cover">${b.cover_url
        ? `<img src="${escapeHtml(coverSrc(b.cover_url))}" alt="" loading="lazy">`
        : escapeHtml(b.title)}</div>
      <div class="title">${escapeHtml(b.title)}</div>
      <div class="meta">${escapeHtml((b.authors || []).join(", "))}</div>
      <div class="meta">${b.year || "?"}</div>
    </a>
  `).join("");

  app.innerHTML = countEl + `<div class="grid">${cards}</div>`;
}

function openCoverModal(src) {
  coverModalImg.src = src;
  coverModal.hidden = false;
}

function closeCoverModal() {
  coverModal.hidden = true;
  coverModalImg.src = "";
}

// Cover-zoom is shared by the list page (never used there today, but harmless)
// and the pre-rendered /book/<slug>/ pages -- wired unconditionally here since
// app.js is loaded by both.
app.addEventListener("click", (e) => {
  const cover = e.target.closest(".cover[data-cover]");
  if (cover) openCoverModal(cover.dataset.cover);
});
app.addEventListener("keydown", (e) => {
  if ((e.key === "Enter" || e.key === " ") && e.target.closest(".cover[data-cover]")) {
    e.preventDefault();
    openCoverModal(e.target.closest(".cover[data-cover]").dataset.cover);
  }
});
coverModal.addEventListener("click", (e) => {
  if (e.target === coverModal || e.target.classList.contains("cover-modal-close")) closeCoverModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !coverModal.hidden) closeCoverModal();
});

// Everything below is the list page only (index.html's #app starts empty;
// a pre-rendered /book/<slug>/ page's #app is already filled with real
// content, so it skips all of this and just gets the cover-modal above).
if (!app.children.length) {
  function route() {
    const hash = location.hash || "#/";
    const yearMatch = hash.match(/^#\/(\d{4})$/);
    if (yearMatch && [...yearFilter.options].some((o) => o.value === yearMatch[1])) {
      yearFilter.value = yearMatch[1];
    }
    renderList();
  }

  window.addEventListener("hashchange", route);
  searchInput.addEventListener("input", route);
  yearFilter.addEventListener("change", () => {
    location.hash = yearFilter.value === "all" ? "#/" : `#/${yearFilter.value}`;
  });

  fetch("/data/books.json")
    .then((r) => r.json())
    .then((data) => {
      books = data;
      populateYearFilter();
      route();
    })
    .catch((err) => {
      app.innerHTML = `<div class="empty">Kunde inte läsa data/books.json. Har du kört <code>python3 cli.py update</code>? (${escapeHtml(String(err))})</div>`;
    });
}

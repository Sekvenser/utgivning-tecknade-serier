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

function sourceLabel(id) {
  return { libris: "Libris", grandocean: "GrandOcean" }[id] || id;
}

const LANGUAGE_LABELS = {
  swe: "Svenska", eng: "Engelska", nor: "Norska", dan: "Danska", fin: "Finska",
  dut: "Nederländska", fre: "Franska", ger: "Tyska", spa: "Spanska", ita: "Italienska",
  cze: "Tjeckiska", ara: "Arabiska", sme: "Nordsamiska",
};

function formatLanguage(language) {
  if (!language) return "";
  return language.split(",").map((code) => LANGUAGE_LABELS[code.trim()] || code.trim()).join(", ");
}

function formatDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("sv-SE", { year: "numeric", month: "long", day: "numeric" });
}

function coverSrc(coverUrl) {
  return coverUrl ? "data/" + coverUrl : "";
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
    <a class="card" href="#/book/${encodeURIComponent(b.id)}">
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

function renderDetail(id) {
  const backHref = yearFilter.value === "all" ? "#/" : `#/${yearFilter.value}`;
  const b = books.find((x) => x.id === id);
  if (!b) {
    app.innerHTML = `<a class="back" href="${backHref}">&larr; Tillbaka</a><div class="empty">Boken hittades inte.</div>`;
    return;
  }

  const links = [];
  if (b.more_info_url) links.push(`<a href="${escapeHtml(b.more_info_url)}" target="_blank" rel="noopener">Mer information</a>`);
  if (b.buy_url) links.push(`<a href="${escapeHtml(b.buy_url)}" target="_blank" rel="noopener">Köp</a>`);
  if (b.source_url) links.push(`<a href="${escapeHtml(b.source_url)}" target="_blank" rel="noopener">Källa (${escapeHtml((b.sources || []).map(sourceLabel).join(", "))})</a>`);
  if (b.bokus_search_url) links.push(`<a href="${escapeHtml(b.bokus_search_url)}" target="_blank" rel="noopener">Sök på Bokus</a>`);

  app.innerHTML = `
    <a class="back" href="${backHref}">&larr; Tillbaka</a>
    <div class="detail-layout">
      <div class="detail">
        <div class="detail-head">
          ${b.cover_url
            ? `<div class="cover" role="button" tabindex="0" aria-label="Visa omslag i fullstorlek" data-cover="${escapeHtml(coverSrc(b.cover_url))}"><img src="${escapeHtml(coverSrc(b.cover_url))}" alt=""></div>`
            : `<div class="cover">${escapeHtml(b.title)}</div>`}
          <div>
            <h2>${escapeHtml(b.title)}</h2>
            <dl>
              <dt>Upphovsperson</dt><dd>${escapeHtml((b.authors || []).join(", ") || "–")}</dd>
              <dt>Förlag</dt><dd>${escapeHtml(b.publisher || "–")}</dd>
              <dt>Utgiven</dt><dd>${b.published_date ? escapeHtml(formatDate(b.published_date)) : escapeHtml(b.published || String(b.year || "") || "–")}</dd>
              <dt>ISBN</dt><dd>${escapeHtml(b.isbn || "–")}</dd>
              <dt>Språk</dt><dd>${escapeHtml(formatLanguage(b.language) || "–")}</dd>
            </dl>
            <div class="links">${links.join(" ")}</div>
          </div>
        </div>
        ${b.description ? `<div class="description">${escapeHtml(b.description)}</div>` : `<p class="empty">Ingen textinformation tillgänglig.</p>`}
      </div>
      <aside class="ad-slot" id="ad-slot" aria-label="Annonsplats">
        <div class="ad-label">Annonser</div>
        <a class="ad-unit" href="https://sekvenser.se" target="_blank" rel="noopener">
          <img src="assets/blurb-news-cropped.png" alt="Sekvenser">
          <p>Sekvenser 2&ndash;3 ute nu. Sveriges enda oberoende tidskrift om tecknade serier och sekventiell konst. Köp den på sekvenser.se</p>
        </a>
        <a class="ad-unit ad-unit-text" href="mailto:mikkeschiren@gmail.com">
          Vill du annonsera här? Kontakta mikkeschiren@gmail.com
        </a>
      </aside>
    </div>
  `;
}

function openCoverModal(src) {
  coverModalImg.src = src;
  coverModal.hidden = false;
}

function closeCoverModal() {
  coverModal.hidden = true;
  coverModalImg.src = "";
}

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

function route() {
  closeCoverModal();
  const hash = location.hash || "#/";
  const bookMatch = hash.match(/^#\/book\/(.+)$/);
  const yearMatch = hash.match(/^#\/(\d{4})$/);
  if (bookMatch) {
    renderDetail(decodeURIComponent(bookMatch[1]));
  } else {
    if (yearMatch && [...yearFilter.options].some((o) => o.value === yearMatch[1])) {
      yearFilter.value = yearMatch[1];
    }
    renderList();
  }
}

window.addEventListener("hashchange", route);
function backToListThenRoute() {
  if (location.hash.startsWith("#/book/")) {
    location.hash = yearFilter.value === "all" ? "#/" : `#/${yearFilter.value}`;
  } else {
    route();
  }
}
searchInput.addEventListener("input", backToListThenRoute);
yearFilter.addEventListener("change", () => {
  location.hash = yearFilter.value === "all" ? "#/" : `#/${yearFilter.value}`;
});

fetch("data/books.json")
  .then((r) => r.json())
  .then((data) => {
    books = data;
    populateYearFilter();
    route();
  })
  .catch((err) => {
    app.innerHTML = `<div class="empty">Kunde inte läsa data/books.json. Har du kört <code>python3 cli.py update</code>? (${escapeHtml(String(err))})</div>`;
  });

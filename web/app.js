const app = document.getElementById("app");
const searchInput = document.getElementById("search");
let books = [];

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function sourceLabel(id) {
  return { libris: "Libris", grandocean: "GrandOcean" }[id] || id;
}

function coverSrc(coverUrl) {
  return coverUrl ? "../data/" + coverUrl : "";
}

function renderList() {
  const query = searchInput.value.trim().toLocaleLowerCase("sv-SE");
  const visible = books
    .filter((b) => !b.hidden)
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
  const b = books.find((x) => x.id === id);
  if (!b) {
    app.innerHTML = `<a class="back" href="#/">&larr; Tillbaka</a><div class="empty">Boken hittades inte.</div>`;
    return;
  }

  const links = [];
  if (b.source_url) links.push(`<a href="${escapeHtml(b.source_url)}" target="_blank" rel="noopener">Källa (${escapeHtml((b.sources || []).map(sourceLabel).join(", "))})</a>`);
  if (b.bokus_search_url) links.push(`<a href="${escapeHtml(b.bokus_search_url)}" target="_blank" rel="noopener">Sök på Bokus</a>`);

  app.innerHTML = `
    <a class="back" href="#/">&larr; Tillbaka</a>
    <div class="detail">
      <div class="detail-head">
        <div class="cover">${b.cover_url
          ? `<img src="${escapeHtml(coverSrc(b.cover_url))}" alt="">`
          : escapeHtml(b.title)}</div>
        <div>
          <h2>${escapeHtml(b.title)}</h2>
          <dl>
            <dt>Upphovsperson</dt><dd>${escapeHtml((b.authors || []).join(", ") || "–")}</dd>
            <dt>Förlag</dt><dd>${escapeHtml(b.publisher || "–")}</dd>
            <dt>Utgiven</dt><dd>${escapeHtml(b.published || String(b.year || "") || "–")}</dd>
            <dt>ISBN</dt><dd>${escapeHtml(b.isbn || "–")}</dd>
            <dt>Språk</dt><dd>${escapeHtml(b.language || "–")}</dd>
          </dl>
          <div class="links">${links.join(" ")}</div>
        </div>
      </div>
      ${b.description ? `<div class="description">${escapeHtml(b.description)}</div>` : `<p class="empty">Ingen textinformation tillgänglig.</p>`}
    </div>
  `;
}

function route() {
  const hash = location.hash || "#/";
  const bookMatch = hash.match(/^#\/book\/(.+)$/);
  if (bookMatch) {
    renderDetail(decodeURIComponent(bookMatch[1]));
  } else {
    renderList();
  }
}

window.addEventListener("hashchange", route);
searchInput.addEventListener("input", () => {
  if (location.hash.startsWith("#/book/")) location.hash = "#/";
  else route();
});

fetch("../data/books.json")
  .then((r) => r.json())
  .then((data) => {
    books = data;
    route();
  })
  .catch((err) => {
    app.innerHTML = `<div class="empty">Kunde inte läsa data/books.json. Har du kört <code>python3 cli.py update</code>? (${escapeHtml(String(err))})</div>`;
  });

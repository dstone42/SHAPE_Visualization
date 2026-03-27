from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from .models import SourceRecord, ValidationWarning


def publish_site(
    records: list[SourceRecord],
    warnings: list[ValidationWarning],
    output_dir: Path,
    generated_at: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset = {
        "generated_at": generated_at,
        "records": [record.to_dict() for record in records],
        "warnings": [warning.to_dict() for warning in warnings],
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(dataset, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "styles.css").write_text(_styles(), encoding="utf-8")
    (output_dir / "app.js").write_text(_app_js(), encoding="utf-8")
    embedded_json = json.dumps(dataset, indent=2).replace("</", "<\\/")
    (output_dir / "index.html").write_text(
        _site_html(generated_at, embedded_json),
        encoding="utf-8",
    )


def publish_validation_report(
    warnings: list[ValidationWarning], output_path: Path, generated_at: str
) -> None:
    rows = []
    for warning in warnings:
        details = html.escape(json.dumps(warning.details, sort_keys=True))
        rows.append(
            "<tr>"
            f"<td>{html.escape(warning.severity)}</td>"
            f"<td>{html.escape(warning.code)}</td>"
            f"<td>{html.escape(warning.source_id)}</td>"
            f"<td>{html.escape(warning.field or '')}</td>"
            f"<td>{html.escape(warning.message)}</td>"
            f"<td><code>{details}</code></td>"
            "</tr>"
        )
    body = "\n".join(rows) if rows else "<tr><td colspan='6'>No warnings.</td></tr>"
    output_path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>SHAPE Validation Report</title>
  <style>
    body {{
      font-family: "Avenir Next", Avenir, "Segoe UI", sans-serif;
      margin: 32px;
      color: #182229;
      background: linear-gradient(180deg, #f7f1e8 0%, #fdfcf9 100%);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #fffef8;
      border: 1px solid #d9d0c2;
    }}
    th, td {{
      text-align: left;
      padding: 12px;
      border-bottom: 1px solid #ece1d0;
      vertical-align: top;
    }}
    th {{
      background: #fff4df;
    }}
    code {{
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <h1>SHAPE Validation Report</h1>
  <p>Generated {html.escape(generated_at)}.</p>
  <table>
    <thead>
      <tr>
        <th>Severity</th>
        <th>Code</th>
        <th>Source</th>
        <th>Field</th>
        <th>Message</th>
        <th>Details</th>
      </tr>
    </thead>
    <tbody>
      {body}
    </tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def generated_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _site_html(generated_at: str, embedded_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SHAPE Metadata Atlas</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="page-shell">
    <section class="hero">
      <p class="eyebrow">SHAPE Metadata Atlas</p>
      <h1>SHAPE data source domains, freshness, and geographies.</h1>
      <p class="hero-copy">
        Pulls metadata from multiple sources to provide an updated view of the data in SHAPE, what domains are covered, 
        what geographic levels are included, and how frequently sources are updated.
      </p>
      <dl class="hero-stats" id="heroStats"></dl>
      <p class="stamp">Updated <span id="generatedAt">{html.escape(generated_at)}</span></p>
    </section>

    <section class="summary-strip" id="warningStrip"></section>

    <section class="controls">
      <div class="controls-top">
        <div class="control-heading">
          <label for="searchInput">Search</label>
          <p class="results-meta" id="resultsMeta"></p>
        </div>
        <div class="view-switcher">
          <p class="view-label">View</p>
          <div class="view-toggle">
            <button type="button" data-view="cards" class="is-active">Cards</button>
            <button type="button" data-view="table">Table</button>
          </div>
        </div>
      </div>
      <div class="search-row">
        <div class="control-group">
          <input id="searchInput" type="search" placeholder="Filter by source, notes, or domain">
        </div>
        <div class="toolbar-actions">
          <details class="filter-drawer filter-drawer--inline" id="filterDrawer">
            <summary>
              <span>Refine Results</span>
              <span class="filter-count hidden" id="activeFilterCount"></span>
            </summary>
            <div class="filter-drawer__panel">
              <div class="filter-drawer__header">
                <div>
                  <p class="eyebrow">Refine Results</p>
                  <h2>Filter sources</h2>
                </div>
                <button type="button" class="text-button" id="clearFilters">Clear all</button>
              </div>
              <p class="filter-summary" id="filterSummary"></p>
              <section class="filters" id="filters"></section>
            </div>
          </details>
        </div>
      </div>
    </section>

    <section id="cardView" class="card-grid" aria-live="polite"></section>
    <section id="tableView" class="table-shell hidden" aria-live="polite"></section>
  </main>

  <script id="shapeMetadata" type="application/json">{embedded_json}</script>
  <script src="app.js"></script>
</body>
</html>
"""


def _styles() -> str:
    return """\
:root {
  --ink: #172328;
  --muted: #5e6a6a;
  --paper: #f9f6ef;
  --panel: rgba(255, 252, 246, 0.9);
  --line: #d9d0c2;
  --accent: #005f73;
  --accent-soft: #d6eceb;
  --warning: #9c3d1d;
  --warning-soft: #f8dfd2;
  --shadow: 0 18px 40px rgba(58, 49, 35, 0.08);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  color: var(--ink);
  font-family: "Avenir Next", Avenir, "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at top left, rgba(0, 95, 115, 0.16), transparent 26%),
    radial-gradient(circle at top right, rgba(238, 155, 0, 0.12), transparent 18%),
    linear-gradient(180deg, #efe4d1 0%, var(--paper) 38%, #fffdf9 100%);
  min-height: 100vh;
}

.page-shell {
  width: min(1200px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 40px 0 64px;
}

.hero,
.controls,
.summary-strip,
.table-shell {
  background: var(--panel);
  border: 1px solid rgba(217, 208, 194, 0.8);
  border-radius: 24px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(10px);
}

.hero {
  padding: 32px;
}

.eyebrow {
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.78rem;
  color: var(--accent);
  margin: 0 0 12px;
}

.hero h1 {
  margin: 0;
  max-width: 20ch;
  font-size: clamp(2.4rem, 5vw, 4.4rem);
  line-height: 0.95;
}

.hero-copy {
  max-width: 64ch;
  color: var(--muted);
  font-size: 1.05rem;
  line-height: 1.6;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-top: 24px;
}

.hero-stats div {
  padding: 16px;
  background: rgba(255, 255, 255, 0.55);
  border-radius: 16px;
  border: 1px solid rgba(217, 208, 194, 0.7);
}

.hero-stats dt {
  color: var(--muted);
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.hero-stats dd {
  margin: 8px 0 0;
  font-size: 1.6rem;
  font-weight: 700;
}

.stamp {
  margin-top: 20px;
  color: var(--muted);
}

.controls {
  margin-top: 20px;
  padding: 20px 24px;
  display: grid;
  gap: 14px;
  position: relative;
  z-index: 2;
}

.controls-top,
.search-row {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.control-heading {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control-heading label {
  display: block;
  font-weight: 600;
}

.control-group {
  min-width: 0;
  flex: 1 1 460px;
}

.control-group input {
  width: 100%;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
  font: inherit;
}

.results-meta {
  margin: 0;
  color: var(--muted);
  font-size: 0.94rem;
  line-height: 1.4;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.view-switcher {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.view-label {
  margin: 0;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.view-toggle {
  display: inline-flex;
  gap: 8px;
}

.view-toggle button,
.chip,
.filter-drawer summary {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--ink);
  padding: 10px 14px;
  font: inherit;
  cursor: pointer;
}

.filter-drawer {
  position: relative;
}

.filter-drawer--inline summary {
  min-height: 48px;
  padding-inline: 16px;
  background: rgba(214, 236, 235, 0.45);
  border-color: rgba(0, 95, 115, 0.14);
}

.filter-drawer summary {
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.filter-drawer summary::-webkit-details-marker {
  display: none;
}

.filter-drawer[open] summary {
  background: var(--accent-soft);
  border-color: rgba(0, 95, 115, 0.16);
  color: var(--accent);
}

.filter-count {
  min-width: 1.5rem;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-size: 0.8rem;
  text-align: center;
}

.filter-drawer__panel {
  position: absolute;
  top: calc(100% + 14px);
  right: 0;
  width: min(540px, calc(100vw - 56px));
  max-height: min(70vh, 720px);
  overflow: auto;
  padding: 20px;
  background: rgba(255, 252, 246, 0.96);
  border: 1px solid rgba(217, 208, 194, 0.9);
  border-radius: 24px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(12px);
  z-index: 10;
}

.filter-drawer__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.filter-drawer__header h2 {
  margin: 4px 0 0;
  font-size: 1.18rem;
}

.filter-summary {
  margin: 12px 0 18px;
  color: var(--muted);
  line-height: 1.6;
}

.text-button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--accent);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.text-button:disabled {
  color: var(--line);
  cursor: default;
}

.view-toggle button.is-active,
.chip.is-active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.filters {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.filter-section {
  padding: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(217, 208, 194, 0.72);
  border-radius: 18px;
}

.filter-section h2 {
  margin: 0 0 12px;
  font-size: 1rem;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  padding: 8px 12px;
  font-size: 0.95rem;
}

.summary-strip {
  margin-top: 20px;
  padding: 18px 24px;
  color: var(--warning);
  background: linear-gradient(90deg, rgba(248, 223, 210, 0.9), rgba(255, 247, 235, 0.9));
}

.summary-strip.hidden {
  display: none;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 18px;
  margin-top: 24px;
}

.card {
  padding: 24px;
  background: rgba(255, 255, 255, 0.78);
  border-radius: 22px;
  border: 1px solid rgba(217, 208, 194, 0.9);
  box-shadow: var(--shadow);
}

.card h2 {
  margin: 0;
  font-size: 1.4rem;
}

.card p {
  line-height: 1.6;
}

.card-description {
  margin: 12px 0 0;
}

.card-description.is-collapsed {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
}

.card-description-toggle {
  margin-top: 8px;
  margin-bottom: 20px;
}

.badge-row,
.meta-list,
.provenance-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.badge,
.meta-pill,
.provenance-pill {
  border-radius: 999px;
  padding: 8px 12px;
  font-size: 0.92rem;
}

.badge {
  background: var(--accent-soft);
  color: var(--accent);
}

.meta-pill {
  background: rgba(238, 155, 0, 0.12);
}

.provenance-pill {
  background: rgba(23, 35, 40, 0.06);
  color: var(--muted);
}

.section-label {
  margin: 18px 0 10px;
  font-size: 0.84rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.card ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.6;
}

.detail-stack {
  display: grid;
  gap: 14px;
}

.details-meta {
  margin: 0;
  color: var(--muted);
  font-size: 0.92rem;
}

.card-details {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid rgba(217, 208, 194, 0.85);
}

.card-details summary {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  font-weight: 600;
  list-style: none;
}

.card-details summary::-webkit-details-marker {
  display: none;
}

.card-details[open] summary {
  margin-bottom: 14px;
}

.card-details__body {
  display: grid;
  gap: 16px;
}

.table-shell {
  margin-top: 24px;
  position: relative;
  z-index: 1;
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 14px 12px;
  border-bottom: 1px solid rgba(217, 208, 194, 0.75);
  text-align: left;
  vertical-align: top;
}

th {
  background: rgba(255, 244, 223, 0.72);
}

.hidden {
  display: none;
}

.empty-state {
  padding: 28px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.62);
  border: 1px dashed var(--line);
  color: var(--muted);
}

@media (max-width: 720px) {
  .page-shell {
    width: min(100vw - 20px, 1200px);
    padding-top: 20px;
  }

  .hero,
  .controls,
  .summary-strip,
  .card {
    border-radius: 20px;
  }

  .controls {
    align-items: stretch;
  }

  .controls-top,
  .search-row {
    align-items: stretch;
  }

  .results-meta {
    text-align: left;
  }

  .view-switcher {
    align-items: flex-start;
  }

  .toolbar-actions {
    width: 100%;
  }

  .filter-drawer,
  .filter-drawer summary {
    width: 100%;
  }

  .filter-drawer summary {
    justify-content: space-between;
  }

  .filter-drawer__panel {
    left: 0;
    right: auto;
    width: min(100%, calc(100vw - 40px));
  }

  .filters {
    grid-template-columns: 1fr;
  }
}
"""


def _app_js() -> str:
    return """\
const state = {
  dataset: null,
  search: "",
  view: "cards",
  filters: {
    domains: new Set(),
    geographic_levels: new Set(),
    update_frequency: new Set(),
    source_type: new Set(),
    review_status: new Set(),
  },
};

async function boot() {
  const inlineData = document.getElementById("shapeMetadata");
  let dataset;
  if (inlineData && inlineData.textContent.trim()) {
    dataset = JSON.parse(inlineData.textContent);
  } else {
    const response = await fetch("metadata.json");
    dataset = await response.json();
  }
  state.dataset = dataset;
  renderShell(dataset);
  renderFilters(dataset.records);
  bindControls();
  renderResults();
}

function bindControls() {
  document.getElementById("searchInput").addEventListener("input", (event) => {
    state.search = event.target.value.trim().toLowerCase();
    renderResults();
  });

  document.querySelectorAll(".view-toggle button").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      document.querySelectorAll(".view-toggle button").forEach((candidate) => {
        candidate.classList.toggle("is-active", candidate === button);
      });
      renderResults();
    });
  });

  document.getElementById("clearFilters").addEventListener("click", () => {
    clearAllFilters();
  });

  const filterDrawer = document.getElementById("filterDrawer");
  document.addEventListener("click", (event) => {
    if (filterDrawer.open && !filterDrawer.contains(event.target)) {
      filterDrawer.open = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      filterDrawer.open = false;
    }
  });

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-description-toggle]");
    if (!toggle) {
      return;
    }
    const targetId = toggle.getAttribute("data-description-toggle");
    const description = document.getElementById(targetId);
    if (!description) {
      return;
    }
    const isCollapsed = description.classList.toggle("is-collapsed");
    toggle.textContent = isCollapsed ? "Show more" : "Show less";
    toggle.setAttribute("aria-expanded", String(!isCollapsed));
  });
}

function renderShell(dataset) {
  const records = dataset.records;
  const warnings = dataset.warnings;
  const domains = collectFilterValues(records, "domains");
  const geographies = collectFilterValues(records, "geographic_levels");
  const stats = [
    ["Sources", records.length],
    ["Domains", domains.length],
    ["Geographies", geographies.length],
    ["Warnings", warnings.length],
  ];

  const statsRoot = document.getElementById("heroStats");
  statsRoot.innerHTML = stats
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
    .join("");

  const warningStrip = document.getElementById("warningStrip");
  if (warnings.length === 0) {
    warningStrip.classList.add("hidden");
    return;
  }
  const draftWarnings = warnings.filter((warning) => warning.severity !== "info").length;
  warningStrip.classList.remove("hidden");
  warningStrip.innerHTML =
    `<strong>${draftWarnings} review warning${draftWarnings === 1 ? "" : "s"}</strong> ` +
    `were generated in this build. Open the validation report artifact for field-level details.`;
}

function renderFilters(records) {
  const filterRoot = document.getElementById("filters");
  const sections = [
    ["domains", "Domains"],
    ["geographic_levels", "Geography"],
    ["update_frequency", "Update Frequency"],
    ["source_type", "Source Type"],
    ["review_status", "Review Status"],
  ];

  filterRoot.innerHTML = sections
    .map(([field, label]) => {
      const values = collectFilterValues(records, field);
      const chips = values
        .map((value) => {
          const safe = escapeHtml(value);
          return `<button class="chip" type="button" data-field="${field}" data-value="${safe}">${safe}</button>`;
        })
        .join("");
      return `<div class="filter-section"><h2>${label}</h2><div class="chip-row">${chips}</div></div>`;
    })
    .join("");

  filterRoot.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const { field, value } = chip.dataset;
      const bucket = state.filters[field];
      if (bucket.has(value)) {
        bucket.delete(value);
      } else {
        bucket.add(value);
      }
      chip.classList.toggle("is-active", bucket.has(value));
      renderResults();
    });
  });
}

function renderResults() {
  const records = state.dataset.records.filter(matchesFilters);
  renderToolbarStatus(records.length, state.dataset.records.length);

  const cardRoot = document.getElementById("cardView");
  const tableRoot = document.getElementById("tableView");

  document.getElementById("cardView").classList.toggle("hidden", state.view !== "cards");
  document.getElementById("tableView").classList.toggle("hidden", state.view !== "table");

  if (records.length === 0) {
    const empty = `<div class="empty-state">No sources match the current filters.</div>`;
    cardRoot.innerHTML = empty;
    tableRoot.innerHTML = empty;
    return;
  }

  cardRoot.innerHTML = records.map(renderCard).join("");
  tableRoot.innerHTML = renderTable(records);
}

function clearAllFilters() {
  Object.values(state.filters).forEach((bucket) => bucket.clear());
  document.querySelectorAll(".chip.is-active").forEach((chip) => chip.classList.remove("is-active"));
  renderResults();
}

function renderToolbarStatus(resultCount, totalCount) {
  const selectedCount = countSelectedFilters();
  const selectedGroups = Object.values(state.filters).filter((bucket) => bucket.size > 0).length;
  const refinements = [];

  if (state.search) {
    refinements.push("a search term");
  }
  if (selectedCount > 0) {
    refinements.push(`${selectedCount} active filter${selectedCount === 1 ? "" : "s"}`);
  }

  const resultsMeta = document.getElementById("resultsMeta");
  resultsMeta.textContent =
    `Showing ${resultCount} of ${totalCount} sources` +
    `${refinements.length ? ` with ${refinements.join(" and ")}` : ""}.`;

  const countBadge = document.getElementById("activeFilterCount");
  countBadge.textContent = String(selectedCount);
  countBadge.classList.toggle("hidden", selectedCount === 0);

  const clearButton = document.getElementById("clearFilters");
  clearButton.disabled = selectedCount === 0;

  const filterSummary = document.getElementById("filterSummary");
  filterSummary.textContent = selectedCount === 0
    ? "Keep the main view focused, then open filters when you need to narrow by domain, geography, update cadence, source type, or review status."
    : `${selectedCount} filter${selectedCount === 1 ? "" : "s"} selected across ${selectedGroups} filter ${selectedGroups === 1 ? "group" : "groups"}.`;
}

function countSelectedFilters() {
  return Object.values(state.filters).reduce((total, bucket) => total + bucket.size, 0);
}

function matchesFilters(record) {
  const haystack = [
    record.display_name,
    record.short_description,
    ...(record.domains || []),
    ...(record.notes || []),
    ...(record.caveats || []),
  ]
    .join(" ")
    .toLowerCase();

  if (state.search && !haystack.includes(state.search)) {
    return false;
  }

  return Object.entries(state.filters).every(([field, values]) => {
    if (values.size === 0) {
      return true;
    }
    const candidateValues = Array.isArray(record[field])
      ? record[field]
      : record[field]
        ? [record[field]]
        : [];
    return [...values].some((selected) => candidateValues.includes(selected));
  });
}

function renderCard(record) {
  const yearRange = record.available_years && record.available_years.length
    ? `${record.year_start} to ${record.year_end}`
    : "Unavailable";
  const detailSummary = buildDetailSummary(record);
  const description = record.short_description || "No description yet.";
  const descriptionId = `description-${escapeHtml(record.source_id)}`;
  const shouldClamp = shouldClampDescription(description);

  return `
    <article class="card">
      <p class="eyebrow">${escapeHtml(record.source_type || "source")}</p>
      <h2>${escapeHtml(record.display_name || record.source_id)}</h2>
      <p id="${descriptionId}" class="card-description${shouldClamp ? " is-collapsed" : ""}">${escapeHtml(description)}</p>
      ${shouldClamp ? `<button type="button" class="text-button card-description-toggle" data-description-toggle="${descriptionId}" aria-expanded="false">Show more</button>` : ""}
      <div class="badge-row">
        ${(record.domains || []).map((domain) => `<span class="badge">${escapeHtml(domain)}</span>`).join("")}
      </div>

      <p class="section-label">Coverage</p>
      <div class="meta-list">
        <span class="meta-pill">Frequency: ${escapeHtml(record.update_frequency || "Unknown")}</span>
        <span class="meta-pill">Years: ${escapeHtml(yearRange)}</span>
        <span class="meta-pill">Status: ${escapeHtml(record.review_status || "draft")}</span>
      </div>

      <p class="section-label">Geography</p>
      <div class="meta-list">
        ${(record.geographic_levels || []).map((level) => `<span class="meta-pill">${escapeHtml(level)}</span>`).join("")}
      </div>

      ${detailSummary ? `
        <details class="card-details">
          <summary>
            <span>Open details</span>
            <span class="details-meta">${escapeHtml(detailSummary)}</span>
          </summary>
          <div class="card-details__body">
            ${renderDetailSections(record)}
          </div>
        </details>
      ` : ""}
    </article>
  `;
}

function renderDetailSections(record) {
  const sections = [];
  const provenanceEntries = Object.entries(record.provenance || {});

  if (provenanceEntries.length) {
    sections.push(`
      <section>
        <p class="section-label">Provenance</p>
        <div class="provenance-list">
          ${provenanceEntries
            .map(([field, details]) => `<span class="provenance-pill">${escapeHtml(field)}: ${escapeHtml(details.source)}</span>`)
            .join("")}
        </div>
      </section>
    `);
  }

  sections.push(renderTextList("Notes", record.notes));
  sections.push(renderTextList("Caveats", record.caveats));

  if (record.year_notes) {
    sections.push(`<section><p class="section-label">Year Notes</p><p>${escapeHtml(record.year_notes)}</p></section>`);
  }

  sections.push(`
    <section>
      <p class="section-label">Last Refresh</p>
      <p>${escapeHtml(record.last_observed_at || "Not observed yet")}</p>
    </section>
  `);

  return `<div class="detail-stack">${sections.filter(Boolean).join("")}</div>`;
}

function renderTextList(label, values) {
  if (!values || values.length === 0) {
    return "";
  }
  return `<section><p class="section-label">${escapeHtml(label)}</p><ul>${values
    .map((value) => `<li>${escapeHtml(value)}</li>`)
    .join("")}</ul></section>`;
}

function buildDetailSummary(record) {
  const summaryBits = [];
  if (record.notes && record.notes.length) {
    summaryBits.push(`${record.notes.length} note${record.notes.length === 1 ? "" : "s"}`);
  }
  if (record.caveats && record.caveats.length) {
    summaryBits.push(`${record.caveats.length} caveat${record.caveats.length === 1 ? "" : "s"}`);
  }
  if (record.year_notes) {
    summaryBits.push("year notes");
  }
  if (record.provenance && Object.keys(record.provenance).length) {
    summaryBits.push("provenance");
  }
  if (record.last_observed_at) {
    summaryBits.push("refresh info");
  }
  return summaryBits.join(" | ");
}

function shouldClampDescription(value) {
  if (!value) {
    return false;
  }
  return value.length > 280 || value.includes("\\n");
}

function renderTable(records) {
  const rows = records
    .map((record) => {
      const years = record.available_years && record.available_years.length
        ? `${record.year_start}-${record.year_end}`
        : "Unavailable";
      return `
        <tr>
          <td>${escapeHtml(record.display_name || record.source_id)}</td>
          <td>${escapeHtml(record.update_frequency || "Unknown")}</td>
          <td>${escapeHtml(years)}</td>
          <td>${escapeHtml((record.domains || []).join(", "))}</td>
          <td>${escapeHtml((record.geographic_levels || []).join(", "))}</td>
          <td>${escapeHtml(record.review_status || "draft")}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <table>
      <thead>
        <tr>
          <th>Source</th>
          <th>Update Frequency</th>
          <th>Years</th>
          <th>Domains</th>
          <th>Geography</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function collectFilterValues(records, field) {
  const values = new Set();
  records.forEach((record) => {
    const candidate = record[field];
    if (Array.isArray(candidate)) {
      candidate.forEach((value) => value && values.add(value));
    } else if (candidate) {
      values.add(candidate);
    }
  });
  return [...values].sort((left, right) => left.localeCompare(right));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

boot().catch((error) => {
  const warningStrip = document.getElementById("warningStrip");
  warningStrip.classList.remove("hidden");
  warningStrip.textContent = `Failed to load SHAPE metadata: ${error.message}`;
});
"""

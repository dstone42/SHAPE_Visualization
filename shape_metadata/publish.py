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
      <h1>Data source coverage, freshness, and provenance in one place.</h1>
      <p class="hero-copy">
        This site is generated from the SHAPE metadata pipeline. Filters and source cards are built directly
        from the published dataset so the interface stays aligned with the underlying registry.
      </p>
      <dl class="hero-stats" id="heroStats"></dl>
      <p class="stamp">Generated <span id="generatedAt">{html.escape(generated_at)}</span></p>
    </section>

    <section class="controls">
      <div class="control-group">
        <label for="searchInput">Search</label>
        <input id="searchInput" type="search" placeholder="Filter by source, notes, or domain">
      </div>
      <div class="view-toggle">
        <button type="button" data-view="cards" class="is-active">Cards</button>
        <button type="button" data-view="table">Table</button>
      </div>
    </section>

    <section class="filters" id="filters"></section>

    <section class="summary-strip" id="warningStrip"></section>

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
.filters,
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
  max-width: 12ch;
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
  display: flex;
  gap: 16px;
  justify-content: space-between;
  align-items: end;
  flex-wrap: wrap;
}

.control-group {
  flex: 1 1 360px;
}

.control-group label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
}

.control-group input {
  width: 100%;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.88);
  font: inherit;
}

.view-toggle {
  display: inline-flex;
  gap: 8px;
}

.view-toggle button,
.chip {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--ink);
  padding: 10px 14px;
  font: inherit;
  cursor: pointer;
}

.view-toggle button.is-active,
.chip.is-active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.filters {
  margin-top: 20px;
  padding: 22px 24px;
}

.filter-section + .filter-section {
  margin-top: 18px;
}

.filter-section h2 {
  margin: 0 0 12px;
  font-size: 1rem;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
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

.table-shell {
  margin-top: 24px;
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
  .filters,
  .summary-strip,
  .card {
    border-radius: 20px;
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
  bindControls();
  renderFilters(dataset.records);
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

  return `
    <article class="card">
      <p class="eyebrow">${escapeHtml(record.source_type || "source")}</p>
      <h2>${escapeHtml(record.display_name || record.source_id)}</h2>
      <p>${escapeHtml(record.short_description || "No description yet.")}</p>
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

      <p class="section-label">Provenance</p>
      <div class="provenance-list">
        ${Object.entries(record.provenance || {})
          .map(([field, details]) => `<span class="provenance-pill">${escapeHtml(field)}: ${escapeHtml(details.source)}</span>`)
          .join("")}
      </div>

      ${renderTextList("Notes", record.notes)}
      ${renderTextList("Caveats", record.caveats)}
      ${record.year_notes ? `<p class="section-label">Year Notes</p><p>${escapeHtml(record.year_notes)}</p>` : ""}
      <p class="section-label">Last Refresh</p>
      <p>${escapeHtml(record.last_observed_at || "Not observed yet")}</p>
    </article>
  `;
}

function renderTextList(label, values) {
  if (!values || values.length === 0) {
    return "";
  }
  return `<p class="section-label">${escapeHtml(label)}</p><ul>${values
    .map((value) => `<li>${escapeHtml(value)}</li>`)
    .join("")}</ul>`;
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

const SHOW_REVIEW_WARNING_STRIP = false;

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
  if (!warningStrip || !SHOW_REVIEW_WARNING_STRIP) {
    return;
  }
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
  return value.length > 280 || value.includes("\n");
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

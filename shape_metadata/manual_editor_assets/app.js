const EMPTY_RECORD = {
  source_id: "",
  display_name: "",
  short_description: "",
  source_type: "",
  update_frequency: "",
  domains: [],
  geographic_levels: [],
  available_years: [],
  year_notes: "",
  source_systems: [],
  confidence: "",
  review_status: "draft",
  last_reviewed_at: "",
  notes: [],
  caveats: [],
  source_documents: [],
};

const state = {
  context: null,
  search: "",
  selectedSourceId: "",
  dirty: false,
  sourceDocumentDrafts: {},
};

window.addEventListener("beforeunload", (event) => {
  if (!state.dirty) {
    return;
  }
  event.preventDefault();
  event.returnValue = "";
});

async function boot() {
  bindShell();
  await reloadContext();
}

function bindShell() {
  document.getElementById("sourceSearch").addEventListener("input", (event) => {
    state.search = event.target.value.trim().toLowerCase();
    renderLists();
  });

  document.getElementById("newRecordButton").addEventListener("click", () => {
    createBlankRecord();
  });

  document.getElementById("reloadButton").addEventListener("click", async () => {
    await reloadContext(state.selectedSourceId);
    setSaveStatus("Reloaded from disk.", "success");
  });

  document.getElementById("saveButton").addEventListener("click", async () => {
    await saveRegistry();
  });

  document.getElementById("duplicateButton").addEventListener("click", () => {
    duplicateSelectedRecord();
  });

  document.getElementById("deleteButton").addEventListener("click", () => {
    deleteSelectedRecord();
  });

  document.getElementById("seedButton").addEventListener("click", () => {
    replaceSelectedWithMergedContext();
  });

  document.getElementById("addDocumentButton").addEventListener("click", () => {
    addDocument();
  });
}

async function reloadContext(preferredSourceId = "") {
  const response = await fetch("/api/context", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unable to load editor context.");
  }

  state.context = payload;
  state.dirty = false;
  state.sourceDocumentDrafts = {};

  const manualRecords = getReviewedRecords();
  const manualIds = new Set(manualRecords.map((record) => record.source_id));
  const selectedStillExists = preferredSourceId && manualIds.has(preferredSourceId);
  if (selectedStillExists) {
    state.selectedSourceId = preferredSourceId;
  } else {
    state.selectedSourceId = manualRecords[0]?.source_id || "";
  }

  renderAll();
}

function renderAll() {
  renderLoadErrors();
  renderLists();
  renderEditor();
  renderContext();
}

function renderLoadErrors() {
  const root = document.getElementById("loadErrors");
  const errors = state.context?.load_errors || [];
  if (!errors.length) {
    root.classList.add("hidden");
    root.innerHTML = "";
    return;
  }

  root.classList.remove("hidden");
  root.innerHTML = errors
    .map(
      (error) =>
        `<div class="error-card"><strong>${escapeHtml(titleCase(error.source))} context</strong><br>${escapeHtml(
          error.message,
        )}</div>`,
    )
    .join("");
}

function renderLists() {
  const manualRecords = filterRecords(getReviewedRecords());
  const suggestions = filterRecords(getSuggestionRecords());

  document.getElementById("manualCount").textContent = String(manualRecords.length);
  document.getElementById("suggestionCount").textContent = String(suggestions.length);

  const manualList = document.getElementById("manualList");
  manualList.innerHTML = manualRecords.length
    ? manualRecords.map((record) => renderSourceItem(record, false)).join("")
    : `<div class="empty-panel">No manual records match the current search.</div>`;

  manualList.querySelectorAll("[data-select-source]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedSourceId = button.dataset.selectSource || "";
      renderAll();
    });
  });

  const suggestionList = document.getElementById("suggestionList");
  suggestionList.innerHTML = suggestions.length
    ? suggestions.map((record) => renderSourceItem(record, true)).join("")
    : `<div class="empty-panel">Nothing upstream is waiting on a manual entry right now.</div>`;

  suggestionList.querySelectorAll("[data-add-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      addSuggestionRecord(button.dataset.addSuggestion || "");
    });
  });
}

function renderSourceItem(record, isSuggestion) {
  const title = record.display_name || record.source_id;
  const domains = (record.domains || []).slice(0, 3).map((domain) => escapeHtml(domain)).join(", ");
  const sourceId = escapeHtml(record.source_id);
  const chips = buildStatusChips(record.source_id, isSuggestion);
  const selected = !isSuggestion && record.source_id === state.selectedSourceId;
  const buttonAttr = isSuggestion ? `data-add-suggestion="${sourceId}"` : `data-select-source="${sourceId}"`;
  const actionText = isSuggestion ? "Add to manual registry" : "Open record";

  return `
    <button type="button" class="source-item${selected ? " is-active" : ""}${isSuggestion ? " is-suggestion" : ""}" ${buttonAttr}>
      <h4>${escapeHtml(title)}</h4>
      <p>${sourceId}</p>
      <div class="source-meta">${chips}</div>
      ${domains ? `<p class="context-copy">${escapeHtml(domains)}</p>` : ""}
      <div class="source-meta"><span class="status-chip">${actionText}</span></div>
    </button>
  `;
}

function renderEditor() {
  const record = getSelectedRecord();
  const title = record ? record.display_name || record.source_id : "Choose a source";
  document.getElementById("editorTitle").textContent = title;

  const emptyState = document.getElementById("emptyState");
  const formFields = document.getElementById("formFields");
  document.getElementById("duplicateButton").disabled = !record;
  document.getElementById("deleteButton").disabled = !record;
  document.getElementById("seedButton").disabled = !record || !findRecordBySourceId("merged_records", record.source_id);
  document.getElementById("addDocumentButton").disabled = !record;

  if (!record) {
    emptyState.classList.remove("hidden");
    formFields.classList.add("hidden");
    document.getElementById("documentList").innerHTML = "";
    return;
  }

  emptyState.classList.add("hidden");
  formFields.classList.remove("hidden");

  document.querySelectorAll("[data-field]").forEach((input) => {
    const fieldName = input.dataset.field;
    if (input.tagName === "SELECT") {
      input.value = record[fieldName] || "draft";
      return;
    }
    input.value = record[fieldName] || "";
  });

  document.querySelectorAll("[data-list-field]").forEach((input) => {
    const fieldName = input.dataset.listField;
    const listMode = input.dataset.listMode;
    input.value = listMode === "years" ? formatYears(record[fieldName]) : formatLineList(record[fieldName]);
  });

  bindFormInputs();
  renderDocuments(record);
}

function renderDocuments(record) {
  const root = document.getElementById("documentList");
  const documents = Array.isArray(record.source_documents) ? record.source_documents : [];

  if (!documents.length) {
    root.innerHTML = `<div class="empty-panel">No source documents are attached to this record.</div>`;
    return;
  }

  root.innerHTML = documents
    .map((document, index) => {
      const documentId = `${record.source_id}-${index}`;
      return `
        <div class="document-card">
          <div class="field-grid two-column">
            <label class="field">
              <span>Name</span>
              <input type="text" data-document-field="name" data-document-index="${index}" value="${escapeAttribute(
                document.name || "",
              )}">
            </label>
            <label class="field">
              <span>Type</span>
              <input type="text" data-document-field="type" data-document-index="${index}" value="${escapeAttribute(
                document.type || "",
              )}">
            </label>
            <label class="field">
              <span>URL</span>
              <input type="text" data-document-field="url" data-document-index="${index}" value="${escapeAttribute(
                document.url || "",
              )}">
            </label>
            <label class="field">
              <span>Worksheet</span>
              <input type="text" data-document-field="worksheet" data-document-index="${index}" value="${escapeAttribute(
                document.worksheet || "",
              )}">
            </label>
            <label class="field checkbox-field">
              <input type="checkbox" data-document-field="stale" data-document-index="${index}" ${
                document.stale ? "checked" : ""
              }>
              <span>Stale reference</span>
            </label>
          </div>
          <label class="field">
            <span>Extra fields (JSON object)</span>
            <textarea rows="3" data-document-extra="${index}" id="extra-${documentId}">${escapeHtml(
              formatDocumentExtras(document),
            )}</textarea>
            <small>Optional. Use this if a document needs fields beyond name, type, url, worksheet, and stale.</small>
          </label>
          <div class="document-actions">
            <button type="button" class="danger-button" data-remove-document="${index}">Remove document</button>
          </div>
        </div>
      `;
    })
    .join("");

  bindDocumentInputs();
}

function renderContext() {
  const record = getSelectedRecord();
  const root = document.getElementById("contextPanel");
  if (!record) {
    root.innerHTML = `<div class="empty-panel">Context appears here after you select a source.</div>`;
    return;
  }

  const sourceId = record.source_id;
  const spreadsheet = findRecordBySourceId("imported_records", sourceId);
  const database = findRecordBySourceId("observed_records", sourceId);
  const merged = findRecordBySourceId("merged_records", sourceId);
  const warnings = (state.context.warnings || []).filter((warning) => warning.source_id === sourceId);

  root.innerHTML = [
    renderContextCard("Merged view", merged, "accent"),
    renderContextCard("Spreadsheet reference", spreadsheet, "default"),
    renderContextCard("Database observation", database, "default"),
    renderWarningsCard(warnings),
  ].join("");
}

function renderContextCard(label, record, tone) {
  if (!record) {
    return `
      <div class="context-card">
        <h3>${escapeHtml(label)}</h3>
        <p class="context-copy">No record loaded for this source.</p>
      </div>
    `;
  }

  return `
    <div class="context-card">
      <div class="section-header">
        <h3>${escapeHtml(label)}</h3>
        <span class="status-chip${tone === "accent" ? " status-chip--accent" : ""}">${escapeHtml(
          record.display_name || record.source_id,
        )}</span>
      </div>
      <div class="context-meta">
        ${renderInlineChip("Domains", record.domains)}
        ${renderInlineChip("Geography", record.geographic_levels)}
        ${renderInlineChip("Years", formatYears(record.available_years))}
      </div>
      ${record.short_description ? `<p class="context-copy">${escapeHtml(record.short_description)}</p>` : ""}
      <pre>${escapeHtml(formatContextRecord(record))}</pre>
    </div>
  `;
}

function renderWarningsCard(warnings) {
  if (!warnings.length) {
    return `
      <div class="context-card">
        <h3>Warnings</h3>
        <p class="context-copy">No validation warnings for this source in the current merged view.</p>
      </div>
    `;
  }

  return `
    <div class="context-card">
      <h3>Warnings</h3>
      ${warnings
        .map(
          (warning) => `
            <div>
              <div class="chip-row">
                <span class="status-chip status-chip--warning">${escapeHtml(warning.severity)}</span>
                <span class="status-chip">${escapeHtml(warning.code)}</span>
              </div>
              <p class="context-copy">${escapeHtml(warning.message)}</p>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function bindFormInputs() {
  document.querySelectorAll("[data-field]").forEach((input) => {
    const eventName = input.tagName === "SELECT" ? "change" : "input";
    input.addEventListener(eventName, () => {
      const record = getSelectedRecord();
      if (!record) {
        return;
      }

      const fieldName = input.dataset.field;
      const previousSourceId = record.source_id;
      record[fieldName] = input.value;

      if (fieldName === "source_id") {
        const nextSourceId = input.value.trim();
        moveDocumentDraft(previousSourceId, nextSourceId);
        state.selectedSourceId = nextSourceId;
      }

      if (fieldName === "source_id" || fieldName === "display_name") {
        document.getElementById("editorTitle").textContent = record.display_name || record.source_id || "Selected Record";
      }

      markDirty();
      renderLists();
      renderContext();
    });
  });

  document.querySelectorAll("[data-list-field]").forEach((input) => {
    const fieldName = input.dataset.listField;
    const mode = input.dataset.listMode;
    input.addEventListener("input", () => {
      const record = getSelectedRecord();
      if (!record) {
        return;
      }
      record[fieldName] = mode === "years" ? parseYears(input.value) : parseLineList(input.value);
      markDirty();
      renderLists();
      renderContext();
    });
  });
}

function bindDocumentInputs() {
  document.querySelectorAll("[data-document-field]").forEach((input) => {
    const eventName = input.type === "checkbox" ? "change" : "input";
    input.addEventListener(eventName, () => {
      const record = getSelectedRecord();
      if (!record) {
        return;
      }
      const index = Number(input.dataset.documentIndex);
      const fieldName = input.dataset.documentField;
      const document = record.source_documents[index];
      if (!document) {
        return;
      }

      document[fieldName] = input.type === "checkbox" ? input.checked : input.value;
      markDirty();
      renderContext();
    });
  });

  document.querySelectorAll("[data-document-extra]").forEach((input) => {
    input.addEventListener("input", () => {
      const record = getSelectedRecord();
      if (!record) {
        return;
      }
      state.sourceDocumentDrafts[documentDraftKey(record.source_id, Number(input.dataset.documentExtra))] = input.value;
      markDirty();
    });
  });

  document.querySelectorAll("[data-remove-document]").forEach((button) => {
    button.addEventListener("click", () => {
      removeDocument(Number(button.dataset.removeDocument));
    });
  });
}

async function saveRegistry() {
  const validationError = applyPendingDocumentDrafts();
  if (validationError) {
    setSaveStatus(validationError, "error");
    return;
  }

  const response = await fetch("/api/reviewed-registry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(getReviewedRecords()),
  });
  const payload = await response.json();
  if (!response.ok) {
    setSaveStatus(payload.error || "Unable to save reviewed registry.", "error");
    return;
  }

  state.context = payload;
  state.dirty = false;
  state.sourceDocumentDrafts = {};
  const savedRecord = getReviewedRecords().find((record) => record.source_id === state.selectedSourceId);
  state.selectedSourceId = savedRecord?.source_id || getReviewedRecords()[0]?.source_id || "";
  renderAll();
  setSaveStatus("Saved reviewed registry to data/reviewed_registry.json.", "success");
}

function createBlankRecord() {
  const sourceId = nextAvailableSourceId("new-source");
  state.context.reviewed_records.unshift({
    ...structuredClone(EMPTY_RECORD),
    source_id: sourceId,
    last_reviewed_at: todayIsoDate(),
  });
  state.selectedSourceId = sourceId;
  markDirty();
  renderAll();
}

function addSuggestionRecord(sourceId) {
  const suggestion = findRecordBySourceId("merged_records", sourceId);
  if (!suggestion) {
    return;
  }
  if (getReviewedRecords().some((record) => record.source_id === sourceId)) {
    state.selectedSourceId = sourceId;
    renderAll();
    return;
  }

  state.context.reviewed_records.unshift(cleanEditableRecord(suggestion));
  state.selectedSourceId = sourceId;
  markDirty();
  renderAll();
}

function duplicateSelectedRecord() {
  const record = getSelectedRecord();
  if (!record) {
    return;
  }

  const duplicate = cleanEditableRecord(record);
  duplicate.source_id = nextAvailableSourceId(`${record.source_id || "source"}-copy`);
  duplicate.display_name = `${duplicate.display_name || record.source_id} Copy`;
  state.context.reviewed_records.unshift(duplicate);
  state.selectedSourceId = duplicate.source_id;
  markDirty();
  renderAll();
}

function deleteSelectedRecord() {
  const record = getSelectedRecord();
  if (!record) {
    return;
  }

  state.context.reviewed_records = getReviewedRecords().filter((candidate) => candidate !== record);
  deleteDocumentDraftsForSource(record.source_id);
  state.selectedSourceId = getReviewedRecords()[0]?.source_id || "";
  markDirty();
  renderAll();
}

function replaceSelectedWithMergedContext() {
  const record = getSelectedRecord();
  if (!record) {
    return;
  }

  const merged = findRecordBySourceId("merged_records", record.source_id);
  if (!merged) {
    return;
  }

  const replacement = cleanEditableRecord(merged);
  replacement.last_reviewed_at = record.last_reviewed_at || todayIsoDate();
  replacement.review_status = record.review_status || replacement.review_status;

  const records = getReviewedRecords();
  const index = records.findIndex((candidate) => candidate.source_id === record.source_id);
  records[index] = replacement;
  state.selectedSourceId = replacement.source_id;
  markDirty();
  renderAll();
}

function addDocument() {
  const record = getSelectedRecord();
  if (!record) {
    return;
  }

  record.source_documents.push({ name: "", type: "", url: "", worksheet: "", stale: false });
  markDirty();
  renderDocuments(record);
  renderContext();
}

function removeDocument(index) {
  const record = getSelectedRecord();
  if (!record) {
    return;
  }

  record.source_documents.splice(index, 1);
  delete state.sourceDocumentDrafts[documentDraftKey(record.source_id, index)];
  markDirty();
  renderDocuments(record);
  renderContext();
}

function applyPendingDocumentDrafts() {
  for (const record of getReviewedRecords()) {
    const documents = Array.isArray(record.source_documents) ? record.source_documents : [];
    for (let index = 0; index < documents.length; index += 1) {
      const key = documentDraftKey(record.source_id, index);
      const raw = state.sourceDocumentDrafts[key];
      if (!raw || !raw.trim()) {
        stripExtraDocumentFields(documents[index]);
        continue;
      }

      try {
        const parsed = JSON.parse(raw);
        if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
          return `Document extras for ${record.source_id} must be a JSON object.`;
        }
        stripExtraDocumentFields(documents[index]);
        Object.assign(documents[index], parsed);
      } catch (error) {
        return `Document extras for ${record.source_id} are not valid JSON.`;
      }
    }
  }
  return "";
}

function stripExtraDocumentFields(document) {
  for (const key of Object.keys(document)) {
    if (!["name", "type", "url", "worksheet", "stale"].includes(key)) {
      delete document[key];
    }
  }
}

function filterRecords(records) {
  return [...records]
    .sort(compareRecords)
    .filter((record) => {
      if (!state.search) {
        return true;
      }
      const haystack = [
        record.source_id,
        record.display_name,
        record.short_description,
        ...(record.domains || []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(state.search);
    });
}

function compareRecords(left, right) {
  const leftLabel = (left.display_name || left.source_id || "").toLowerCase();
  const rightLabel = (right.display_name || right.source_id || "").toLowerCase();
  return leftLabel.localeCompare(rightLabel);
}

function buildStatusChips(sourceId, isSuggestion) {
  const chips = [];
  if (findRecordBySourceId("imported_records", sourceId)) {
    chips.push(`<span class="status-chip status-chip--accent">spreadsheet</span>`);
  }
  if (findRecordBySourceId("observed_records", sourceId)) {
    chips.push(`<span class="status-chip">database</span>`);
  }
  if (isSuggestion) {
    chips.push(`<span class="status-chip status-chip--warning">missing manual</span>`);
  }
  const manual = findRecordBySourceId("reviewed_records", sourceId);
  if (manual?.review_status) {
    chips.push(
      `<span class="status-chip${
        manual.review_status.toLowerCase() === "reviewed" ? " status-chip--accent" : " status-chip--danger"
      }">${escapeHtml(manual.review_status)}</span>`,
    );
  }
  return chips.join("");
}

function renderInlineChip(label, value) {
  if (!value || (Array.isArray(value) && !value.length)) {
    return "";
  }
  const text = Array.isArray(value) ? value.join(", ") : value;
  return `<span class="status-chip"><strong>${escapeHtml(label)}:</strong>&nbsp;${escapeHtml(text)}</span>`;
}

function cleanEditableRecord(record) {
  return {
    ...structuredClone(EMPTY_RECORD),
    source_id: record.source_id || "",
    display_name: record.display_name || "",
    short_description: record.short_description || "",
    source_type: record.source_type || "",
    update_frequency: record.update_frequency || "",
    domains: uniqueStrings(record.domains || []),
    geographic_levels: uniqueStrings(record.geographic_levels || []),
    available_years: uniqueNumbers(record.available_years || []),
    year_notes: record.year_notes || "",
    source_systems: uniqueStrings(record.source_systems || []),
    confidence: record.confidence || "",
    review_status: record.review_status || "draft",
    last_reviewed_at: record.last_reviewed_at || "",
    notes: uniqueStrings(record.notes || []),
    caveats: uniqueStrings(record.caveats || []),
    source_documents: Array.isArray(record.source_documents)
      ? record.source_documents.map((document) => ({ ...document }))
      : [],
  };
}

function getReviewedRecords() {
  return state.context?.reviewed_records || [];
}

function getSuggestionRecords() {
  const manualIds = new Set(getReviewedRecords().map((record) => record.source_id));
  return (state.context?.merged_records || []).filter((record) => !manualIds.has(record.source_id));
}

function getSelectedRecord() {
  return getReviewedRecords().find((record) => record.source_id === state.selectedSourceId) || null;
}

function findRecordBySourceId(bucket, sourceId) {
  return (state.context?.[bucket] || []).find((record) => record.source_id === sourceId) || null;
}

function nextAvailableSourceId(baseSourceId) {
  const normalized = normalizeSourceId(baseSourceId);
  const usedIds = new Set(getReviewedRecords().map((record) => record.source_id));
  if (!usedIds.has(normalized)) {
    return normalized;
  }

  let counter = 2;
  while (usedIds.has(`${normalized}-${counter}`)) {
    counter += 1;
  }
  return `${normalized}-${counter}`;
}

function normalizeSourceId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "new-source";
}

function moveDocumentDraft(previousSourceId, nextSourceId) {
  if (!previousSourceId || previousSourceId === nextSourceId) {
    return;
  }
  const nextDrafts = {};
  for (const [key, value] of Object.entries(state.sourceDocumentDrafts)) {
    if (!key.startsWith(`${previousSourceId}::`)) {
      nextDrafts[key] = value;
      continue;
    }
    nextDrafts[key.replace(`${previousSourceId}::`, `${nextSourceId}::`)] = value;
  }
  state.sourceDocumentDrafts = nextDrafts;
}

function deleteDocumentDraftsForSource(sourceId) {
  for (const key of Object.keys(state.sourceDocumentDrafts)) {
    if (key.startsWith(`${sourceId}::`)) {
      delete state.sourceDocumentDrafts[key];
    }
  }
}

function documentDraftKey(sourceId, index) {
  return `${sourceId}::${index}`;
}

function parseLineList(value) {
  return uniqueStrings(
    value
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function parseYears(value) {
  return uniqueNumbers(
    value
      .split(/[^0-9]+/)
      .map((item) => Number(item))
      .filter((item) => Number.isInteger(item) && item > 1900 && item < 2200),
  );
}

function formatLineList(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function formatYears(value) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function uniqueStrings(values) {
  return [...new Set(values.map((value) => String(value).trim()).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" }),
  );
}

function uniqueNumbers(values) {
  return [...new Set(values.map((value) => Number(value)).filter(Number.isInteger))].sort((a, b) => a - b);
}

function formatContextRecord(record) {
  return JSON.stringify(
    {
      source_id: record.source_id,
      display_name: record.display_name,
      source_type: record.source_type,
      update_frequency: record.update_frequency,
      available_years: record.available_years,
      geographic_levels: record.geographic_levels,
      source_systems: record.source_systems,
      last_observed_at: record.last_observed_at,
      last_reviewed_at: record.last_reviewed_at,
      review_status: record.review_status,
    },
    null,
    2,
  );
}

function formatDocumentExtras(document) {
  const extras = {};
  Object.entries(document).forEach(([key, value]) => {
    if (!["name", "type", "url", "worksheet", "stale"].includes(key)) {
      extras[key] = value;
    }
  });
  return Object.keys(extras).length ? JSON.stringify(extras, null, 2) : "";
}

function markDirty() {
  state.dirty = true;
  setSaveStatus("Unsaved changes.", "");
}

function setSaveStatus(message, kind) {
  const node = document.getElementById("saveStatus");
  node.textContent = message;
  node.classList.toggle("is-success", kind === "success");
  node.classList.toggle("is-error", kind === "error");
}

function titleCase(value) {
  return String(value || "")
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("\n", "&#10;");
}

boot().catch((error) => {
  setSaveStatus(error.message || "Unable to load the manual editor.", "error");
});

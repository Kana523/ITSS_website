(() => {
  "use strict";
  const app = document.querySelector("[data-industry-app]");
  if (!app?.querySelector("[data-blueprint-library]")) return;
  const field = name => app.querySelector(`[data-blueprint-${name}]`);
  const data = globalThis.industryBlueprintData;
  const workspace = globalThis.industryWorkspace;
  const KEY = "itss_industry_blueprints_v1";
  let entries = [];
  let lastStored = null;
  let unreadable = false;
  let editing = null;
  let editingOriginal = null;
  let searchRevision = 0;
  let controller;
  const identifier = () => globalThis.crypto?.randomUUID?.() || `bp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const status = message => { field("status").textContent = message; };
  const capacity = entry => entry.kind === "bpo" ? "Unlimited" : `${(entry.quantity * entry.remaining_runs).toLocaleString("en-US")} (${entry.remaining_runs} per copy)`;
  const selected = () => workspace.capture().blueprint_selections;
  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(label, action) {
    const node = element("button", label); node.type = "button";
    node.className = "buy-button buy-button--secondary";
    node.addEventListener("click", () => attempt(action));
    return node;
  }
  function attempt(action) {
    try { action(); } catch (error) { status(error.message); }
  }
  function read(raw) {
    if (raw === null) return [];
    const parsed = JSON.parse(raw);
    if (parsed?.schema_version !== 1 || parsed.format !== "itss-blueprint-library") throw new Error("Unsupported blueprint library format or version.");
    return data.normalizeEntries(parsed.entries);
  }
  function commit(next) {
    if (unreadable) throw new Error("Library storage could not be read. Export a backup and reload before saving.");
    const normalized = data.normalizeEntries(next);
    if (localStorage.getItem(KEY) !== lastStored) throw new Error("The library changed in another tab. Reload before saving this edit.");
    const serialized = JSON.stringify({ format: "itss-blueprint-library", schema_version: 1, entries: normalized });
    localStorage.setItem(KEY, serialized);
    lastStored = serialized; entries = normalized;
    render();
  }
  function select(entry) {
    const scheduling = Boolean(workspace.capture().schedule);
    const next = selected().filter(row => scheduling
      ? row.id !== entry.id && (row.product_type_id !== entry.product_type_id || row.blueprint_type_id === entry.blueprint_type_id)
      : row.blueprint_type_id !== entry.blueprint_type_id && row.product_type_id !== entry.product_type_id);
    workspace.setBlueprintSelections([...next, entry]);
    status(`Selected ${entry.label} for this project. Calculate to check required runs.`);
  }
  function row(cells) {
    const tr = element("tr");
    cells.forEach(value => {
      const td = element("td");
      if (typeof value === "string") td.textContent = value;
      else td.append(value);
      tr.append(td);
    });
    return tr;
  }
  function renderSelections() {
    field("require").checked = workspace.capture().require_owned_blueprints;
    field("selections").replaceChildren();
    for (const entry of selected()) {
      const current = entries.find(item => item.id === entry.id);
      const matches = current && JSON.stringify(current) === JSON.stringify(entry);
      const actions = element("div"); actions.className = "blueprint-actions";
      if (current && !matches) actions.append(button("Refresh from library", () => select(current)));
      if (workspace.capture().schedule) actions.append(button("Use first", () => workspace.setBlueprintSelections([entry, ...selected().filter(item => item.id !== entry.id)])));
      actions.append(button("Remove selection", () => workspace.setBlueprintSelections(selected().filter(item => item.id !== entry.id))));
      field("selections").append(row([`${entry.blueprint_name} / ${entry.label} (${entry.kind.toUpperCase()})`,
        `${entry.material_efficiency}% / ${entry.time_efficiency}%`, capacity(entry),
        matches ? "Matches library" : current ? "Library changed; project uses saved snapshot" : "Project snapshot; lot absent from library", actions]));
    }
    if (!selected().length) {
      const tr = element("tr"); const td = element("td", "No blueprint lots selected. Choose a lot from your library."); td.colSpan = 5; tr.append(td); field("selections").append(tr);
    }
  }
  function render() {
    const query = field("filter").value.trim().toLowerCase();
    field("rows").replaceChildren();
    const visible = entries.filter(entry => `${entry.blueprint_name} ${entry.product_name} ${entry.label}`.toLowerCase().includes(query));
    field("count").textContent = `${entries.length} owned lots · ${visible.length} shown`;
    for (const entry of visible) {
      const actions = element("div"); actions.className = "blueprint-actions";
      actions.append(button("Use in project", () => select(entry)), button("Edit lot", () => edit(entry)),
        button("Duplicate lot", () => edit({ ...entry, id: identifier(), label: `${entry.label.slice(0, 53)} (copy)` })),
        button("Delete lot", () => {
          if (!confirm(`Delete “${entry.label}” from the shared library? Existing project snapshots will be retained.`)) return;
          commit(entries.filter(item => item.id !== entry.id));
          if (editing?.id === entry.id) cancelEdit();
          status("Blueprint lot deleted. Existing project snapshots are retained.");
        }));
      field("rows").append(row([`${entry.blueprint_name} / ${entry.label}`,
        `${entry.quantity} ${entry.kind === "bpo" ? (entry.quantity === 1 ? "original" : "originals") : (entry.quantity === 1 ? "copy" : "copies")}`,
        `${entry.material_efficiency}% / ${entry.time_efficiency}%`, capacity(entry), actions]));
    }
    renderSelections();
  }
  function syncKind() {
    const copy = field("kind").value === "bpc";
    field("runs-field").hidden = !copy;
    field("runs").disabled = !copy;
    field("runs").required = copy;
  }
  function edit(entry) {
    editing = { ...entry };
    editingOriginal = JSON.stringify(entries.find(item => item.id === entry.id) || null);
    field("editor").hidden = false;
    field("editor-title").textContent = entry.blueprint_name;
    field("label").value = entry.label;
    field("kind").value = entry.kind;
    field("quantity").value = entry.quantity;
    field("me").value = entry.material_efficiency;
    field("te").value = entry.time_efficiency;
    field("runs").value = entry.remaining_runs ?? 1;
    syncKind(); field("label").focus();
  }
  function cancelEdit() { editing = null; editingOriginal = null; field("editor").hidden = true; }
  field("kind").addEventListener("change", syncKind);
  field("cancel").addEventListener("click", cancelEdit);
  field("editor").addEventListener("submit", event => {
    event.preventDefault();
    attempt(() => {
      if (!editing || !field("editor").reportValidity()) return;
      if (JSON.stringify(entries.find(item => item.id === editing.id) || null) !== editingOriginal) {
        throw new Error("This lot changed while you were editing. Your fields are retained; cancel and reopen the lot to use the latest stock.");
      }
      const entry = data.normalizeEntry({ ...editing, label: field("label").value,
        kind: field("kind").value, quantity: Number(field("quantity").value),
        material_efficiency: Number(field("me").value), time_efficiency: Number(field("te").value),
        remaining_runs: field("kind").value === "bpc" ? Number(field("runs").value) : null });
      commit([...entries.filter(item => item.id !== entry.id), entry]);
      cancelEdit(); status(`Saved ${entry.label}. Existing project selections keep their previous snapshot until refreshed.`);
    });
  });
  field("filter").addEventListener("input", render);
  function invalidateSearch() {
    searchRevision += 1; controller?.abort(); field("search-results").replaceChildren();
    field("search-button").disabled = false; field("search-status").textContent = "";
  }
  field("search").addEventListener("input", invalidateSearch);
  field("search-form").addEventListener("submit", async event => {
    event.preventDefault(); invalidateSearch();
    const revision = searchRevision;
    const query = field("search").value.trim();
    if (!query) return;
    controller = new AbortController(); field("search-button").disabled = true;
    field("search-status").textContent = "Searching manufacturing blueprints…";
    try {
      const base = document.body.dataset.industryApiBase?.replace(/\/$/, "") || "";
      const response = await fetch(`${base}/api/industry/blueprints?${new URLSearchParams({ search: query, limit: 20 })}`, { signal: controller.signal, headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message || "Blueprint search failed.");
      if (revision !== searchRevision) return;
      for (const item of payload.items) {
        const li = element("li");
        li.append(button(`Add ${item.blueprint_name}`, () => {
          edit({ ...item, id: identifier(), label: item.blueprint_name.slice(0, 60),
            sde_build_number: payload.sde_build_number, kind: "bpo", quantity: 1,
            remaining_runs: null, material_efficiency: 0, time_efficiency: 0 });
        })); field("search-results").append(li);
      }
      field("search-status").textContent = payload.items.length ? `${payload.items.length} results. Choose a blueprint to record ownership.` : "No supported manufacturing blueprints found.";
    } catch (error) {
      if (revision === searchRevision && error.name !== "AbortError") field("search-status").textContent = error.message;
    } finally { if (revision === searchRevision) field("search-button").disabled = false; }
  });
  field("require").addEventListener("change", () => workspace.setBlueprintSelections(selected(), field("require").checked));
  function download(text) {
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const anchor = element("a"); anchor.href = url; anchor.download = "blueprint-library.json"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  field("export").addEventListener("click", () => {
    download(unreadable && lastStored ? lastStored : JSON.stringify({ format: "itss-blueprint-library", schema_version: 1, entries }, null, 2));
    status(unreadable ? "Exported the stored library for recovery." : "Exported blueprint library.");
  });
  field("import").addEventListener("click", () => field("file").click());
  field("file").addEventListener("change", async () => {
    const file = field("file").files[0]; field("file").value = "";
    if (!file) return;
    try {
      if (file.size > 5000000) throw new Error("Library files must be smaller than 5 MB.");
      const incoming = read(await file.text());
      const ids = new Map(entries.map(entry => [entry.id, entry]));
      for (const entry of incoming) {
        const existing = ids.get(entry.id);
        if (existing && JSON.stringify(existing) !== JSON.stringify(entry)) throw new Error("Import conflicts with an existing lot. Its stock was not overwritten.");
        ids.set(entry.id, entry);
      }
      const added = ids.size - entries.length;
      commit([...ids.values()]); status(`Imported ${added} new lots. Identical existing lots were kept once.`);
    } catch (error) { status(`Import failed: ${error.message}`); }
  });
  app.addEventListener("industry:blueprints-selected", renderSelections);
  app.addEventListener("industry:schedule-settings-changed", renderSelections);
  app.addEventListener("industry:project-loaded", () => { renderSelections(); invalidateSearch(); });
  app.addEventListener("industry:workspace-changed", () => { field("usage").textContent = "Inputs changed. Calculate to check required runs."; });
  app.addEventListener("industry:plan-calculated", event => {
    const steps = event.detail.build_steps.filter(step => step.recipe_key.activity_id === 1);
    const selections = selected();
    const untracked = steps.filter(step => !selections.some(entry => entry.blueprint_type_id === step.recipe_key.blueprint_type_id));
    const messages = selections.map(entry => {
      const step = steps.find(step => step.recipe_key.blueprint_type_id === entry.blueprint_type_id);
      const scheduledRuns = event.detail.schedule?.jobs.filter(job => job.lot_id === entry.id).reduce((sum, job) => sum + job.runs, 0);
      const runs = scheduledRuns ?? step?.runs;
      return `${entry.label}: ${runs ? `${runs} runs required` : "not used in this route"}`;
    });
    field("usage").textContent = `${messages.join(". ")}${messages.length ? ". " : ""}${untracked.length} manufacturing recipe(s) use untracked blueprints. Library quantities are unchanged.`;
    for (const controls of app.querySelectorAll("[data-blueprint-type-id]")) {
      if (!selections.some(entry => entry.blueprint_type_id === Number(controls.dataset.blueprintTypeId))) continue;
      controls.querySelectorAll("[data-efficiency-field], [data-efficiency-action]").forEach(input => {
        input.disabled = true; input.title = "ME/TE comes from the selected library lot. Edit or remove it on Blueprints.";
      });
      if (controls.querySelector("[data-efficiency-field]")) {
        const note = element("p", "ME/TE supplied by the selected blueprint lot. Edit its selection on Blueprints."); note.className = "field-status"; controls.append(note);
      }
    }
  });
  // Library changes can refresh the catalog in another tab, but never its project selections.
  window.addEventListener("storage", event => {
    if (event.key !== KEY && event.key !== null) return;
    try {
      const raw = localStorage.getItem(KEY); const next = read(raw);
      entries = next; lastStored = raw; unreadable = false; render();
      status("Library changed in another tab. Unsaved edit fields and project snapshots are retained; refresh selections when ready.");
    } catch (error) { unreadable = true; status(error.message); }
  });
  try { lastStored = localStorage.getItem(KEY); entries = read(lastStored); }
  catch (error) { unreadable = true; status(`Library recovery unavailable: ${error.message} Export a backup before changing stored data.`); }
  render();
})();

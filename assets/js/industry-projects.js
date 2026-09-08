(() => {
  "use strict";
  const app = document.querySelector("[data-industry-app]");
  if (!app?.querySelector("[data-project-panel]")) return;
  const field = name => app.querySelector(`[data-project-${name}]`);
  const workspace = globalThis.industryWorkspace;
  const config = globalThis.industryFacilityConfig;
  const data = globalThis.industryProjectData;
  const KEY = "itss_industry_projects_v1";
  const MAX_PROJECTS = 25;
  app.dataset.projectWorkspace = "active";
  let timer;
  let applying = false;
  let conflict = false;
  let lastStored = null;
  let store = { schema_version: 1, active_id: null, projects: [] };
  const status = message => { field("status").textContent = message; };
  const active = () => store.projects.find(entry => entry.id === store.active_id);
  const projectId = () => globalThis.crypto?.randomUUID?.()
    || `project-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  function normalizeSnapshot(raw) {
    if (!raw || typeof raw !== "object") throw new Error("Missing project snapshot.");
    const configuration = config.normalize(raw.configuration);
    if (!configuration) throw new Error("Production settings are invalid or incompatible. Check the Config tab.");
    return { workspace: data.normalizeWorkspace(raw.workspace), configuration };
  }
  function capture() {
    return normalizeSnapshot({ workspace: workspace.capture(), configuration: config.capture() });
  }
  function nameValue(raw) {
    if (typeof raw !== "string" || !raw.trim() || raw.trim().length > 60) throw new Error("Use a project name of 1–60 characters.");
    return raw.trim();
  }
  function persist() {
    if (conflict) throw new Error("Projects changed in another tab or could not be read. Export your current plan, then reload to continue saving.");
    const current = localStorage.getItem(KEY);
    if (current !== lastStored) {
      conflict = true;
      throw new Error("Projects changed in another tab. Export your current plan, then reload to continue saving.");
    }
    const serialized = JSON.stringify(store);
    localStorage.setItem(KEY, serialized);
    lastStored = serialized;
  }
  function render() {
    field("select").replaceChildren(...store.projects.map(entry => new Option(entry.name, entry.id)));
    field("select").value = store.active_id || "";
    field("name").value = active()?.name || "Working draft";
  }
  function save({ announce = true } = {}) {
    clearTimeout(timer);
    const snapshot = capture();
    const name = nameValue(field("name").value);
    const entry = active();
    if (!entry) throw new Error("No project is selected.");
    if (entry.name !== name || JSON.stringify(entry.snapshot) !== JSON.stringify(snapshot)) {
      entry.name = name;
      entry.snapshot = snapshot;
      entry.updated_at = new Date().toISOString();
    }
    persist();
    const option = [...field("select").options].find(option => option.value === entry.id);
    if (option) option.textContent = name;
    if (announce) status(`Saved ${name}.`);
  }
  function attempt(action) {
    try { action(); } catch (error) {
      status(`${error.message} Your current tab is still available; export a backup before closing.`);
    }
  }
  function queueSave() {
    if (applying) return;
    clearTimeout(timer);
    timer = setTimeout(() => attempt(() => save()), 350);
  }
  function apply(entry) {
    const snapshot = normalizeSnapshot(entry.snapshot);
    applying = true;
    try {
      config.applyProject(snapshot.configuration);
      workspace.apply(snapshot.workspace);
      store.active_id = entry.id;
      render();
      app.dispatchEvent(new CustomEvent("industry:project-loaded"));
    } finally { applying = false; }
  }
  function create(name, snapshot) {
    if (store.projects.length >= MAX_PROJECTS) throw new Error("You have 25 projects. Export and delete one before adding another.");
    const entry = { id: projectId(), name: nameValue(name), snapshot: normalizeSnapshot(snapshot), updated_at: new Date().toISOString() };
    store.projects.push(entry);
    apply(entry);
    persist();
    status(`Saved ${entry.name}. Calculate to refresh the route and prices.`);
  }
  field("save").addEventListener("click", () => attempt(() => save()));
  field("name").addEventListener("input", queueSave);
  field("select").addEventListener("change", () => attempt(() => {
    const id = field("select").value;
    try { save({ announce: false }); } catch (error) { field("select").value = store.active_id; throw error; }
    apply(store.projects.find(entry => entry.id === id));
    persist();
    status(`Loaded ${active().name}. Calculate to refresh the route and prices.`);
  }));
  field("new").addEventListener("click", () => attempt(() => {
    save({ announce: false });
    const snapshot = capture();
      snapshot.workspace = { ...snapshot.workspace, demands: [], owned_materials: [], choices: [], blueprint_efficiencies: [], blueprint_selections: [], require_owned_blueprints: false };
      if (snapshot.workspace.schedule) snapshot.workspace.schedule.assignments = [];
    create("Untitled project", snapshot);
  }));
  field("duplicate").addEventListener("click", () => attempt(() => {
    save({ announce: false });
    create(`${active().name.slice(0, 53)} (copy)`, capture());
  }));
  field("delete").addEventListener("click", () => attempt(() => {
    if (!confirm(`Delete project “${active().name}”? This removes its saved plan from this browser.`)) return;
    clearTimeout(timer);
      const fallback = { workspace: { ...workspace.capture(), demands: [], owned_materials: [], choices: [], blueprint_efficiencies: [], blueprint_selections: [], require_owned_blueprints: false }, configuration: active().snapshot.configuration };
      if (fallback.workspace.schedule) fallback.workspace.schedule.assignments = [];
    store.projects = store.projects.filter(entry => entry.id !== store.active_id);
    if (!store.projects.length) create("Working draft", fallback);
    else { apply(store.projects[0]); persist(); status("Project deleted."); }
  }));
  field("export").addEventListener("click", () => attempt(() => {
    const name = nameValue(field("name").value);
    const exported = { format: "itss-industry-project", schema_version: 1, name, snapshot: capture() };
    const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${name.replace(/[^a-z0-9_-]+/gi, "-") || "industry-project"}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status(`Exported ${name}.`);
  }));
  field("import").addEventListener("click", () => field("file").click());
  field("file").addEventListener("change", async () => {
    const file = field("file").files[0];
    field("file").value = "";
    if (!file) return;
    try {
      if (file.size > 5000000) throw new Error("Project files must be smaller than 5 MB.");
      const raw = JSON.parse(await file.text());
      if (raw?.format !== "itss-industry-project" || raw.schema_version !== 1) throw new Error("Unsupported project file format or version.");
      const name = nameValue(raw.name);
      const snapshot = normalizeSnapshot(raw.snapshot);
      if (store.projects.length >= MAX_PROJECTS) throw new Error("You have 25 projects. Export and delete one before importing.");
      save({ announce: false });
      create(name, snapshot);
    } catch (error) { status(`Import failed: ${error.message}`); }
  });
  app.addEventListener("industry:workspace-changed", queueSave);
  app.addEventListener("industry:configuration-applied", queueSave);
  app.addEventListener("industry:system-picker-resolved", queueSave);
  // Also captures implants, skill buttons, profile choices, and applied route decisions.
  app.addEventListener("input", event => {
    if (!event.target.closest("[data-project-panel], [data-bulk-panel], [data-blueprint-library], [data-search-input], [data-owned-search-input], [data-system-search]")) queueSave();
  });
  app.addEventListener("change", event => {
    if (!event.target.closest("[data-project-panel], [data-bulk-panel], [data-blueprint-library]")) queueSave();
  });
  window.addEventListener("pagehide", () => { if (!applying) attempt(() => save({ announce: false })); });
  window.addEventListener("storage", event => {
    if ((event.key === KEY || event.key === null) && event.newValue !== lastStored) {
      conflict = true;
      clearTimeout(timer);
      status("Projects changed in another tab. Export your current plan, then reload to continue saving.");
    }
  });
  try {
    lastStored = localStorage.getItem(KEY);
    if (lastStored) {
      const raw = JSON.parse(lastStored);
      if (raw?.schema_version !== 1 || !Array.isArray(raw.projects) || !raw.projects.length || raw.projects.length > MAX_PROJECTS) throw new Error("Invalid project store.");
      const ids = new Set();
      const projects = raw.projects.map(entry => {
        if (typeof entry.id !== "string" || !entry.id || entry.id.length > 100 || ids.has(entry.id)) throw new Error("Invalid project identifier.");
        ids.add(entry.id);
        return { id: entry.id, name: nameValue(entry.name), snapshot: normalizeSnapshot(entry.snapshot), updated_at: entry.updated_at };
      });
      if (!ids.has(raw.active_id)) throw new Error("Invalid active project.");
      store = { schema_version: 1, active_id: raw.active_id, projects };
      apply(active());
      status(`Restored ${active().name}. Calculate to refresh the route and prices.`);
    } else {
      // The first project adopts existing local profile settings without changing them.
      const entry = { id: projectId(), name: "Working draft", snapshot: capture(), updated_at: new Date().toISOString() };
      store.projects.push(entry); store.active_id = entry.id; render(); persist();
      status("Your working draft is saved automatically in this browser.");
    }
  } catch (error) {
    conflict = Boolean(lastStored);
    if (!active()) {
      const entry = { id: projectId(), name: "Working draft", snapshot: { workspace: workspace.capture(), configuration: config.capture() } };
      store = { schema_version: 1, active_id: entry.id, projects: [entry] }; render();
    }
    status(`Project recovery unavailable: ${error.message} Existing stored data has been retained. Export your current plan before closing.`);
  }
})();

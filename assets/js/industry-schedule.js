(() => {
  "use strict";
  const app = document.querySelector("[data-industry-app]");
  if (!app?.querySelector("[data-schedule-panel]")) return;
  const field = name => app.querySelector(`[data-schedule-${name}]`);
  const workspace = globalThis.industryWorkspace;
  let latest = null;
  let recipes = [];
  const status = value => { field("status").textContent = value; };
  const uid = () => globalThis.crypto?.randomUUID?.() || `schedule-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const localDate = value => {
    if (!value) return "";
    const date = new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 23);
  };
  const utcDate = value => value ? new Date(value).toISOString() : null;
  const node = (tag, text) => { const element = document.createElement(tag); if (text !== undefined) element.textContent = text; return element; };
  function input(name, value, type = "text", min = null, max = null) {
    const element = node("input"); element.type = type; element.value = value ?? "";
    element.dataset.field = name; element.setAttribute("aria-label", name.replaceAll("_", " "));
    if (min !== null) { element.min = min; element.step = 1; }
    if (max !== null) element.max = max;
    if (type === "text") element.maxLength = 60;
    if (type === "datetime-local") element.step = "0.001";
    element.required = name !== "available_from";
    return element;
  }
  function select(name, value, options) {
    const element = node("select"); element.dataset.field = name; element.setAttribute("aria-label", name.replaceAll("_", " "));
    options.forEach(([id, label]) => element.add(new Option(label, id))); element.value = value || "";
    return element;
  }
  function resourceRow(target, resource, cells) {
    const tr = node("tr"); tr.dataset.resourceId = resource.id;
    cells.forEach(cell => { const td = node("td"); td.append(cell); tr.append(td); });
    const td = node("td"); const remove = node("button", "Remove"); remove.type = "button"; remove.className = "buy-button buy-button--secondary";
    remove.addEventListener("click", () => { tr.remove(); status("Resource edits are pending. Apply settings to use them."); });
    td.append(remove); tr.append(td); field(target).append(tr);
  }
  function addWorker(worker = { id: uid(), name: "New character", manufacturing_slots: 1, reaction_slots: 0, available_from: null }) {
    resourceRow("workers", worker, [input("name", worker.name), input("manufacturing_slots", worker.manufacturing_slots, "number", 0, 11),
      input("reaction_slots", worker.reaction_slots, "number", 0, 11), input("available_from", localDate(worker.available_from), "datetime-local")]);
  }
  function addFacility(facility = { id: uid(), name: "New facility", activity: "manufacturing", solar_system_id: 30000142, slots: 1 }) {
    resourceRow("facilities", facility, [input("name", facility.name), select("activity", facility.activity, [["manufacturing", "Manufacturing"], ["reaction", "Reactions"]]),
      input("solar_system_id", facility.solar_system_id, "number", 1, 2147483647), input("slots", facility.slots, "number", 1, 100)]);
  }
  function defaults() {
    const readSystem = name => Number(app.querySelector(`[data-pricing-integer="${name}"]`)?.value || 0);
    const facilities = [{ id: "manufacturing", name: "Manufacturing facility", activity: "manufacturing", solar_system_id: readSystem("solar_system_id") || 30000142, slots: 1 }];
    const reaction = readSystem("reaction_solar_system_id");
    if (reaction) facilities.push({ id: "reaction", name: "Reaction facility", activity: "reaction", solar_system_id: reaction, slots: 1 });
    return { start_at: new Date().toISOString(), max_runs_per_job: 100,
      workers: [{ id: "pilot-1", name: "Pilot 1", manufacturing_slots: 1, reaction_slots: 1, available_from: null }], facilities, assignments: [] };
  }
  function renderAssignments(options) {
    field("assignments").replaceChildren();
    const all = new Map(recipes.map(recipe => [`${recipe.recipe_key.blueprint_type_id}:${recipe.recipe_key.activity_id}`, recipe]));
    for (const assignment of options.assignments) {
      const key = `${assignment.recipe_key.blueprint_type_id}:${assignment.recipe_key.activity_id}`;
      if (!all.has(key)) all.set(key, { recipe_key: assignment.recipe_key, name: `Blueprint ${assignment.recipe_key.blueprint_type_id}` });
    }
    for (const recipe of all.values()) {
      const tr = node("tr"); tr.dataset.blueprint = recipe.recipe_key.blueprint_type_id; tr.dataset.activity = recipe.recipe_key.activity_id;
      const assigned = options.assignments.find(row => row.recipe_key.blueprint_type_id === recipe.recipe_key.blueprint_type_id && row.recipe_key.activity_id === recipe.recipe_key.activity_id);
      tr.append(node("td", recipe.name));
      for (const control of [select("worker_id", assigned?.worker_id, [["", "Automatic"], ...options.workers.map(row => [row.id, row.name])]),
        select("facility_id", assigned?.facility_id, [["", "Automatic"], ...options.facilities.map(row => [row.id, row.name])])]) {
        const td = node("td"); td.append(control); tr.append(td);
      }
      field("assignments").append(tr);
    }
  }
  function renderSettings() {
    const options = workspace.capture().schedule;
    field("enabled").checked = Boolean(options); field("form").hidden = !options;
    if (!options) return;
    field("start").value = localDate(options.start_at); field("max-runs").value = options.max_runs_per_job;
    field("workers").replaceChildren(); options.workers.forEach(addWorker);
    field("facilities").replaceChildren(); options.facilities.forEach(addFacility);
    renderAssignments(options);
  }
  function readSettings() {
    const readRows = target => [...field(target).children].map(tr => {
      const row = { id: tr.dataset.resourceId };
      tr.querySelectorAll("[data-field]").forEach(control => {
        row[control.dataset.field] = control.type === "number" ? Number(control.value)
          : control.dataset.field === "available_from" ? utcDate(control.value) : control.value;
      }); return row;
    });
    const assignments = [...field("assignments").children].map(tr => ({ recipe_key: { blueprint_type_id: Number(tr.dataset.blueprint), activity_id: Number(tr.dataset.activity) },
      worker_id: tr.querySelector('[data-field="worker_id"]').value || null, facility_id: tr.querySelector('[data-field="facility_id"]').value || null }))
      .filter(row => row.worker_id || row.facility_id);
    return { start_at: utcDate(field("start").value), max_runs_per_job: Number(field("max-runs").value), workers: readRows("workers"), facilities: readRows("facilities"), assignments };
  }
  function apply() {
    if (!field("form").reportValidity()) return false;
    try { workspace.setSchedule(readSettings()); status("Scheduling settings applied. Recalculate to refresh quantities and dates."); return true; }
    catch (error) { status(error.message); return false; }
  }
  field("enabled").addEventListener("change", () => {
    try { workspace.setSchedule(field("enabled").checked ? defaults() : null); renderSettings(); }
    catch (error) { field("enabled").checked = Boolean(workspace.capture().schedule); status(error.message); }
  });
  field("add-worker").addEventListener("click", () => addWorker());
  field("add-facility").addEventListener("click", () => addFacility());
  field("apply").addEventListener("click", apply);
  field("form").addEventListener("submit", async event => {
    event.preventDefault();
    if (apply()) {
      status("Calculating jobs…");
      await workspace.calculate();
      if (!latest) status("No schedule was produced. Check Build for calculation details.");
    }
  });
  field("form").addEventListener("input", () => status("Edits are pending. Apply settings or calculate the schedule to use them."));
  app.addEventListener("industry:schedule-settings-changed", renderSettings);
  app.addEventListener("industry:project-loaded", () => { recipes = []; renderSettings(); });
  app.addEventListener("industry:workspace-changed", () => { latest = null; field("results").hidden = true; });
  app.addEventListener("industry:plan-calculated", event => {
    const plan = event.detail;
    recipes = plan.build_steps.map(step => ({ recipe_key: step.recipe_key, name: step.blueprint.name }));
    if (!plan.schedule) return;
    latest = plan; const options = workspace.capture().schedule;
    renderAssignments(options);
    const schedule = plan.schedule; const workers = new Map(options.workers.map(row => [row.id, row.name]));
    const facilities = new Map(options.facilities.map(row => [row.id, row.name]));
    const types = new Map(plan.build_steps.map(step => [step.product.type_id, step.product.name]));
    const lots = new Map(workspace.capture().blueprint_selections.map(row => [row.id, row.label]));
    const format = value => new Date(value).toLocaleString();
    field("summary").textContent = `${schedule.jobs.length} jobs · Start ${format(schedule.start_at)} · Finish ${format(schedule.end_at)} (local time)`;
    field("assumptions").replaceChildren(...schedule.assumptions.map(value => node("li", value)));
    field("jobs").replaceChildren(); field("timeline").replaceChildren();
    const start = Date.parse(schedule.start_at); const span = Math.max(1, Date.parse(schedule.end_at) - start);
    for (const job of schedule.jobs) {
      const tr = node("tr");
      const values = [`#${job.job_id} ${types.get(job.product_type_id) || job.product_type_id}`, `${job.runs} / ${job.material_efficiency}% / ${job.time_efficiency}%`,
        `${lots.get(job.lot_id) || "Untracked"} / ${job.blueprint_instance}`, `${workers.get(job.worker_id)} / ${job.worker_slot}`, `${facilities.get(job.facility_id)} / ${job.facility_slot}`,
        format(job.start_at), format(job.end_at), job.dependency_product_type_ids.map(id => types.get(id) || id).join(", ") || "None"];
      values.forEach(value => tr.append(node("td", String(value)))); field("jobs").append(tr);
      const li = node("li"); li.append(node("span", `#${job.job_id} ${types.get(job.product_type_id)} · ${workers.get(job.worker_id)}`));
      const track = node("div"); track.className = "schedule-track";
      const bar = node("span"); bar.className = "schedule-bar"; bar.dataset.activity = job.activity;
      bar.style.marginLeft = `${100 * (Date.parse(job.start_at) - start) / span}%`;
      bar.style.width = `${Math.max(0.2, 100 * (Date.parse(job.end_at) - Date.parse(job.start_at)) / span)}%`;
      bar.title = `${format(job.start_at)} → ${format(job.end_at)}`; track.append(bar); li.append(track); field("timeline").append(li);
    }
    field("results").hidden = false; status("Schedule calculated. Stock quantities have not been consumed.");
    window.industryTabs?.activate("schedule");
  });
  field("export").addEventListener("click", () => {
    if (!latest?.schedule) return;
    // Quote all values and neutralize spreadsheet formula prefixes in user-supplied labels.
    const quote = value => `"${String(value ?? "").replace(/^[=+@-]/, "'$&").replaceAll('"', '""')}"`;
    const headers = ["Job", "Product type ID", "Blueprint type ID", "Lot ID", "Instance", "Runs", "ME", "TE", "Worker ID", "Worker slot", "Facility ID", "Facility slot", "Start UTC", "Finish UTC", "Dependency product IDs"];
    const rows = latest.schedule.jobs.map(job => [job.job_id, job.product_type_id, job.recipe_key.blueprint_type_id, job.lot_id, job.blueprint_instance, job.runs, job.material_efficiency,
      job.time_efficiency, job.worker_id, job.worker_slot, job.facility_id, job.facility_slot, job.start_at, job.end_at, job.dependency_product_type_ids.join(";")]);
    const url = URL.createObjectURL(new Blob([[headers, ...rows].map(row => row.map(quote).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
    const anchor = node("a"); anchor.href = url; anchor.download = "industry-schedule.csv"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  renderSettings();
})();

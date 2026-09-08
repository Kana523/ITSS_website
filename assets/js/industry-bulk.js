(() => {
  "use strict";
  const app = document.querySelector("[data-industry-app]");
  if (!app?.querySelector("[data-bulk-panel]")) return;
  const field = name => app.querySelector(`[data-bulk-${name}]`);
  const data = globalThis.industryProjectData;
  const workspace = globalThis.industryWorkspace;
  let controller;
  let revision = 0;
  let preview = null;
  const status = message => { field("status").textContent = message; };
  function invalidate() {
    revision += 1;
    controller?.abort();
    preview = null;
    field("apply").disabled = true;
    field("preview").disabled = false;
    field("results").hidden = true;
    status("Preview the list before adding items.");
  }
  for (const name of ["text", "target", "mode"]) field(name).addEventListener("input", invalidate);
  app.addEventListener("industry:project-loaded", invalidate);
  field("preview").addEventListener("click", async () => {
    invalidate();
    const requestRevision = revision;
    controller = new AbortController();
    field("preview").disabled = true;
    status("Resolving exact item names and IDs…");
    try {
      const parsed = data.parsePaste(field("text").value);
      if (!parsed.length) throw new Error("Paste at least one item.");
      const queries = [...new Set(parsed.filter(row => !row.error && !row.ignored).map(row => row.query))];
      let payload = { items: [], producible_type_ids: [], sde_build_number: null };
      if (queries.length) {
        const base = document.body.dataset.industryApiBase?.replace(/\/$/, "") || "";
        const response = await fetch(`${base}/api/industry/types/resolve`, {
          method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ queries }), signal: controller.signal,
        });
        payload = await response.json();
        if (!response.ok) throw new Error(payload.error?.message || "Item lookup failed. Try again.");
      }
      if (requestRevision !== revision) return;
      const target = field("target").value;
      const producible = new Set(payload.producible_type_ids);
      const additions = [];
      let issues = 0;
      let ignored = 0;
      field("rows").replaceChildren();
      for (const row of parsed) {
        let message = row.error || row.ignored;
        let matched;
        if (row.ignored) ignored += 1;
        else if (!row.error) {
          const matches = payload.items.filter(item => item.name.toLowerCase() === row.query.toLowerCase()
            || (/^\d+$/.test(row.query) && item.type_id === Number(row.query)));
          if (!matches.length) message = "Unknown item";
          else if (matches.length > 1) message = "Ambiguous name; use a type ID";
          else if (target === "demands" && !producible.has(matches[0].type_id)) message = "No production recipe; use inventory if owned";
          else {
            matched = matches[0];
            additions.push({ item: matched, quantity: row.quantity });
            message = "Matched";
          }
        }
        if (!matched && !row.ignored) issues += 1;
        const tr = document.createElement("tr");
        for (const value of [row.line, matched?.name || row.query, row.quantity ?? "—", message]) {
          const td = document.createElement("td"); td.textContent = String(value); tr.append(td);
        }
        if (!matched && !row.ignored) tr.dataset.issue = "true";
        field("rows").append(tr);
      }
      field("results").hidden = false;
      if (additions.length) {
        // Preview checks totals too; apply rechecks against any subsequent edits to the live lists.
        data.mergeRows(workspace.capture()[target], additions, target === "demands" ? 50 : 500, field("mode").value);
        preview = { target, additions, mode: field("mode").value, buildNumber: payload.sde_build_number };
        field("apply").disabled = false;
      }
      field("apply").textContent = issues ? "Add matched items only" : "Add matched items";
      status(`${additions.length} matched entries, ${issues} unresolved, ${ignored} empty slots ignored. Repeated items are combined. Only matched entries will be added.`);
    } catch (error) {
      if (requestRevision === revision && error.name !== "AbortError") status(error.message);
    } finally {
      if (requestRevision === revision) field("preview").disabled = false;
    }
  });
  field("apply").addEventListener("click", () => {
    if (!preview) return;
    try {
      const { target, additions, mode, buildNumber } = preview;
      const previousBuild = workspace.capture().sde_build_number;
      workspace.merge(target, additions, mode, buildNumber);
      preview = null;
      field("apply").disabled = true;
      status(`Added matched items to ${target === "demands" ? "the build list" : "owned inventory"}. Calculate to refresh the plan.${previousBuild && previousBuild !== buildNumber ? " Industry data changed; recipe choices and ME/TE settings were reset." : ""}`);
    } catch (error) { status(error.message); }
  });
})();

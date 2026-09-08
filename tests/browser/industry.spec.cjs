const { test, expect } = require("@playwright/test");
const calculation = require("./fixtures/calculation.json");
const scheduledCalculation = require("./fixtures/scheduled-calculation.json");

async function mockApi(page) {
  const requests = [];
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    let json;
    if (url.pathname === "/api/ready") json = { status: "ready", sde_build_number: 9000001 };
    else if (url.pathname.endsWith("/systems")) json = {
      systems: [{ solar_system_id: 30000142, name: "Jita", security_status: 0.945913, security_space: "highsec" }],
    };
    else if (url.pathname.endsWith("/rig-scopes")) json = [{ category_id: 1, category_name: "Test Category", group_id: 10, group_name: "Test Group" }];
    else if (url.pathname.endsWith("/industry-index")) json = { status: "fresh", cost_index: 0.01 };
    else if (url.pathname.endsWith("/status")) json = { status: "fresh", age_minutes: 1 };
    else if (url.pathname.endsWith("/types")) json = {
      sde_build_number: 9000001, items: [{ type_id: 1001, name: "Test Product", published: true,
        group_id: 10, group_name: "Test Group", category_id: 1, category_name: "Test Category" }],
    };
    else if (url.pathname.endsWith("/types/resolve")) json = {
      sde_build_number: 9000001,
      items: [
        { type_id: 1001, name: "Test Product", published: true, group_id: 10, group_name: "Test Group", category_id: 1, category_name: "Test Category" },
        { type_id: 34, name: "Tritanium", published: true, group_id: 10, group_name: "Test Group", category_id: 1, category_name: "Test Category" },
      ], producible_type_ids: [1001],
    };
    else if (url.pathname.endsWith("/blueprints")) json = {
      sde_build_number: 9000001, items: [{ blueprint_type_id: 2001, blueprint_name: "Test Product Blueprint", product_type_id: 1001, product_name: "Test Product" }],
    };
    else if (url.pathname.endsWith("/calculate")) {
      const request = route.request().postDataJSON();
      requests.push(request);
      json = request.schedule ? structuredClone(scheduledCalculation) : calculation;
      if (request.schedule) {
        // The schedule fixture comes from the real API; adapt identifiers and the
        // chosen start time to this browser's project without simulating planning.
        const shift = Date.parse(request.schedule.start_at) - Date.parse(json.schedule.start_at);
        const at = value => new Date(Date.parse(value) + shift).toISOString();
        json.schedule.start_at = at(json.schedule.start_at); json.schedule.end_at = at(json.schedule.end_at);
        for (const job of json.schedule.jobs) {
          job.lot_id = request.blueprint_selections?.[0]?.lot_id || null;
          job.worker_id = request.schedule.assignments[0]?.worker_id || request.schedule.workers[0].id;
          job.facility_id = request.schedule.assignments[0]?.facility_id || request.schedule.facilities[0].id;
          job.start_at = at(job.start_at); job.end_at = at(job.end_at);
        }
      }
    } else return route.fulfill({ status: 404, json: { error: "Unexpected test request" } });
    await route.fulfill({ json });
  });
  await page.goto("/industry/");
  await expect(page.locator("[data-api-label]")).toHaveText("Calculator online");
  await expect(page.locator('[data-security-select][data-profile-activity="manufacturing"]')).toHaveValue("highsec");
  return requests;
}

async function addProduct(page) {
  await page.getByRole("tab", { name: "Build", exact: true }).click();
  await page.locator("[data-search-input]").fill("Test Product");
  await page.getByRole("button", { name: "Add Test Product to the build list" }).click();
}

async function addBlueprintLot(page, { kind = "bpc", runs = "3", quantity = "2", label = "Weekend copies" } = {}) {
  await page.getByRole("tab", { name: "Blueprints", exact: true }).click();
  await page.locator("[data-blueprint-search]").fill("Test Product");
  await page.locator("[data-blueprint-search-button]").click();
  await page.getByRole("button", { name: "Add Test Product Blueprint", exact: true }).click();
  await page.locator("[data-blueprint-label]").fill(label);
  await page.locator("[data-blueprint-kind]").selectOption(kind);
  await page.locator("[data-blueprint-quantity]").fill(quantity);
  await page.locator("[data-blueprint-me]").fill("10");
  await page.locator("[data-blueprint-te]").selectOption("20");
  if (kind === "bpc") await page.locator("[data-blueprint-runs]").fill(runs);
  await page.getByRole("button", { name: "Save blueprint lot", exact: true }).click();
  await expect(page.locator("[data-blueprint-status]")).toContainText(`Saved ${label}.`);
}

test("schedule slots, dates, assignments and exports persist with the project", async ({ page }, testInfo) => {
  const errors = []; page.on("pageerror", error => errors.push(error.message));
  const requests = await mockApi(page);
  await addProduct(page);
  await page.locator('[data-demand-quantity="1001"]').fill("3");
  await addBlueprintLot(page, { kind: "bpo", quantity: "2", label: "Originals" });
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Use in project" }).click();
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await page.locator("[data-schedule-enabled]").check();
  await page.locator("[data-schedule-start]").fill("2026-09-08T12:00");
  await page.locator("[data-schedule-max-runs]").fill("1");
  await page.locator('[data-schedule-workers] [data-field="manufacturing_slots"]').fill("2");
  await page.locator('[data-schedule-workers] [data-field="available_from"]').fill("2026-09-08T11:59:30.123");
  await page.locator('[data-schedule-facilities] [data-field="slots"]').fill("2");
  await page.getByRole("button", { name: "Calculate schedule", exact: true }).click();
  await expect(page.locator("[data-schedule-results]")).toBeVisible();
  await expect(page.locator("[data-schedule-jobs] tr")).toHaveCount(2);
  await expect(page.locator("[data-schedule-summary]")).toContainText("2 jobs");
  await expect(page.locator("[data-schedule-timeline] .schedule-bar")).toHaveCount(2);
  expect(requests.at(-1).schedule.max_runs_per_job).toBe(1);
  expect(requests.at(-1).schedule.workers[0].manufacturing_slots).toBe(2);
  expect(requests.at(-1).schedule.facilities[0].slots).toBe(2);
  await page.locator('[data-schedule-assignments] [data-field="worker_id"]').selectOption("pilot-1");
  await page.locator('[data-schedule-assignments] [data-field="facility_id"]').selectOption("manufacturing");
  await page.locator("[data-schedule-apply]").click();
  await expect(page.locator("[data-schedule-results]")).toBeHidden();
  await page.locator("[data-project-save]").click();
  await page.reload();
  await expect(page.locator("[data-schedule-enabled]")).toBeChecked();
  await expect(page.locator("[data-schedule-start]")).toHaveValue("2026-09-08T12:00");
  await expect(page.locator('[data-schedule-workers] [data-field="available_from"]')).toHaveValue("2026-09-08T11:59:30.123");
  await expect(page.locator('[data-schedule-assignments] [data-field="worker_id"]')).toHaveValue("pilot-1");
  await page.getByRole("button", { name: "Calculate schedule", exact: true }).click();
  await expect(page.locator("[data-schedule-results]")).toBeVisible();
  expect(requests.at(-1).schedule.assignments).toEqual([{ recipe_key: { blueprint_type_id: 2001, activity_id: 1 }, worker_id: "pilot-1", facility_id: "manufacturing" }]);
  const pending = page.waitForEvent("download");
  await page.locator("[data-schedule-export]").click();
  const download = await pending; const stream = await download.createReadStream(); const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const csv = Buffer.concat(chunks).toString();
  expect(csv).toContain('"Start UTC","Finish UTC"');
  expect(csv.split("\r\n")).toHaveLength(3);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("production-schedule.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("scheduling permits multiple lots, priority changes and portable project snapshots", async ({ page }) => {
  await mockApi(page); await addProduct(page);
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await page.locator("[data-schedule-enabled]").check();
  for (const label of ["First copies", "Second copies"]) {
    await addBlueprintLot(page, { label });
    await page.locator("[data-blueprint-rows] tr").filter({ hasText: label }).getByRole("button", { name: "Use in project" }).click();
  }
  await expect(page.locator("[data-blueprint-selections] tr")).toHaveCount(2);
  await page.locator("[data-blueprint-selections] tr").filter({ hasText: "Second copies" }).getByRole("button", { name: "Use first" }).click();
  await expect(page.locator("[data-blueprint-selections] tr").first()).toContainText("Second copies");
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await page.locator("[data-schedule-enabled]").click();
  await expect(page.locator("[data-schedule-enabled]")).toBeChecked();
  await expect(page.locator("[data-schedule-status]")).toContainText("Remove extra lots");
  const pending = page.waitForEvent("download"); await page.locator("[data-project-export]").click();
  const download = await pending; const stream = await download.createReadStream(); const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const buffer = Buffer.concat(chunks); const exported = JSON.parse(buffer.toString());
  expect(exported.snapshot.workspace.blueprint_selections.map(row => row.label)).toEqual(["Second copies", "First copies"]);
  expect(exported.snapshot.workspace.schedule.workers).toHaveLength(1);
  await page.locator("[data-project-new]").click();
  await page.locator("[data-project-file]").setInputFiles({ name: "schedule.json", mimeType: "application/json", buffer });
  await page.getByRole("tab", { name: "Blueprints", exact: true }).click();
  await expect(page.locator("[data-blueprint-selections] tr")).toHaveCount(2);
  await expect(page.locator("[data-blueprint-selections] tr").first()).toContainText("Second copies");
});

test("mobile schedule controls remain usable and invalid resource edits preserve saved settings", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.getByRole("tab", { name: "Schedule", exact: true }).click();
  await page.locator("[data-schedule-enabled]").check();
  await page.locator("[data-schedule-add-worker]").click();
  await expect(page.locator("[data-schedule-workers] tr")).toHaveCount(2);
  await page.locator('[data-schedule-workers] tr').last().getByRole("button", { name: "Remove" }).click();
  await page.locator("[data-schedule-add-facility]").click();
  await page.locator('[data-schedule-facilities] tr').last().getByRole("button", { name: "Remove" }).click();
  await page.locator('[data-schedule-workers] [data-field="manufacturing_slots"]').fill("12");
  await page.locator("[data-schedule-apply]").click();
  expect(await page.locator('[data-schedule-workers] [data-field="manufacturing_slots"]').evaluate(input => input.validity.valid)).toBe(false);
  await page.reload();
  await expect(page.locator('[data-schedule-workers] [data-field="manufacturing_slots"]')).toHaveValue("1");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("mobile-schedule.png"), fullPage: true });
});

test("library copy stock reaches calculation, persists and stays unchanged after planning", async ({ page }, testInfo) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const requests = await mockApi(page);
  await addProduct(page);
  await addBlueprintLot(page);
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Use in project" }).click();
  await page.locator("[data-blueprint-require]").check();
  await page.locator("[data-project-save]").click();
  await page.reload();
  await expect(page.locator("[data-blueprint-selections]")).toContainText("Weekend copies");
  await expect(page.locator("[data-blueprint-require]")).toBeChecked();
  await page.getByRole("tab", { name: "Build", exact: true }).click();
  await page.locator("[data-calculate-button]").click();
  await expect(page.locator("[data-plan-output]")).toBeVisible();
  expect(requests.at(-1).blueprint_selections).toEqual([{ recipe_key: { blueprint_type_id: 2001, activity_id: 1 }, kind: "bpc", quantity: 2, remaining_runs: 3, material_efficiency: 10, time_efficiency: 20 }]);
  expect(requests.at(-1).blueprint_efficiencies).toEqual([]);
  expect(requests.at(-1).require_owned_blueprints).toBe(true);
  await expect(page.locator("[data-plan-output] [data-efficiency-field]").first()).toBeDisabled();
  await page.getByRole("tab", { name: "Blueprints", exact: true }).click();
  await expect(page.locator("[data-blueprint-usage]")).toContainText("2 runs required");
  await expect(page.locator("[data-blueprint-rows]")).toContainText("6 (3 per copy)");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("blueprint-library.png"), fullPage: true });
  expect(errors).toEqual([]);
});

test("shared library edits preserve project snapshots until explicitly refreshed", async ({ page }) => {
  await mockApi(page);
  await addBlueprintLot(page);
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Use in project" }).click();
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Edit lot" }).click();
  await page.locator("[data-blueprint-runs]").fill("1");
  await page.getByRole("button", { name: "Save blueprint lot", exact: true }).click();
  await expect(page.locator("[data-blueprint-selections]")).toContainText("Library changed");
  await expect(page.locator("[data-blueprint-selections]")).toContainText("6 (3 per copy)");
  await page.locator("[data-blueprint-selections]").getByRole("button", { name: "Refresh from library" }).click();
  await expect(page.locator("[data-blueprint-selections]")).toContainText("2 (1 per copy)");
  await page.locator("[data-project-new]").click();
  await expect(page.locator("[data-blueprint-selections]")).toContainText("No blueprint lots selected");
  await expect(page.locator("[data-blueprint-rows]")).toContainText("Weekend copies");
  await page.locator("[data-project-select]").selectOption({ label: "Working draft" });
  await expect(page.locator("[data-blueprint-selections]")).toContainText("2 (1 per copy)");
});

test("library backups merge without duplicating stock and reject invalid entries", async ({ page }) => {
  await mockApi(page);
  await addBlueprintLot(page, { kind: "bpo", quantity: "1", label: "Original" });
  await expect(page.locator("[data-blueprint-rows]")).toContainText("Unlimited");
  const pending = page.waitForEvent("download");
  await page.locator("[data-blueprint-export]").click();
  const download = await pending;
  const stream = await download.createReadStream(); const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const buffer = Buffer.concat(chunks);
  await page.locator("[data-blueprint-file]").setInputFiles({ name: "library.json", mimeType: "application/json", buffer });
  await expect(page.locator("[data-blueprint-status]")).toContainText("Imported 0 new lots");
  const raw = JSON.parse(buffer.toString()); raw.entries[0].quantity = -1;
  await page.locator("[data-blueprint-file]").setInputFiles({ name: "bad.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(raw)) });
  await expect(page.locator("[data-blueprint-status]")).toContainText("Import failed");
  await expect(page.locator("[data-blueprint-count]")).toContainText("1 owned lots");
  page.once("dialog", dialog => dialog.accept());
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Delete lot" }).click();
  await expect(page.locator("[data-blueprint-count]")).toContainText("0 owned lots");
  await page.locator("[data-blueprint-file]").setInputFiles({ name: "library.json", mimeType: "application/json", buffer });
  await expect(page.locator("[data-blueprint-rows]")).toContainText("Unlimited");
});

test("conflicting library edits in two tabs preserve unsaved fields and the newer stock", async ({ page, context }) => {
  await mockApi(page);
  await addBlueprintLot(page);
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Edit lot" }).click();
  await page.locator("[data-blueprint-runs]").fill("2");
  const other = await context.newPage();
  await mockApi(other);
  await other.getByRole("tab", { name: "Blueprints", exact: true }).click();
  await other.locator("[data-blueprint-rows]").getByRole("button", { name: "Edit lot" }).click();
  await other.locator("[data-blueprint-runs]").fill("1");
  await other.getByRole("button", { name: "Save blueprint lot", exact: true }).click();
  await expect(page.locator("[data-blueprint-status]")).toContainText("Library changed in another tab");
  await expect(page.locator("[data-blueprint-runs]")).toHaveValue("2");
  await page.getByRole("button", { name: "Save blueprint lot", exact: true }).click();
  await expect(page.locator("[data-blueprint-status]")).toContainText("This lot changed while you were editing");
  await expect(page.locator("[data-blueprint-rows]")).toContainText("2 (1 per copy)");
  await other.close();
});

test("insufficient blueprint stock offers a direct path back to the library", async ({ page }) => {
  await mockApi(page);
  await addProduct(page);
  await addBlueprintLot(page, { runs: "0" });
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Use in project" }).click();
  await page.route("**/api/industry/calculate", route => route.fulfill({ status: 409, json: {
    sde_build_number: 9000001,
    error: { code: "insufficient_blueprint_stock", message: "Blueprint 2001 requires 2 runs; the selected library stock provides 0.", details: { recipe_key: { blueprint_type_id: 2001, activity_id: 1 }, required_runs: 2, available_runs: 0 } },
  } }));
  await page.getByRole("tab", { name: "Build", exact: true }).click();
  await page.locator("[data-calculate-button]").click();
  await expect(page.locator("[data-error-message]")).toContainText("stock provides 0");
  await page.getByRole("button", { name: "Review blueprint library", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Blueprints", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("blueprint library remains usable on mobile", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await addBlueprintLot(page);
  await page.locator("[data-blueprint-rows]").getByRole("button", { name: "Use in project" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  const clippedTabs = await page.locator("[data-industry-tab]").evaluateAll(tabs => tabs.filter(tab => {
    const label = tab.querySelector("span").getBoundingClientRect();
    const bounds = tab.getBoundingClientRect();
    return label.right > bounds.right || label.left < bounds.left;
  }).length);
  expect(clippedTabs).toBe(0);
  await page.evaluate(() => {
    document.querySelectorAll(".blueprint-table-scroll").forEach(node => { node.scrollLeft = 0; });
    window.scrollTo(0, 0);
  });
  await page.screenshot({ path: testInfo.outputPath("blueprint-library-mobile.png"), fullPage: true });
});

test("Accounting, implants and scoped rigs reach the request and results render", async ({ page }, testInfo) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const requests = await mockApi(page);
  await page.getByRole("tab", { name: "Config", exact: true }).click();
  await page.locator("[data-trade-skill-groups] summary").click();
  await page.getByRole("button", { name: "Accounting level 5", exact: true }).click();
  await expect(page.locator("[data-effective-sales-tax]")).toHaveText("3.375% sales tax · Accounting 5");
  await page.locator('[data-profile-implant="manufacturing_time_implant"]').selectOption("27170");
  await page.locator('[data-rig-tier-select][data-profile-activity="manufacturing"]').selectOption("t2");
  await page.locator('[data-rig-coverage][data-profile-activity="manufacturing"]').selectOption("group:10");
  await page.screenshot({ path: testInfo.outputPath("configuration.png"), fullPage: true });
  await addProduct(page);
  await page.locator("[data-calculate-button]").click();
  await expect(page.locator("[data-plan-output]")).toBeVisible();
  expect(requests).toHaveLength(1);
  expect(requests[0].pricing.accounting_level).toBe(5);
  expect(requests[0].production_profile.manufacturing_time_implant).toBe(27170);
  expect(requests[0].production_profile.rig_modifiers[0].group_ids).toEqual([10]);
  expect(requests[0].production_profile.rig_modifiers[0].material_reduction_basis_points).toBe(240);
  await expect(page.getByText("Production steps", { exact: true })).toBeVisible();
  await expect(page.locator("[data-market-detail]")).toContainText("3.375% sales tax");
  await page.getByRole("tab", { name: "Shopping", exact: true }).click();
  await expect(page.locator("[data-shopping-output]")).toBeVisible();
  expect(errors).toEqual([]);
});

test("whole projects recover inventory, route choices, efficiencies and settings", async ({ page }) => {
  const requests = await mockApi(page);
  await addProduct(page);
  await page.locator("[data-demand-quantity='1001']").fill("7");
  await page.locator("[data-project-name]").fill("Frigate batch");
  await page.locator("[data-bulk-panel] summary").click();
  await page.locator("[data-bulk-target]").selectOption("owned_materials");
  await page.locator("[data-bulk-text]").fill("Tritanium\t1,000\nTritanium x5\nUnknown Thing 4");
  await page.locator("[data-bulk-preview]").click();
  await expect(page.locator("[data-bulk-status]")).toContainText("2 matched entries, 1 unresolved");
  await expect(page.locator("[data-owned-quantity]")).toHaveCount(0);
  await page.locator("[data-bulk-apply]").click();
  await expect(page.locator("[data-owned-quantity='34']")).toHaveValue("1005");
  await page.locator("[data-inventory-valuation]").selectOption("recorded_cost");
  await page.locator("[data-owned-unit-cost='34']").fill("1234567890123456.12345678");
  // Seed the same public bridge used by project import to cover dormant recipe choices.
  await page.evaluate(() => {
    const snapshot = industryWorkspace.capture();
    snapshot.choices = [{ type_id: 34, decision: "buy" }];
    snapshot.blueprint_efficiencies = [{ recipe_key: { blueprint_type_id: 2001, activity_id: 1 }, product_type_id: 1001, material_efficiency: 10, time_efficiency: 20 }];
    industryWorkspace.apply(snapshot);
  });
  await page.locator("[data-project-save]").click();
  await expect(page.locator("[data-project-status]")).toHaveText("Saved Frigate batch.");
  await page.reload();
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("7");
  const restored = await page.evaluate(() => industryWorkspace.capture());
  expect(restored.owned_materials[0].unitCost).toBe("1234567890123456.12345678");
  expect(restored.owned_materials[0].quantity).toBe(1005);
  expect(restored.choices).toEqual([{ type_id: 34, decision: "buy" }]);
  expect(restored.blueprint_efficiencies[0].material_efficiency).toBe(10);
  await expect(page.locator("[data-plan-output]")).toBeHidden();
  await page.locator("[data-project-duplicate]").click();
  await expect(page.locator("[data-project-name]")).toHaveValue("Frigate batch (copy)");
  await page.locator("[data-demand-quantity='1001']").fill("9");
  await page.locator("[data-project-save]").click();
  await page.locator("[data-project-select]").selectOption({ label: "Frigate batch" });
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("7");
  expect(requests).toHaveLength(0);
});

test("JSON import validates atomically and export can be restored", async ({ page }) => {
  await mockApi(page);
  await addProduct(page);
  await page.locator("[data-project-name]").fill("Export test");
  const downloadPromise = page.waitForEvent("download");
  await page.locator("[data-project-export]").click();
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const exported = Buffer.concat(chunks);
  const raw = JSON.parse(exported.toString());
  raw.snapshot.workspace.demands[0].quantity = -5;
  await page.locator("[data-project-file]").setInputFiles({ name: "bad.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(raw)) });
  await expect(page.locator("[data-project-status]")).toContainText("Import failed:");
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("1");
  await page.locator("[data-project-new]").click();
  await expect(page.locator("[data-demand-quantity]")).toHaveCount(0);
  await page.locator("[data-project-file]").setInputFiles({ name: "good.json", mimeType: "application/json", buffer: exported });
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("1");
  await expect(page.locator("[data-project-name]")).toHaveValue("Export test");
});

test("fitting preview excludes unavailable recipes and becomes stale on edits", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.locator("[data-bulk-panel] summary").click();
  await page.locator("[data-bulk-text]").fill("[Test Product, Weekend fit]\nTest Product\nTritanium x100\n[Empty Low slot]");
  await page.locator("[data-bulk-preview]").click();
  await expect(page.locator("[data-bulk-status]")).toContainText("2 matched entries, 1 unresolved, 1 empty slots");
  await page.locator("[data-bulk-text]").fill("Test Product 3");
  await expect(page.locator("[data-bulk-apply]")).toBeDisabled();
  await page.locator("[data-bulk-preview]").click();
  await expect(page.locator("[data-bulk-apply]")).toBeEnabled();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("projects-and-paste.png"), fullPage: true });
  await page.locator("[data-bulk-apply]").click();
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("3");
  await page.locator("[data-bulk-mode]").selectOption("replace");
  await page.locator("[data-bulk-text]").fill("Test Product 2");
  await page.locator("[data-bulk-preview]").click();
  await expect(page.locator("[data-bulk-apply]")).toBeEnabled();
  await page.locator("[data-bulk-apply]").click();
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("2");
});

test("edits in another tab cannot overwrite this tab's project or configuration", async ({ page, context }) => {
  await mockApi(page);
  await addProduct(page);
  await page.locator("[data-project-save]").click();
  const other = await context.newPage();
  await mockApi(other);
  await other.locator("[data-demand-quantity='1001']").fill("8");
  await other.locator("[data-project-save]").click();
  await expect(page.locator("[data-project-status]")).toContainText("changed in another tab");
  await page.locator("[data-demand-quantity='1001']").fill("4");
  await page.locator("[data-project-save]").click();
  await expect(page.locator("[data-project-status]")).toContainText("changed in another tab");
  await page.reload();
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("8");
  await other.close();
});

test("storage failure is visible and leaves export available", async ({ page }) => {
  await mockApi(page);
  await addProduct(page);
  await page.evaluate(() => { Storage.prototype.setItem = () => { throw new DOMException("Storage quota exceeded", "QuotaExceededError"); }; });
  await page.locator("[data-project-save]").click();
  await expect(page.locator("[data-project-status]")).toContainText("Storage quota exceeded");
  const download = page.waitForEvent("download");
  await page.locator("[data-project-export]").click();
  expect((await download).suggestedFilename()).toBe("Working-draft.json");
  await expect(page.locator("[data-demand-quantity='1001']")).toHaveValue("1");
});

test("project and paste controls fit a narrow viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.locator("[data-bulk-panel] summary").click();
  await page.locator("[data-bulk-text]").fill("Test Product 3");
  await page.locator("[data-bulk-preview]").click();
  await expect(page.locator("[data-bulk-apply]")).toBeEnabled();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("projects-mobile.png"), fullPage: true });
});

test("named profiles restore manual fee assumptions after reload", async ({ page }) => {
  await mockApi(page);
  await page.getByRole("tab", { name: "Config", exact: true }).click();
  await page.locator("[data-config-new]").click();
  await page.locator("[data-config-name]").fill("Weekend build");
  await page.locator('[data-config-choice="sales_tax_mode"]').selectOption("manual");
  await page.locator('[data-pricing-percent="sales_tax_basis_points"]').fill("4.25");
  await expect(page.locator("[data-effective-sales-tax]")).toContainText("4.25%");
  await page.locator("[data-config-save]").click();
  await expect(page.locator("[data-config-status]")).toHaveText("Saved Weekend build.");
  await page.reload();
  await page.getByRole("tab", { name: "Config", exact: true }).click();
  await expect(page.locator('[data-config-choice="sales_tax_mode"]')).toHaveValue("manual");
  await expect(page.locator('[data-pricing-percent="sales_tax_basis_points"]')).toHaveValue("4.25");
  await expect(page.locator("[data-effective-sales-tax]")).toHaveText("4.25% sales tax · manual rate");
});

test("highsec reaction setup prevents a calculation request", async ({ page }) => {
  const requests = await mockApi(page);
  await addProduct(page);
  await page.getByRole("tab", { name: "Config", exact: true }).click();
  const picker = page.locator('[data-system-picker][data-system-activity="reaction"]');
  await picker.locator("[data-system-search]").fill("Jita");
  await picker.getByRole("button", { name: "Jita · highsec" }).click();
  await page.getByRole("tab", { name: "Build", exact: true }).click();
  await page.locator("[data-calculate-button]").click();
  await expect(page.getByRole("tab", { name: "Config", exact: true })).toHaveAttribute("aria-selected", "true");
  expect(await picker.locator("[data-system-search]").evaluate(input => input.validationMessage)).toContain("Reactions require");
  expect(requests).toHaveLength(0);
});

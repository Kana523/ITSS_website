(() => {
  "use strict";
  const fail = message => { throw new Error(message); };
  const integer = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;
  const label = (value, max = 60) => typeof value === "string" && value.trim() && value.length <= max;
  const date = value => {
    if (typeof value !== "string" || !/(Z|[+-]\d\d:\d\d)$/.test(value) || !Number.isFinite(Date.parse(value))) fail("Schedule dates need a valid time and timezone.");
    return new Date(value).toISOString();
  };
  function normalize(raw) {
    if (raw == null) return null;
    if (!integer(raw.max_runs_per_job, 1, Number.MAX_SAFE_INTEGER)) fail("Runs per job must be a positive whole number.");
    const normalizeRows = (rows, maximum, convert) => {
      if (!Array.isArray(rows) || !rows.length || rows.length > maximum) fail(`Use between 1 and ${maximum} scheduling resources.`);
      const seen = new Set();
      return rows.map(row => {
        if (!row || !label(row.id, 100) || !label(row.name) || seen.has(row.id)) fail("Resource names and unique IDs are required.");
        seen.add(row.id); return convert(row);
      });
    };
    const workers = normalizeRows(raw.workers, 20, row => {
      if (!integer(row.manufacturing_slots, 0, 11) || !integer(row.reaction_slots, 0, 11)) fail("Character slots must be whole numbers from 0 to 11.");
      return { id: row.id, name: row.name.trim(), manufacturing_slots: row.manufacturing_slots, reaction_slots: row.reaction_slots,
        available_from: row.available_from ? date(row.available_from) : null };
    });
    const facilities = normalizeRows(raw.facilities, 50, row => {
      if (!["manufacturing", "reaction"].includes(row.activity) || !integer(row.slots, 1, 100)
        || !integer(row.solar_system_id, 1, 2147483647)) fail("Facilities need an activity, system ID, and 1–100 concurrent jobs.");
      return { id: row.id, name: row.name.trim(), activity: row.activity, solar_system_id: row.solar_system_id, slots: row.slots };
    });
    if (!Array.isArray(raw.assignments) || raw.assignments.length > 500) fail("Invalid recipe assignments.");
    const keys = new Set();
    const assignments = raw.assignments.map(row => {
      const key = row?.recipe_key;
      if (!key || !integer(key.blueprint_type_id, 1, 2147483647) || !integer(key.activity_id, 1, 2147483647)) fail("Invalid assignment recipe.");
      const id = `${key.blueprint_type_id}:${key.activity_id}`;
      if (keys.has(id) || (row.worker_id && !workers.some(worker => worker.id === row.worker_id))
        || (row.facility_id && !facilities.some(facility => facility.id === row.facility_id))) fail("Duplicate assignment or missing resource.");
      keys.add(id);
      return { recipe_key: { ...key }, worker_id: row.worker_id || null, facility_id: row.facility_id || null };
    });
    return { start_at: date(raw.start_at), max_runs_per_job: raw.max_runs_per_job, workers, facilities, assignments };
  }
  globalThis.industryScheduleData = Object.freeze({ normalize });
  if (typeof module !== "undefined") module.exports = globalThis.industryScheduleData;
})();

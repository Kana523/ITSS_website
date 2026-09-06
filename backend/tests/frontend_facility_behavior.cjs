// Exercise the real configuration, override and system-picker scripts together.
// The small DOM implements only the browser operations used by these controls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const camel = value => value.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

class Element {
  constructor(tag = "div") {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {};
    this.handlers = new Map(); this._value = ""; this.textContent = "";
    this.className = ""; this.validationMessage = ""; this.disabled = false;
    this.defaultValue = ""; this.min = ""; this.max = "";
  }
  append(...children) {
    for (let child of children) {
      if (typeof child === "string") { const text = new Element("#text"); text.textContent = child; child = text; }
      if (child.tagName === "fragment") this.append(...child.children);
      else { child.parentNode = this; this.children.push(child); }
    }
  }
  add(option) { this.append(option); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  get options() { return this.querySelectorAll("option"); }
  get selectedOptions() {
    const selected = this.options.filter(option => option.selected);
    return selected.length || this.multiple ? selected : this.options.slice(0, 1);
  }
  get value() { return this.tagName === "select" ? this.selectedOptions[0]?.value || "" : this._value; }
  set value(value) {
    this._value = String(value);
    if (this.tagName === "select") this.options.forEach(option => { option.selected = option.value === this._value; });
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name.startsWith("data-")) this.dataset[camel(name.slice(5))] = String(value);
    else if (name === "class") this.className = String(value);
    else if (["disabled", "multiple", "hidden", "selected"].includes(name)) this[name] = true;
    else this[name] = String(value);
    if (name === "value") this.defaultValue = String(value);
  }
  getAttribute(name) { return this.attributes[name] ?? null; }
  hasAttribute(name) { return name in this.attributes; }
  removeAttribute(name) { delete this.attributes[name]; }
  matches(selector) {
    return selector.split(/,\s*/).some(part => {
      part = part.trim();
      const parts = part.split(/\s+(?![^\[]*\])/);
      if (parts.length > 1) {
        const last = parts.pop();
        return this.matches(last) && Boolean(this.parentNode?.closest(parts.join(" ")));
      }
      if (part === ":disabled") return this.disabled || Boolean(this.parentNode?.closest("fieldset:disabled"));
      if (part.includes(":not(")) {
        const match = part.match(/:not\(([^)]+)\)/);
        if (this.matches(match[1])) return false;
        part = part.replace(match[0], "");
      }
      if (part.endsWith(":disabled")) {
        if (!this.disabled) return false;
        part = part.replace(":disabled", "");
      }
      const tag = part.match(/^[\w-]+/);
      if (tag && this.tagName !== tag[0]) return false;
      for (const match of part.matchAll(/\.([\w-]+)/g)) if (!this.className.split(" ").includes(match[1])) return false;
      for (const match of part.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)) {
        const value = match[1].startsWith("data-") ? this.dataset[camel(match[1].slice(5))] : this[match[1]] ?? this.attributes[match[1]];
        if (value === undefined || (match[2] !== undefined && String(value) !== match[2])) return false;
      }
      return true;
    });
  }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
  contains(element) { return element === this || this.children.some(child => child.contains(element)); }
  addEventListener(name, fn) { this.handlers.set(name, [...(this.handlers.get(name) || []), fn]); }
  dispatchEvent(event) {
    event.target ||= this;
    for (const fn of this.handlers.get(event.type) || []) fn(event);
    if (event.bubbles) this.parentNode?.dispatchEvent(event);
    return true;
  }
  setCustomValidity(value) { this.validationMessage = value; }
  checkValidity() { return this.matches(":disabled") || !this.validationMessage; }
  reportValidity() { return this.checkValidity(); }
  focus() { this.focused = true; }
  scrollIntoView() {}
}

function parseHtml(html) {
  const document = new Element("document"); const stack = [document];
  const voids = new Set(["input", "meta", "link", "img", "br", "hr"]);
  for (const token of html.matchAll(/<!--[\s\S]*?-->|<![^>]*>|<\/?[a-zA-Z][^>]*>|[^<]+/g)) {
    const text = token[0];
    if (text.startsWith("<!")) continue;
    if (text.startsWith("</")) { stack.pop(); continue; }
    if (!text.startsWith("<")) { stack.at(-1).textContent += text.trim(); continue; }
    const tag = text.match(/^<([\w-]+)/)[1]; const element = new Element(tag);
    for (const attr of text.slice(tag.length + 1, -1).matchAll(/([\w-]+)(?:="([^"]*)")?/g)) element.setAttribute(attr[1], attr[2] ?? "");
    stack.at(-1).append(element);
    if (!voids.has(tag)) stack.push(element);
  }
  document.body = document.querySelector("body");
  document.createElement = tag => new Element(tag);
  document.createTextNode = text => { const node = new Element("#text"); node.textContent = text; return node; };
  document.createDocumentFragment = () => new Element("fragment");
  return document;
}

const document = parseHtml(fs.readFileSync(path.join(root, "industry/index.html"), "utf8"));
const app = document.querySelector("[data-industry-app]");
const groups = [
  { category_id: 6, category_name: "Ship", group_id: 25, group_name: "Frigate" },
  { category_id: 7, category_name: "Module", group_id: 53, group_name: "Energy Weapon" },
];
let holdLookups = false;
const pending = [];
const systems = {
  30000142: { solar_system_id: 30000142, name: "Jita", security_space: "highsec", security_status: 0.94 },
  30000001: { solar_system_id: 30000001, name: "Low", security_space: "lowsec", security_status: 0.1 },
  30000002: { solar_system_id: 30000002, name: "Null", security_space: "nullsec", security_status: -0.5 },
  31000005: { solar_system_id: 31000005, name: "J100001", security_space: "wormhole", security_status: -0.99 },
};
const response = value => ({ ok: true, json: async () => value });
const context = vm.createContext({
  document, console, URL, URLSearchParams, AbortController,
  Event: class { constructor(type, options = {}) { this.type = type; Object.assign(this, options); } },
  CustomEvent: class { constructor(type, options = {}) { this.type = type; Object.assign(this, options); } },
  Option: function(text, value) { const option = new Element("option"); option.textContent = text; option.value = value; return option; },
  location: { hostname: "localhost" }, setTimeout: () => 1, clearTimeout() {}, addEventListener() {},
  localStorage: { getItem: () => null, setItem() {} },
  fetch: async address => {
    const url = new URL(address);
    if (url.pathname.endsWith("rig-scopes")) return response(groups);
    if (url.pathname.endsWith("industry-index")) return response({ cost_index: 0.05, status: "fresh" });
    const system = systems[url.searchParams.get("search")];
    if (holdLookups) return new Promise(resolve => pending.push(() => resolve(response({ systems: system ? [system] : [] }))));
    return response({ systems: system ? [system] : [] });
  },
});
context.window = context;
function run(name, exports = "") {
  const source = fs.readFileSync(path.join(root, "assets/js", name), "utf8");
  vm.runInContext(exports ? source.replace(/\}\)\(\);\s*$/, `${exports}\n})();`) : source, context);
}
run("industry-overrides.js");
run("industry-configs.js", "globalThis.configHooks = { captureConfiguration, applyConfiguration, normalizeConfiguration, updateAllActivities };");
run("industry-systems.js", "globalThis.systemHooks = { selectSystem, resolveStoredSystem, queueSearch }; ");
const core = fs.readFileSync(path.join(root, "assets/js/industry-core.js"), "utf8");
vm.runInContext(`(() => {
  const app = document.querySelector("[data-industry-app]");
  function showConfigTab() {}
  ${core.slice(core.indexOf("  function percentToBasisPoints("), core.indexOf("  function readSpecialistSkills("))}
  globalThis.readProfile = readProductionProfile;
})();`, context);
const tick = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
const field = (activity, name) => app.querySelector(`[data-${name}][data-profile-activity="${activity}"]`);
const picker = activity => app.querySelector(`[data-pricing-details] [data-system-picker][data-system-activity="${activity}"]`);
const change = element => element.dispatchEvent(new context.Event("change", { bubbles: true }));
const choose = (activity, id) => context.systemHooks.selectSystem(picker(activity), systems[id]);
const rigValue = activity => app.querySelector(`[data-profile-modifier="rig"][data-profile-activity="${activity}"][data-profile-effect="material"]`).value;

(async () => {
  await tick();
  assert.equal(field("manufacturing", "security-select").value, "highsec");
  assert.equal(field("manufacturing", "security-select").disabled, true);
  field("manufacturing", "rig-tier-select").value = "t2";
  change(field("manufacturing", "rig-tier-select"));
  assert.equal(context.industryFacilityConfig.validate().ok, false, "a generic rig must have explicit coverage");
  assert.equal(context.readProfile().ok, false, "invalid coverage blocks actual request construction");
  const coverage = field("manufacturing", "rig-coverage");
  coverage.options.find(option => option.value === "group:25").selected = true;
  change(coverage);
  assert.equal(context.industryFacilityConfig.validate().ok, true);
  const profile = context.readProfile();
  assert.equal(profile.ok, true);
  assert.deepEqual(JSON.parse(JSON.stringify(profile.value.rig_modifiers)), [{
    activity: "manufacturing", material_reduction_basis_points: 240,
    time_reduction_basis_points: 2400, category_ids: [], group_ids: [25],
  }]);
  assert.equal(rigValue("manufacturing"), "2.4", "Jita must use highsec rig bonuses");
  assert.equal(app.querySelector('[data-rig-scope="group_ids"][data-profile-activity="manufacturing"]').value, "25");
  field("manufacturing", "security-select").value = "nullsec";
  change(field("manufacturing", "security-select"));
  assert.equal(rigValue("manufacturing"), "2.4", "editing the derived dropdown must not change security");
  choose("manufacturing", 30000001);
  assert.equal(rigValue("manufacturing"), "4.56");
  choose("manufacturing", 30000002);
  assert.equal(rigValue("manufacturing"), "5.04");
  choose("manufacturing", 31000005);
  assert.equal(field("manufacturing", "security-select").value, "wormhole");
  assert.equal(rigValue("manufacturing"), "5.04");

  const saved = context.configHooks.captureConfiguration();
  saved.pricing.integers.solar_system_id = "30000142";
  saved.activities.manufacturing.security = "nullsec"; // Legacy contradictory profile.
  holdLookups = true;
  assert.equal(context.configHooks.applyConfiguration(saved), true);
  assert.equal(context.industryFacilityConfig.validate().ok, false, "saved security must be re-resolved");
  assert.equal(rigValue("manufacturing"), "0", "pending lookups cannot retain previous rig bonuses");
  pending.splice(0).forEach(resolve => resolve());
  await tick();
  assert.equal(rigValue("manufacturing"), "2.4");
  assert.equal(coverage.selectedOptions[0].value, "group:25", "saved coverage round trips");

  // A late lookup for the same ID must not overwrite a newer profile/selection.
  const old = context.systemHooks.resolveStoredSystem(picker("manufacturing"));
  const newer = context.systemHooks.resolveStoredSystem(picker("manufacturing"));
  const [finishOld, finishNew] = pending.splice(0);
  finishOld(); await tick();
  assert.equal(context.industryFacilityConfig.validate().ok, false);
  finishNew(); await Promise.all([old, newer]);
  assert.equal(context.industryFacilityConfig.validate().ok, true);
  const lookup = context.systemHooks.resolveStoredSystem(picker("manufacturing"));
  choose("manufacturing", 30000002);
  pending.splice(0).forEach(resolve => resolve()); await lookup;
  assert.equal(rigValue("manufacturing"), "5.04");
  holdLookups = false;

  context.systemHooks.queueSearch(picker("manufacturing"));
  assert.equal(context.industryFacilityConfig.validate().ok, false);
  assert.equal(rigValue("manufacturing"), "0");
  choose("manufacturing", 30000142);
  choose("reaction", 30000142);
  assert.equal(context.industryFacilityConfig.validate().ok, false, "highsec reactions are invalid even without rigs");
  choose("reaction", 30000001);
  assert.equal(context.industryFacilityConfig.validate().ok, true);

  const legacy = context.configHooks.captureConfiguration();
  delete legacy.activities.manufacturing.category_ids;
  delete legacy.activities.manufacturing.group_ids;
  assert.equal(context.configHooks.applyConfiguration(legacy), true);
  await tick();
  assert.equal(context.industryFacilityConfig.validate().ok, false, "legacy unscoped rigs must prompt for coverage");
  field("manufacturing", "rig-tier-select").value = "none";
  change(field("manufacturing", "rig-tier-select"));
  assert.equal(context.industryFacilityConfig.validate().ok, true);

  const row = app.querySelector('[data-setup-override="t1_small_ships"]');
  const enabled = row.querySelector("[data-setup-override-enabled]");
  enabled.checked = true; change(enabled); await tick();
  row.querySelector("[data-setup-override-rig]").value = "t2";
  change(row.querySelector("[data-setup-override-rig]"));
  let result = context.industrySetupOverrides.readRequest();
  assert.equal(result.ok, true);
  assert.equal(result.value[0].rig_material_reduction_basis_points, 240);
  context.systemHooks.selectSystem(row.querySelector("[data-system-picker]"), systems[30000002]);
  result = context.industrySetupOverrides.readRequest();
  assert.equal(result.value[0].rig_material_reduction_basis_points, 504);
  context.systemHooks.selectSystem(row.querySelector("[data-system-picker]"), { solar_system_id: 30000003, name: "Unknown" });
  assert.equal(context.industrySetupOverrides.readRequest().ok, false);
  enabled.checked = false; change(enabled);
  assert.equal(context.industryFacilityConfig.validate().ok, true, "disabled overrides do not block calculation");
  assert.equal(context.readProfile().value, null, "None removes rig bonuses and leaves no stale scopes in the request");
  console.log("Facility, coverage, saved-profile and async lookup behavior passed.");
})().catch(error => { console.error(error); process.exitCode = 1; });

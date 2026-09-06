// Focused DOM unit tests for the actual calculator script. No network/browser.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.handlers = new Map();
    this.value = "";
    this.hidden = false;
    this.textContent = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  append(...items) {
    for (const item of items) {
      if (item.tagName === "fragment") this.append(...item.children);
      else { this.children.push(item); item.parentNode = this; }
    }
  }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  hasAttribute(name) { return name in this.attributes; }
  addEventListener(name, handler) { this.handlers.set(name, handler); }
  setCustomValidity(message) { this.validationMessage = message; }
  reportValidity() { return !this.validationMessage; }
  focus() { this.focused = true; }
  matches(selector) {
    const match = selector.match(/^\[data-([\w-]+)(?:="([^"]+)")?\]$/);
    if (!match) return false;
    const key = match[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    return key in this.dataset && (match[2] === undefined || this.dataset[key] === match[2]);
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [
      ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) {
    if (this.matches(selector)) return this;
    return this.parentNode?.closest(selector) || this;
  }
}

const app = new Element();
const controls = new Map();
app.querySelector = selector => {
  if (!controls.has(selector)) controls.set(selector, new Element());
  return controls.get(selector);
};
const document = {
  body: new Element("body"),
  querySelector: selector => selector === "[data-industry-app]" ? app : app.querySelector(selector),
  createElement: tag => new Element(tag),
  createDocumentFragment: () => new Element("fragment"),
  addEventListener() {},
};
const context = vm.createContext({
  document, console, Intl, URLSearchParams, AbortController, setTimeout, clearTimeout,
  navigator: {}, location: { hostname: "localhost" },
  fetch: async () => ({ ok: true, json: async () => ({ api: "ok", database: "ok" }) }),
});
context.window = context;
const source = fs.readFileSync(path.resolve(__dirname, "../../assets/js/industry-core.js"), "utf8");
vm.runInContext(source.replace(/\}\)\(\);\s*$/, `
  globalThis.testHooks = { state, elements, readPricing, renderOwnedList, renderDemandList, renderValuation };
})();`), context);
const { state, elements, readPricing, renderOwnedList, renderDemandList, renderValuation } = context.testHooks;
const item = { type_id: 34, name: "Tritanium", group_name: "Mineral" };
state.ownedMaterials.set(34, { item, quantity: 6, unitCost: "9007199254740993.12345678" });
elements.inventoryValuation.value = "replacement_cost";
renderOwnedList();
let cost = elements.ownedList.querySelector("[data-owned-unit-cost]");
assert.equal(cost.parentNode.hidden, true);
assert.equal(readPricing().value.recorded_inventory_costs.length, 0);

elements.inventoryValuation.value = "recorded_cost";
elements.inventoryValuation.handlers.get("change")();
cost = elements.ownedList.querySelector("[data-owned-unit-cost]");
assert.equal(cost.parentNode.hidden, false);
assert.equal(readPricing().value.recorded_inventory_costs[0].unit_cost_isk, "9007199254740993.12345678");
cost.value = "-1";
elements.ownedList.handlers.get("input")({ target: cost });
assert.equal(readPricing().ok, false);
assert.ok(cost.validationMessage);
cost.value = "0";
elements.ownedList.handlers.get("input")({ target: cost });
assert.equal(readPricing().value.recorded_inventory_costs[0].unit_cost_isk, "0");
cost.value = "";
elements.ownedList.handlers.get("input")({ target: cost });
assert.equal(readPricing().value.recorded_inventory_costs.length, 0);

// Adding normal demands must still work with the new owned-inventory controls.
state.demands.set(34, { item, quantity: 1 });
renderDemandList();
assert.equal(elements.demandList.children.length, 1);

const economics = {
  cash_required_isk: "0", cash_surplus_isk: "100", consumed_inventory_value: { amount_isk: null },
  consumed_inventory: [{ item, quantity: 6, total_isk: null, has_sufficient_liquidity: null }],
  shopping_list_cost: { amount_isk: "0" }, installation_cost_total_isk: "0",
  total_cost_isk: null, net_output_value_isk: "100", profit_isk: null,
  profit_margin: null, surplus_inventory_value: { amount_isk: "0" },
  profit_including_surplus_isk: null, profit_margin_including_surplus: null, surplus_inventory: [],
  complete: false,
  missing_data: {
    shopping_sell_quote_type_ids: [], output_buy_quote_type_ids: [], adjusted_price_type_ids: [],
    shopping_sell_liquidity_type_ids: [], output_buy_liquidity_type_ids: [], system_cost_indices: [],
    inventory_cost_type_ids: [34], inventory_sell_liquidity_type_ids: [],
  },
};
renderValuation({ market_snapshot: { status: "fresh", resources: [] },
  pricing_options: { inventory_valuation_method: "recorded_cost", solar_system_id: 30000142 }, economics });
assert.equal(elements.economicsCashRequired.textContent, "0.00 ISK");
assert.equal(elements.economicsCashSurplus.textContent, "100.00 ISK");
assert.equal(elements.economicsProfit.textContent, "—");
assert.match(elements.consumedInventory.children[0].textContent, /Tritanium: Recorded unit cost missing/);
assert.match(elements.valuationNote.textContent, /Inventory valuation is incomplete/);
console.log("Inventory input, exact prices, validation, and incomplete-profit rendering passed.");

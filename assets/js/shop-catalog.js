// Product catalog data + DOM rendering. Renders into .display before filter/cart
// run (defer order). Edit CATALOG below to add/remove items.
(function () {
  // Item fields: `image` (rooted at assets/images/items/) else materials derive
  // materials/<sub>/<name_underscored>.avif; `fittings` (boats/structures, names
  // resolved against kind:"fitting" rows). Blueprints are ordered by total runs
  // (the legacy per-item `maxRuns` field is no longer read).
  const CATALOG = [
    { name: "Zirnitra",                  category: "boats",      sub: "dreadnought",        price: 4_400_000_000, image: "boats/zirnitra-render-256.avif",   fittings: ["Siege Fit", "Gank Fit", "Shield Tank"] },
    { name: "Moros",                     category: "boats",      sub: "dreadnought",        price:             0, image: "boats/moros-render-256.avif",      fittings: ["Siege Fit", "Armor Tank", "Gank Fit"] },
    { name: "Naglfar",                   category: "boats",      sub: "dreadnought",        price:             0, image: "boats/naglfar-render-256.avif",    fittings: ["Siege Fit", "Shield Tank", "Tackle Fit"] },
    { name: "Phoenix",                   category: "boats",      sub: "dreadnought",        price:             0, image: "boats/phoenix-render-256.avif",    fittings: ["Siege Fit", "Shield Tank"] },
    { name: "Revelation",                category: "boats",      sub: "dreadnought",        price:             0, image: "boats/revelation-render-256.avif", fittings: ["Siege Fit", "Armor Tank"] },
    { name: "Apostle",                   category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/apostle-render-256.avif",    fittings: ["Triage Fit", "Armor Tank"] },
    { name: "Minokawa",                  category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/minokawa-render-256.avif",   fittings: ["Triage Fit", "Shield Tank"] },
    { name: "Ninazu",                    category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/ninazu-render-256.avif",     fittings: ["Triage Fit", "Armor Tank"] },
    { name: "Lif",                       category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/lif-render-256.avif",        fittings: ["Triage Fit", "Shield Tank"] },
    { name: "Ark",                       category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/ark-render-256.avif",        fittings: ["Travel Fit", "Cargo Fit", "Armor Tank"] },
    { name: "Rhea",                      category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/rhea-render-256.avif",       fittings: ["Travel Fit", "Cargo Fit", "Shield Tank"] },
    { name: "Anshar",                    category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/anshar-render-256.avif",     fittings: ["Travel Fit", "Cargo Fit"] },
    { name: "Nomad",                     category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/nomad-render-256.avif",      fittings: ["Travel Fit", "Cargo Fit"] },
    { name: "Rorqual",                   category: "boats",      sub: "industrial-capital", price:             0, image: "boats/rorqual-render-256.avif",    fittings: ["Mining Fit", "PANIC Fit", "Shield Tank"] },
    { name: "Astrahus",                  category: "structures", sub: "citadel",            price:             0, image: "structures/astrahus-render-256.avif", fittings: ["Defense Fit"] },
    { name: "Raitaru",                   category: "structures", sub: "engineering",        price:             0, image: "structures/raitaru-render-256.avif",  fittings: ["Industry Fit"] },
    { name: "Athanor",                   category: "structures", sub: "refinery",           price:             0, image: "structures/athanor-render-256.avif",  fittings: ["Reaction Fit"] },
    { name: "Fermionic Condensates",     category: "materials",  sub: "reaction",  price:             0 },
    { name: "Hypersynaptic Fibers",      category: "materials",  sub: "reaction",  price:             0 },
    { name: "Nanotransistors",           category: "materials",  sub: "reaction",  price:             0 },
    { name: "Nonlinear Metamaterials",   category: "materials",  sub: "reaction",  price:             0 },
    { name: "Photonic Metamaterials",    category: "materials",  sub: "reaction",  price:             0 },
    { name: "Plasmonic Metamaterials",   category: "materials",  sub: "reaction",  price:             0 },
    { name: "Terahertz Metamaterials",   category: "materials",  sub: "reaction",  price:             0 },
    { name: "Sylramic Fibers",           category: "materials",  sub: "reaction",  price:      8_750_000 },
    { name: "Reinforced Carbon Fiber",   category: "materials",  sub: "reaction",  price:     12_300_000, image: "materials/reaction/reinforced_carbon_fiber.avif" },
    { name: "Titanium Carbide",          category: "materials",  sub: "reaction",  price:      9_600_000, image: "materials/reaction/titanium_carbide.avif" },
    { name: "Tungsten Carbide",          category: "materials",  sub: "reaction",  price:     10_100_000, image: "materials/reaction/tungsten_carbide.avif" },
    { name: "Pressurized Oxidizers",     category: "materials",  sub: "reaction",  price:      7_800_000 },
    { name: "Ferrogel",                  category: "materials",  sub: "reaction",  price:     15_800_000 },
    { name: "Fernite Carbide",           category: "materials",  sub: "reaction",  price:     11_200_000 },
    { name: "Crystalline Carbonide",     category: "materials",  sub: "reaction",  price:              0 },
    { name: "Fullerides",                category: "materials",  sub: "reaction",  price:              0 },
    { name: "Phenolic Composites",       category: "materials",  sub: "reaction",  price:              0 },
    { name: "Broadcast Node",              category: "materials",  sub: "planetary", price:      5_200_000 },
    { name: "Integrity Response Drones",   category: "materials",  sub: "planetary", price:      6_100_000 },
    { name: "Nano-Factory",                category: "materials",  sub: "planetary", price:             0 },
    { name: "Organic Mortar Applicators",  category: "materials",  sub: "planetary", price:             0 },
    { name: "Recursive Computing Module",  category: "materials",  sub: "planetary", price:             0 },
    { name: "Self-Harmonizing Power Core", category: "materials",  sub: "planetary", price:             0 },
    { name: "Sterile Conduits",            category: "materials",  sub: "planetary", price:      4_700_000 },
    { name: "Wetware Mainframe",           category: "materials",  sub: "planetary", price:      9_300_000 },
    { name: "Capital Capacitor Battery Blueprint",    category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_capacitor_battery_blueprint.avif",    maxRuns: 20 },
    { name: "Capital Computer System Blueprint",      category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_computer_system_blueprint.avif",      maxRuns: 20 },
    { name: "Capital Construction Parts Blueprint",   category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_construction_parts_blueprint.avif",   maxRuns: 30 },
    { name: "Capital Corporate Hangar Bay Blueprint", category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_corporate_hangar_bay_blueprint.avif", maxRuns: 10 },
    { name: "Capital Drone Bay Blueprint",            category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_drone_bay_blueprint.avif",            maxRuns: 10 },
    { name: "Capital Power Generator Blueprint",      category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_power_generator_blueprint.avif",      maxRuns: 20 },
    { name: "Capital Propulsion Engine Blueprint",    category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_propulsion_engine_blueprint.avif",    maxRuns: 20 },
    { name: "Capital Sensor Cluster Blueprint",       category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_sensor_cluster_blueprint.avif",       maxRuns: 10 },
    { name: "Capital Shield Emitter Blueprint",       category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_shield_emitter_blueprint.avif",       maxRuns: 20 },
    { name: "Capital Ship Maintenance Bay Blueprint", category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_ship_maintenance_bay_blueprint.avif", maxRuns: 10 },

    // ── Fittings ── add-ons for boats/structures (referenced by `fittings`);
    // kind:"fitting" keeps them out of the grid/filters — no card.
    { name: "Shield Tank",  price:   250_000_000, kind: "fitting" },
    { name: "Armor Tank",   price:   240_000_000, kind: "fitting" },
    { name: "Siege Fit",    price:   600_000_000, kind: "fitting" },
    { name: "Triage Fit",   price:   550_000_000, kind: "fitting" },
    { name: "Gank Fit",     price:   820_000_000, kind: "fitting" },
    { name: "Tackle Fit",   price:    90_000_000, kind: "fitting" },
    { name: "Travel Fit",   price:   140_000_000, kind: "fitting" },
    { name: "Cargo Fit",    price:   160_000_000, kind: "fitting" },
    { name: "Mining Fit",   price:   320_000_000, kind: "fitting" },
    { name: "PANIC Fit",    price:   210_000_000, kind: "fitting" },
    { name: "Defense Fit",  price: 1_200_000_000, kind: "fitting" },
    { name: "Industry Fit", price:   700_000_000, kind: "fitting" },
    { name: "Reaction Fit", price:   650_000_000, kind: "fitting" },
  ];

  const { normalizeName, formatPrice } = window.ShopUtils;

  const SHOP_IMAGE_ROOT = "../assets/images/items/";

  // Fittings live in CATALOG as `kind: "fitting"` rows; resolve them into a flat
  // list + a by-name lookup, and pre-resolve each item's `fittings` names.
  const FITTINGS = CATALOG
    .filter((i) => i.kind === "fitting")
    .map((i) => ({ name: i.name, price: i.price }));
  const fittingByName = new Map(FITTINGS.map((f) => [normalizeName(f.name), f]));
  const fittingsByItem = new Map();
  CATALOG.forEach((item) => {
    if (!Array.isArray(item.fittings) || item.fittings.length === 0) return;
    const resolved = item.fittings
      .map((name) => fittingByName.get(normalizeName(name)))
      .filter(Boolean);
    if (resolved.length) fittingsByItem.set(normalizeName(item.name), resolved);
  });

  // Resolved fittings for an item (boats/structures), or [] when it has none.
  function fittingsFor(itemName) {
    return fittingsByItem.get(normalizeName(itemName)) || [];
  }
  // A single fitting record by name, or null.
  function getFittingByName(name) {
    return fittingByName.get(normalizeName(name)) || null;
  }

  // Terse element builder for the flip configurator markup below.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  // `root` is the path prefix to images/items/ for the current page. Shop pages
  // sit one level deep so default to "../"; the home page passes its own root.
  function imagePath(item, root = SHOP_IMAGE_ROOT) {
    if (item.image) return `${root}${item.image}`;
    if (item.category === "materials" && item.sub) {
      const file = item.name.toLowerCase().replace(/[\s-]+/g, "_") + ".avif";
      return `${root}materials/${item.sub}/${file}`;
    }
    return "";
  }

  function badgeText(item) {
    const raw = item.sub || item.category || "";
    const label = raw.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    // Blueprints are sold as copies — tag the badge "BPC" (e.g. "Component BPC").
    return item.category === "blueprints" ? `${label} BPC` : label;
  }

  // Icons live alongside items (…/images/items/ ↔ …/images/icons/), so derive
  // the icon root from whatever image root the page passed in.
  function iconRootFrom(imageRoot) {
    return imageRoot.replace(/items\/?$/, "icons/");
  }

  // ±1 qty stepper; shop-cart reads/clamps [data-flip-qty-input]. Used for every
  // category (blueprints' qty == total runs).
  function flipStepper(value) {
    const wrap = el("div", "flip-stepper");

    const minus = el("button", "flip-step-btn", "−");
    minus.type = "button";
    minus.dataset.flipStep = "";
    minus.dataset.flipDir = "-1";
    minus.setAttribute("aria-label", "Decrease quantity");

    const input = el("input", "flip-num");
    input.type = "text";
    input.inputMode = "numeric";
    input.value = String(value);
    input.dataset.flipQtyInput = "";
    input.setAttribute("aria-label", "Quantity");

    const plus = el("button", "flip-step-btn", "+");
    plus.type = "button";
    plus.dataset.flipStep = "";
    plus.dataset.flipDir = "1";
    plus.setAttribute("aria-label", "Increase quantity");

    wrap.appendChild(minus);
    wrap.appendChild(input);
    wrap.appendChild(plus);
    return wrap;
  }

  // Coarse ±100k / ±1m qty button (materials); shares the qty stepper's hook.
  function flipBigBtn(label, dir, amount) {
    const b = el("button", "flip-bigstep-btn", label);
    b.type = "button";
    b.dataset.flipStep = "";
    b.dataset.flipDir = String(dir);
    b.dataset.flipAmount = String(amount);
    b.setAttribute("aria-label", `${dir < 0 ? "Decrease" : "Increase"} quantity by ${amount.toLocaleString("en-US")}`);
    return b;
  }

  // Flip back face — the configurator. Boats/structures get a fitting dropdown;
  // all get a qty stepper (blueprints label it "Total runs", materials add
  // ±100k / ±1m). Add/Options buttons live in the action row (createCard), not
  // here; shop-cart reads these on ADD.
  function createFlipBack(item, fittings) {
    const cat = item.category;
    const isBlueprint = cat === "blueprints";
    const isMat = cat === "materials";
    const back = el("div", "item-card-face item-card-face--back");
    back.setAttribute("aria-hidden", "true");

    back.appendChild(el("p", "flip-item-name", item.name));

    // Fitting dropdown — boats + structures. Always offers "No Fitting".
    if ((cat === "boats" || cat === "structures") && fittings.length) {
      const field = el("div", "flip-field");
      field.appendChild(el("span", "flip-label flip-label--fitting", "Fitting:"));
      const select = el("select", "flip-select");
      select.dataset.flipFitting = "";
      select.setAttribute("aria-label", `Fitting for ${item.name}`);
      const none = el("option", null, "No Fitting");
      none.value = "";
      select.appendChild(none);
      fittings.forEach((f) => {
        const opt = el("option", null, `${f.name} — +${formatPrice(f.price)} ISK`);
        opt.value = f.name;
        opt.dataset.price = String(f.price);
        select.appendChild(opt);
      });
      field.appendChild(select);
      const price = el("p", "flip-fit-price", "+0 ISK");
      price.dataset.flipFitPrice = "";
      field.appendChild(price);
      back.appendChild(field);
    }

    // Quantity — all variants. Sits at the bottom, above the action row.
    // Blueprints: qty == total runs. Materials: ±100k / ±1m coarse steps.
    const qtyField = el("div", "flip-field flip-qty-field");
    qtyField.appendChild(el("span", "flip-label", isBlueprint ? "Total runs" : "Quantity"));
    if (isMat) {
      const row = el("div", "flip-bigstep-row");
      row.appendChild(flipBigBtn("-1m", -1, 1000000));
      row.appendChild(flipBigBtn("-100k", -1, 100000));
      row.appendChild(flipStepper(1));
      row.appendChild(flipBigBtn("+100k", 1, 100000));
      row.appendChild(flipBigBtn("+1m", 1, 1000000));
      qtyField.appendChild(row);
    } else {
      qtyField.appendChild(flipStepper(1));
    }
    back.appendChild(qtyField);

    return back;
  }

  // Generalized product card (shop, home highlights, any page with shop-utils +
  // catalog); defaults produce the interactive shop card. opts: tag/href,
  // imageRoot, categorized, action, actionLabel, priceText, stockText,
  // stockValue, outOfStock, extraClass, ariaLabel, flip.
  function createCard(item, opts = {}) {
    const {
      tag = "article",
      href = null,
      imageRoot = SHOP_IMAGE_ROOT,
      categorized = true,
      action = "button",
      actionLabel = "ADD TO CART",
      priceText = null,
      stockText = null,
      stockValue = null,
      outOfStock = false,
      extraClass = "",
      ariaLabel = null,
      flip = false,
    } = opts;

    const card = document.createElement(tag);
    card.className = "item-card"
      + (categorized ? " item-card--cat" : "")
      + (outOfStock ? " item-card--out-of-stock" : "")
      + (extraClass ? ` ${extraClass}` : "");
    if (href) card.href = href;
    if (ariaLabel) card.setAttribute("aria-label", ariaLabel);

    card.dataset.name = normalizeName(item.name);
    card.dataset.price = String(item.price);
    card.dataset.category = item.category;
    if (item.sub) card.dataset.sub = item.sub;

    const badge = document.createElement("span");
    badge.className = "card-badge";
    badge.textContent = badgeText(item);

    const media = document.createElement("div");
    media.className = "item-media";

    const img = document.createElement("img");
    img.src = imagePath(item, imageRoot);
    img.alt = item.name;
    img.width = 128;
    img.height = 128;
    img.loading = "lazy";
    img.decoding = "async";
    media.appendChild(img);

    // Blueprints carry a research box (ME/TE, e.g. "10/20") straddling the
    // bottom edge of the art. Defaults to 10/20; per-item `research` overrides.
    if (item.category === "blueprints") {
      const research = item.research || "10/20";
      const bp = document.createElement("span");
      bp.className = "bp-research";
      bp.textContent = research;
      bp.setAttribute("aria-label", `Material/time efficiency ${research}`);
      media.appendChild(bp);
    }

    const heading = document.createElement("h2");
    // blueprint title drops the " Blueprint" suffix visually (badge reads "… BPC")
    // but keeps it in textContent so cart/filter/order see the canonical name
    const bpSuffix = item.category === "blueprints" && / Blueprint$/.test(item.name);
    if (bpSuffix) {
      heading.appendChild(document.createTextNode(item.name.replace(/ Blueprint$/, "")));
      const suffix = document.createElement("span");
      suffix.className = "bp-title-suffix";
      suffix.textContent = " Blueprint";
      heading.appendChild(suffix);
    } else {
      heading.textContent = item.name;
    }

    const text = document.createElement("div");
    text.className = "text";

    const footer = document.createElement("div");
    footer.className = "item-card-footer";

    const priceP = document.createElement("p");
    const priceStrong = document.createElement("strong");
    priceStrong.textContent = "Price:";
    priceP.appendChild(priceStrong);
    if (priceText !== null) priceP.appendChild(document.createTextNode(` ${priceText}`));

    const stockState = document.createElement("div");
    stockState.className = "stock-state";
    if (stockValue !== null) stockState.setAttribute("aria-label", `In stock: ${stockValue}`);
    const stockIcon = document.createElement("img");
    stockIcon.src = `${iconRootFrom(imageRoot)}stock.avif`;
    stockIcon.alt = "";
    stockIcon.width = 64;
    stockIcon.height = 64;
    stockIcon.setAttribute("aria-hidden", "true");
    const stockCount = document.createElement("p");
    stockCount.className = "stock-state-count";
    if (stockText !== null) {
      stockCount.setAttribute("aria-hidden", "true");
      stockCount.textContent = stockText;
    }
    stockState.appendChild(stockIcon);
    stockState.appendChild(stockCount);

    footer.appendChild(priceP);
    footer.appendChild(stockState);

    // action row (outside the flip so it stays put): filled --primary add button
    // + secondary Options on flip cards (relabelled Close while flipped)
    const controls = document.createElement("div");
    controls.className = "item-buy-controls";
    if (action !== "none") {
      const actionEl = document.createElement(action === "button" ? "button" : "span");
      actionEl.className = action === "button" ? "buy-button buy-button--primary" : "buy-button";
      actionEl.textContent = actionLabel;
      if (action === "button") {
        actionEl.type = "button";
        actionEl.setAttribute("data-cart-add", "");
        actionEl.setAttribute("aria-label", `Add ${item.name} to cart`);
      }
      controls.appendChild(actionEl);

      if (flip && action === "button") {
        const cfg = document.createElement("button");
        cfg.type = "button";
        cfg.className = "buy-button buy-button--secondary";
        cfg.textContent = "Options";
        cfg.setAttribute("data-flip-toggle", "");
        cfg.setAttribute("aria-label", `Options for ${item.name}`);
        controls.appendChild(cfg);
      }
    }

    text.appendChild(footer);

    // badge is absolute, so DOM order = visual order: image, heading, price/stock
    const frontChildren = [badge, media, heading, text];

    if (flip) {
      // Wrap the front content + configurator back face in the rotating flip
      // element; shop-cart reads the back controls when ADD is clicked.
      const flipEl = document.createElement("div");
      flipEl.className = "item-card-flip";
      const front = document.createElement("div");
      front.className = "item-card-face item-card-face--front";
      front.setAttribute("aria-hidden", "false");
      frontChildren.forEach((child) => front.appendChild(child));
      flipEl.appendChild(front);
      flipEl.appendChild(createFlipBack(item, fittingsFor(item.name)));
      card.appendChild(flipEl);
      card.appendChild(controls);
    } else {
      frontChildren.forEach((child) => card.appendChild(child));
      if (action !== "none") card.appendChild(controls);
    }
    return card;
  }

  function renderCatalog() {
    const display = document.querySelector(".display");
    if (!display) return;
    const frag = document.createDocumentFragment();
    // Fittings are add-ons (kind:"fitting") — they never get a card of their own.
    CATALOG.forEach((item) => {
      if (item.kind === "fitting") return;
      frag.appendChild(createCard(item, { flip: true }));
    });
    display.appendChild(frag);
  }

  // Shared product data + helpers for home highlights + any card-rendering page.
  // (renderCatalog no-ops without a .display, e.g. home.)
  window.ShopCatalog = {
    CATALOG, imagePath, badgeText, createCard,
    fittingsFor, fittingByName: getFittingByName, FITTINGS,
  };

  renderCatalog();
})();

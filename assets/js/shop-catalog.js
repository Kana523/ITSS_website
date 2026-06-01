// Product catalog data + DOM rendering for the shop. Renders into .display
// before filter/cart's DOMContentLoaded handlers run (loaded with defer
// before those scripts). Edit CATALOG below to add/remove/edit items.
(function () {
  // Image path resolution:
  //   - explicit `image` field is used as-is, rooted at assets/images/items/
  //   - else, items in category "materials" with a sub derive
  //     materials/<sub>/<name_with_underscores>.avif
  //     (e.g. "Carbon Polymers" → carbon_polymers.avif,
  //      "Nano-Factory"    → nano_factory.avif)
  //   - non-materials without `image` will render a broken <img> (must specify)
  const CATALOG = [
    { name: "Zirnitra",                  category: "boats",      sub: "dreadnought",        price: 4_400_000_000, image: "boats/zirnitra-render-256.avif" },
    { name: "Moros",                     category: "boats",      sub: "dreadnought",        price:             0, image: "boats/moros-render-256.avif" },
    { name: "Naglfar",                   category: "boats",      sub: "dreadnought",        price:             0, image: "boats/naglfar-render-256.avif" },
    { name: "Phoenix",                   category: "boats",      sub: "dreadnought",        price:             0, image: "boats/phoenix-render-256.avif" },
    { name: "Revelation",                category: "boats",      sub: "dreadnought",        price:             0, image: "boats/revelation-render-256.avif" },
    { name: "Apostle",                   category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/apostle-render-256.avif" },
    { name: "Minokawa",                  category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/minokawa-render-256.avif" },
    { name: "Ninazu",                    category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/ninazu-render-256.avif" },
    { name: "Lif",                       category: "boats",      sub: "force-auxiliary",    price:             0, image: "boats/lif-render-256.avif" },
    { name: "Ark",                       category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/ark-render-256.avif" },
    { name: "Rhea",                      category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/rhea-render-256.avif" },
    { name: "Anshar",                    category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/anshar-render-256.avif" },
    { name: "Nomad",                     category: "boats",      sub: "jump-freighter",     price:             0, image: "boats/nomad-render-256.avif" },
    { name: "Rorqual",                   category: "boats",      sub: "industrial-capital", price:             0, image: "boats/rorqual-render-256.avif" },
    { name: "Astrahus",                  category: "structures", sub: "citadel",            price:             0, image: "structures/astrahus-render-256.avif" },
    { name: "Raitaru",                   category: "structures", sub: "engineering",        price:             0, image: "structures/raitaru-render-256.avif" },
    { name: "Athanor",                   category: "structures", sub: "refinery",           price:             0, image: "structures/athanor-render-256.avif" },
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
    { name: "Capital Capacitor Battery Blueprint",    category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_capacitor_battery_blueprint.avif" },
    { name: "Capital Computer System Blueprint",      category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_computer_system_blueprint.avif" },
    { name: "Capital Construction Parts Blueprint",   category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_construction_parts_blueprint.avif" },
    { name: "Capital Corporate Hangar Bay Blueprint", category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_corporate_hangar_bay_blueprint.avif" },
    { name: "Capital Drone Bay Blueprint",            category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_drone_bay_blueprint.avif" },
    { name: "Capital Power Generator Blueprint",      category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_power_generator_blueprint.avif" },
    { name: "Capital Propulsion Engine Blueprint",    category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_propulsion_engine_blueprint.avif" },
    { name: "Capital Sensor Cluster Blueprint",       category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_sensor_cluster_blueprint.avif" },
    { name: "Capital Shield Emitter Blueprint",       category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_shield_emitter_blueprint.avif" },
    { name: "Capital Ship Maintenance Bay Blueprint", category: "blueprints", sub: "component", price: 0, image: "blueprints/component/capital_ship_maintenance_bay_blueprint.avif" },
  ];

  const { normalizeName } = window.ShopUtils;

  const SHOP_IMAGE_ROOT = "../assets/images/items/";

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

  // Generalized product card, shared across the shop, the home highlights row,
  // and any other page that loads shop-utils + shop-catalog. Options cover the
  // per-page differences; defaults produce the interactive shop card.
  //   tag / href      — "article" (shop) or "a" linking elsewhere (home)
  //   imageRoot       — path prefix to images/items/ for the current page
  //   categorized     — category-coloured badge + glow (shop/trade) vs gold (home)
  //   action          — "button" (data-cart-add) | "span" (label) | "none"
  //   actionLabel     — text on the button/label
  //   priceText       — value after "Price:"; omit to let shop-filter fill it
  //   stockText       — stock-count text; omit to let shop-filter fill it
  //   stockValue      — number for the "In stock: N" aria-label; omit for none
  //   outOfStock      — apply the muted out-of-stock treatment (shop only)
  //   extraClass      — extra class(es) on the card (e.g. "highlight-card")
  //   ariaLabel       — accessible label for link cards
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
    // Blueprint cards drop the redundant " Blueprint" suffix from the visible
    // title (the badge already reads "… BPC"), but keep it in textContent so the
    // cart/filter/order still see the canonical name.
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
    stockIcon.src = `${iconRootFrom(imageRoot)}stock.png`;
    stockIcon.alt = "";
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

    const controls = document.createElement("div");
    controls.className = "item-buy-controls";
    if (action !== "none") {
      const actionEl = document.createElement(action === "button" ? "button" : "span");
      actionEl.className = "buy-button";
      actionEl.textContent = actionLabel;
      if (action === "button") {
        actionEl.type = "button";
        actionEl.setAttribute("data-cart-add", "");
        actionEl.setAttribute("aria-label", `Add ${item.name} to cart`);
      }
      controls.appendChild(actionEl);
    }

    text.appendChild(footer);
    text.appendChild(controls);

    // Badge is absolutely positioned, so DOM order here is the visual order:
    // image, heading, then the price/stock/action block.
    card.appendChild(badge);
    card.appendChild(media);
    card.appendChild(heading);
    card.appendChild(text);
    return card;
  }

  function renderCatalog() {
    const display = document.querySelector(".display");
    if (!display) return;
    const frag = document.createDocumentFragment();
    CATALOG.forEach((item) => frag.appendChild(createCard(item)));
    display.appendChild(frag);
  }

  // Shared product data + helpers, consumed by the home highlights row and any
  // page that wants product cards. (renderCatalog no-ops where there is no
  // .display, e.g. the home page.)
  window.ShopCatalog = { CATALOG, imagePath, badgeText, createCard };

  renderCatalog();
})();

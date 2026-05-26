// Product catalog data + DOM rendering for the shop. Renders into .display
// before filter/cart's DOMContentLoaded handlers run (loaded with defer
// before those scripts). Edit CATALOG below to add/remove/edit items.
(function () {
  // Image path resolution:
  //   - explicit `image` field is used as-is, rooted at assets/images/items/
  //   - else, items in category "materials" with a sub derive
  //     materials/<sub>/<sku-with-underscores>.avif
  //   - non-materials without `image` will render a broken <img> (must specify)
  const CATALOG = [
    { sku: "zirnitra",                  name: "Zirnitra",                  category: "ships",      sub: "dreadnought",        price: 4_400_000_000, image: "ships/zirnitra-render-128.avif" },
    { sku: "moros",                     name: "Moros",                     category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "naglfar",                   name: "Naglfar",                   category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "phoenix",                   name: "Phoenix",                   category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "revelation",                name: "Revelation",                category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "apostle",                   name: "Apostle",                   category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "minokawa",                  name: "Minokawa",                  category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "ninazu",                    name: "Ninazu",                    category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "lif",                       name: "Lif",                       category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "ark",                       name: "Ark",                       category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "rhea",                      name: "Rhea",                      category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "anshar",                    name: "Anshar",                    category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "nomad",                     name: "Nomad",                     category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "rorqual",                   name: "Rorqual",                   category: "ships",      sub: "industrial-capital", price:             0, image: "ships/zirnitra-render-128.avif" },
    { sku: "sylramic-fibers",           name: "Sylramic Fibers",           category: "materials",  sub: "reaction",  price:      8_750_000 },
    { sku: "reinforced-carbon-fiber",   name: "Reinforced Carbon Fiber",   category: "materials",  sub: "reaction",  price:     12_300_000, image: "materials/reaction/reinforced_carbon_fiber.avif" },
    { sku: "titanium-carbide",          name: "Titanium Carbide",          category: "materials",  sub: "reaction",  price:      9_600_000, image: "materials/reaction/titanium_carbide.avif" },
    { sku: "tungsten-carbide",          name: "Tungsten Carbide",          category: "materials",  sub: "reaction",  price:     10_100_000, image: "materials/reaction/tungsten_carbide.avif" },
    { sku: "pressurized-oxidizers",     name: "Pressurized Oxidizers",     category: "materials",  sub: "reaction",  price:      7_800_000 },
    { sku: "ferrogel",                  name: "Ferrogel",                  category: "materials",  sub: "reaction",  price:     15_800_000 },
    { sku: "fernite-carbide",           name: "Fernite Carbide",           category: "materials",  sub: "reaction",  price:     11_200_000 },
    { sku: "broadcast-node",            name: "Broadcast Node",            category: "materials",  sub: "planetary", price:      5_200_000 },
    { sku: "integrity-response-drones", name: "Integrity Response Drones", category: "materials",  sub: "planetary", price:      6_100_000 },
    { sku: "sterile-conduits",          name: "Sterile Conduits",          category: "materials",  sub: "planetary", price:      4_700_000 },
    { sku: "wetware-mainframe",         name: "Wetware Mainframe",         category: "materials",  sub: "planetary", price:      9_300_000 },
    { sku: "capital-armor-plates",      name: "Capital Armor Plates",      category: "materials",  sub: "component", price:     68_000_000, image: "ships/zirnitra-render-128.avif" },
    { sku: "capital-capacitor-battery", name: "Capital Capacitor Battery", category: "materials",  sub: "component", price:     75_000_000, image: "ships/zirnitra-render-128.avif" },
    { sku: "capital-cargo-bay",         name: "Capital Cargo Bay",         category: "materials",  sub: "component", price:     59_000_000, image: "ships/zirnitra-render-128.avif" },
  ];

  function imagePath(item) {
    if (item.image) return `../assets/images/items/${item.image}`;
    if (item.category === "materials" && item.sub) {
      const file = item.sku.replace(/-/g, "_") + ".avif";
      return `../assets/images/items/materials/${item.sub}/${file}`;
    }
    return "";
  }

  function badgeText(item) {
    const raw = item.sub || item.category || "";
    return raw.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  }

  function renderCard(item) {
    const article = document.createElement("article");
    article.className = "item-card";
    article.dataset.sku = item.sku;
    article.dataset.price = String(item.price);
    article.dataset.category = item.category;
    if (item.sub) article.dataset.sub = item.sub;

    const badge = document.createElement("span");
    badge.className = "card-badge";
    badge.textContent = badgeText(item);

    const heading = document.createElement("h2");
    heading.textContent = item.name;

    const img = document.createElement("img");
    img.src = imagePath(item);
    img.alt = item.name;

    const text = document.createElement("div");
    text.className = "text";

    const footer = document.createElement("div");
    footer.className = "item-card-footer";

    const priceP = document.createElement("p");
    const priceStrong = document.createElement("strong");
    priceStrong.textContent = "Price:";
    priceP.appendChild(priceStrong);

    const stockState = document.createElement("div");
    stockState.className = "stock-state";
    const stockIcon = document.createElement("img");
    stockIcon.src = "../assets/images/icons/stock.png";
    stockIcon.alt = "";
    stockIcon.setAttribute("aria-hidden", "true");
    const stockCount = document.createElement("p");
    stockCount.className = "stock-state-count";
    stockState.appendChild(stockIcon);
    stockState.appendChild(stockCount);

    footer.appendChild(priceP);
    footer.appendChild(stockState);

    const controls = document.createElement("div");
    controls.className = "item-buy-controls";
    const buyBtn = document.createElement("button");
    buyBtn.type = "button";
    buyBtn.className = "buy-button";
    buyBtn.setAttribute("data-cart-add", "");
    buyBtn.setAttribute("aria-label", `Add ${item.name} to cart`);
    buyBtn.textContent = "ADD TO CART";
    controls.appendChild(buyBtn);

    text.appendChild(footer);
    text.appendChild(controls);

    article.appendChild(badge);
    article.appendChild(heading);
    article.appendChild(img);
    article.appendChild(text);
    return article;
  }

  function renderCatalog() {
    const display = document.querySelector(".display");
    if (!display) return;
    const frag = document.createDocumentFragment();
    CATALOG.forEach((item) => frag.appendChild(renderCard(item)));
    display.appendChild(frag);
  }

  renderCatalog();
})();

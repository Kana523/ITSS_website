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
    { name: "Zirnitra",                  category: "ships",      sub: "dreadnought",        price: 4_400_000_000, image: "ships/zirnitra-render-128.avif" },
    { name: "Moros",                     category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Naglfar",                   category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Phoenix",                   category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Revelation",                category: "ships",      sub: "dreadnought",        price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Apostle",                   category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Minokawa",                  category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Ninazu",                    category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Lif",                       category: "ships",      sub: "force-auxiliary",    price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Ark",                       category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Rhea",                      category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Anshar",                    category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Nomad",                     category: "ships",      sub: "jump-freighter",     price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Rorqual",                   category: "ships",      sub: "industrial-capital", price:             0, image: "ships/zirnitra-render-128.avif" },
    { name: "Astrahus",                  category: "structures", sub: "citadel",            price:             0 },
    { name: "Raitaru",                   category: "structures", sub: "engineering",        price:             0 },
    { name: "Athanor",                   category: "structures", sub: "refinery",           price:             0 },
    { name: "Carbon Polymers",           category: "materials",  sub: "reaction",  price:             0 },
    { name: "Ceramic Fibers",            category: "materials",  sub: "reaction",  price:             0 },
    { name: "Fermionic Condensates",     category: "materials",  sub: "reaction",  price:             0 },
    { name: "Fluxed Condensates",        category: "materials",  sub: "reaction",  price:             0 },
    { name: "Hypersynaptic Fibers",      category: "materials",  sub: "reaction",  price:             0 },
    { name: "Metallofullerene Plating",  category: "materials",  sub: "reaction",  price:             0 },
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
    { name: "Broadcast Node",              category: "materials",  sub: "planetary", price:      5_200_000 },
    { name: "Integrity Response Drones",   category: "materials",  sub: "planetary", price:      6_100_000 },
    { name: "Nano-Factory",                category: "materials",  sub: "planetary", price:             0 },
    { name: "Organic Mortar Applicators",  category: "materials",  sub: "planetary", price:             0 },
    { name: "Recursive Computing Module",  category: "materials",  sub: "planetary", price:             0 },
    { name: "Self-Harmonizing Power Core", category: "materials",  sub: "planetary", price:             0 },
    { name: "Sterile Conduits",            category: "materials",  sub: "planetary", price:      4_700_000 },
    { name: "Wetware Mainframe",           category: "materials",  sub: "planetary", price:      9_300_000 },
    { name: "Capital Armor Plates",      category: "materials",  sub: "component", price:     68_000_000, image: "ships/zirnitra-render-128.avif" },
    { name: "Capital Capacitor Battery", category: "materials",  sub: "component", price:     75_000_000, image: "ships/zirnitra-render-128.avif" },
    { name: "Capital Cargo Bay",         category: "materials",  sub: "component", price:     59_000_000, image: "ships/zirnitra-render-128.avif" },
  ];

  const { normalizeName } = window.ShopUtils;

  function imagePath(item) {
    if (item.image) return `../assets/images/items/${item.image}`;
    if (item.category === "materials" && item.sub) {
      const file = item.name.toLowerCase().replace(/[\s-]+/g, "_") + ".avif";
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
    article.dataset.name = normalizeName(item.name);
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

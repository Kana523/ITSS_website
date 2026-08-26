(() => {
  "use strict";

  const loader = document.currentScript;
  if (!loader?.src) return;
  const baseUrl = new URL("./", loader.src);

  const core = document.createElement("script");
  core.src = new URL("industry-core.js", baseUrl).href;
  core.async = false;
  core.addEventListener("load", () => {
    const implants = document.createElement("script");
    implants.src = new URL("industry-implants.js", baseUrl).href;
    implants.async = false;
    implants.addEventListener("load", () => {
      const configs = document.createElement("script");
      configs.src = new URL("industry-configs.js", baseUrl).href;
      configs.async = false;

      const loadMarket = () => {
        const market = document.createElement("script");
        market.src = new URL("industry-market.js", baseUrl).href;
        market.async = false;
        document.head.append(market);
      };
      configs.addEventListener("load", loadMarket, { once: true });
      configs.addEventListener("error", loadMarket, { once: true });
      document.head.append(configs);
    });
    document.head.append(implants);
  });
  document.head.append(core);
})();

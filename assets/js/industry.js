(() => {
  "use strict";

  const loader = document.currentScript;
  if (!loader?.src) return;
  const baseUrl = new URL("./", loader.src);

  const loadCore = () => {
    const core = document.createElement("script");
    core.src = new URL("industry-core.js", baseUrl).href;
    core.async = false;
    core.addEventListener("load", () => {
      const implants = document.createElement("script");
      implants.src = new URL("industry-implants.js", baseUrl).href;
      implants.async = false;
      implants.addEventListener("load", () => {
        const tabs = document.createElement("script");
        tabs.src = new URL("industry-tabs.js", baseUrl).href;
        tabs.async = false;
        const loadConfigs = () => {
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
        };
        tabs.addEventListener("load", loadConfigs, { once: true });
        tabs.addEventListener("error", loadConfigs, { once: true });
        document.head.append(tabs);
      });
      document.head.append(implants);
    });
    document.head.append(core);
  };

  const skills = document.createElement("script");
  skills.src = new URL("industry-skills.js", baseUrl).href;
  skills.async = false;
  skills.addEventListener("load", loadCore, { once: true });
  skills.addEventListener("error", loadCore, { once: true });
  document.head.append(skills);
})();

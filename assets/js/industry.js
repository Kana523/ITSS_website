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
        const reprocessing = document.createElement("script");
        reprocessing.src = new URL("industry-reprocessing.js", baseUrl).href;
        reprocessing.async = false;
        const loadTabs = () => {
          const tabs = document.createElement("script");
          tabs.src = new URL("industry-tabs.js", baseUrl).href;
          tabs.async = false;
          const loadOverrides = () => {
            const overrides = document.createElement("script");
            overrides.src = new URL("industry-overrides.js", baseUrl).href;
            overrides.async = false;
            overrides.addEventListener("load", loadConfigs, { once: true });
            overrides.addEventListener("error", loadConfigs, { once: true });
            document.head.append(overrides);
          };
          const loadConfigs = () => {
            const configs = document.createElement("script");
            configs.src = new URL("industry-configs.js", baseUrl).href;
            configs.async = false;

            const loadSystems = () => {
              const systems = document.createElement("script");
              systems.src = new URL("industry-systems.js", baseUrl).href;
              systems.async = false;
              const loadMarket = () => {
                const market = document.createElement("script");
                market.src = new URL("industry-market.js", baseUrl).href;
                market.async = false;
                document.head.append(market);
              };
              systems.addEventListener("load", loadMarket, { once: true });
              systems.addEventListener("error", loadMarket, { once: true });
              document.head.append(systems);
            };
            configs.addEventListener("load", loadSystems, { once: true });
            configs.addEventListener("error", loadSystems, { once: true });
            document.head.append(configs);
          };
          tabs.addEventListener("load", loadOverrides, { once: true });
          tabs.addEventListener("error", loadOverrides, { once: true });
          document.head.append(tabs);
        };
        reprocessing.addEventListener("load", loadTabs, { once: true });
        reprocessing.addEventListener("error", loadTabs, { once: true });
        document.head.append(reprocessing);
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

const trigger = document.getElementById("ccp-legal-trigger");
const tooltip = document.getElementById("ccp-legal-tooltip");

if (trigger && tooltip) {
  function placeTooltip(x, y) {
    // Show first so we can measure its size.
    tooltip.style.display = "block";
    const rect = tooltip.getBoundingClientRect();
    const padding = 10;

    let left = x - rect.width / 2;
    let top = y - rect.height - 15;

    left = Math.max(padding, Math.min(left, window.innerWidth - rect.width - padding));
    if (top < padding) top = y + 15;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  trigger.addEventListener("mousemove", (e) => {
    placeTooltip(e.clientX, e.clientY);
  });

  trigger.addEventListener("focus", () => {
    placeTooltip(window.innerWidth / 2, window.innerHeight / 2);
  });

  trigger.addEventListener("mouseleave", () => {
    tooltip.style.display = "none";
  });

  trigger.addEventListener("blur", () => {
    tooltip.style.display = "none";
  });

  // Keep click-toggle support only when the trigger is not a link.
  if (trigger.tagName.toLowerCase() !== "a") {
    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      const isVisible = tooltip.style.display === "block";
      if (isVisible) {
        tooltip.style.display = "none";
      } else {
        placeTooltip(window.innerWidth / 2, window.innerHeight / 2);
      }
    });
  }

  document.addEventListener("click", (e) => {
    if (!trigger.contains(e.target) && !tooltip.contains(e.target)) {
      tooltip.style.display = "none";
    }
  });
}

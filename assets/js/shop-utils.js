// Shared shop-wide formatting and parsing helpers. Exposed as window.ShopUtils.
(function () {
  function formatPrice(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "0";

    function formatUnit(divisor, suffix) {
      const unitValue = amount / divisor;
      const trimmed = unitValue
        .toFixed(1)
        .replace(/(\.\d*?[1-9])0+$/, "$1")
        .replace(/\.0+$/, "");
      return `${trimmed}${suffix}`;
    }

    if (amount >= 1000000000000) return formatUnit(1000000000000, "t");
    if (amount >= 1000000000) return formatUnit(1000000000, "b");
    if (amount >= 1000000) return formatUnit(1000000, "m");
    if (amount >= 1000) return formatUnit(1000, "k");
    return `${Math.round(amount)}`;
  }

  function formatPriceLong(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "0";
    return Math.round(amount).toLocaleString("en-US");
  }

  function formatPriceCompact(value) {
    const num = Number(value);
    if (!Number.isFinite(num) || num === 0) return "";
    const abs = Math.abs(num);
    const sign = num < 0 ? "-" : "";
    let scaled, suffix;
    if (abs >= 1e12)      { scaled = abs / 1e12; suffix = "t"; }
    else if (abs >= 1e9)  { scaled = abs / 1e9;  suffix = "b"; }
    else                  { scaled = abs / 1e6;  suffix = "m"; }
    const text = scaled.toFixed(2).replace(/\.?0+$/, "");
    return `~${sign}${text}${suffix}`;
  }

  function parsePriceToIsk(rawValue) {
    const multipliers = {
      k: 1000,
      thousand: 1000,
      m: 1000000,
      mil: 1000000,
      million: 1000000,
      b: 1000000000,
      bil: 1000000000,
      billion: 1000000000,
      t: 1000000000000,
      tril: 1000000000000,
      trillion: 1000000000000
    };

    const text = String(rawValue || "").trim();
    if (!text) return 0;

    const direct = Number(text.replace(/,/g, ""));
    if (Number.isFinite(direct) && direct > 0) return direct;

    const match = text.match(/^([\d.,]+)\s*([a-zA-Z]+)?\s*(?:isk)?$/i);
    if (!match) return 0;

    const numericValue = Number(match[1].replace(/,/g, ""));
    if (!Number.isFinite(numericValue) || numericValue <= 0) return 0;

    const unit = String(match[2] || "").toLowerCase();
    const multiplier = unit ? (multipliers[unit] || 1) : 1;
    return numericValue * multiplier;
  }

  // canonical lookup key — trim, lowercase, collapse whitespace (keep hyphens);
  // identical on frontend + Apps Script sheet so matches survive casing/spacing
  function normalizeName(value) {
    return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  // true on local dev hosts (file://, localhost, loopback, *.local); read at call time
  function isLocalHost() {
    const host = (location.hostname || "").toLowerCase();
    return location.protocol === "file:" ||
      ["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"].includes(host) ||
      host.endsWith(".local");
  }

  window.ShopUtils = { formatPrice, formatPriceLong, formatPriceCompact, parsePriceToIsk, normalizeName, isLocalHost };
})();

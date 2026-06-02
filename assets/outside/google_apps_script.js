const STOCK_SHEET_NAME    = "Stock";
const ORDERS_SHEET_NAME   = "WebOrders";
const ARCHIVE_SHEET_NAME  = "WebOrdersArchive";

// WebOrders columns (1-indexed): orderId, status, customerRef, timestamp,
// key, name, category, qty, unitPrice, lineTotal, orderTotal, isExtra.
// `key` = normalized name (lookup), `name` = display; extras use the parent key.
const WEBORDERS_HEADERS = [
  "orderId", "status", "customerRef", "timestamp",
  "key", "name", "category", "qty",
  "unitPrice", "lineTotal", "orderTotal", "isExtra"
];
const STATUS_VALUES = ["New", "In progress", "Fulfilled", "Cancelled"];
const RESERVED_STATUSES = new Set(["new", "in progress"]);
const COMPLETED_STATUSES = new Set(["fulfilled", "cancelled"]);

// canonical lookup key — mirrors ShopUtils.normalizeName (trim, lowercase,
// collapse whitespace, keep hyphens)
function normalizeName(value) {
  return String(value == null ? "" : value).trim().toLowerCase().replace(/\s+/g, " ");
}

// Reads Stock!A:E. Returns Map keyed by normalizeName(col A) →
// { stock, price, next_stock, weeks }.
function readStockData(sheet) {
  const out = new Map();
  if (!sheet || sheet.getLastRow() < 2) return out;
  const lastRow = sheet.getLastRow();
  const ae = sheet.getRange(2, 1, lastRow - 1, 5).getValues();
  for (let i = 0; i < ae.length; i++) {
    const key = normalizeName(ae[i][0]);
    if (!key) continue;
    out.set(key, {
      stock: toInt(ae[i][1]),
      price: toNumber(ae[i][2]),
      next_stock: toText(ae[i][3]),
      weeks: toNumber(ae[i][4])
    });
  }
  return out;
}

// sums reserved qty per item key (orders with status New / In progress). Status
// is on each order's first row, so scan twice: map orderId→status, then sum
// (skipping extras). Reads col F (name) for back-compat with old col E SKUs.
function computeReservations(ordersSheet) {
  const reserved = new Map();
  if (!ordersSheet || ordersSheet.getLastRow() < 2) return reserved;
  const rows = ordersSheet.getRange(2, 1, ordersSheet.getLastRow() - 1, WEBORDERS_HEADERS.length).getValues();
  const statusByOrder = new Map();
  for (const row of rows) {
    const orderId = String(row[0] || "").trim();
    const status  = String(row[1] || "").trim().toLowerCase();
    if (orderId && status && !statusByOrder.has(orderId)) {
      statusByOrder.set(orderId, status);
    }
  }
  for (const row of rows) {
    const orderId = String(row[0] || "").trim();
    if (!orderId) continue;
    if (!RESERVED_STATUSES.has(statusByOrder.get(orderId) || "")) continue;
    const isExtra = row[11] === true || String(row[11]).toLowerCase() === "true";
    if (isExtra) continue;
    const key = normalizeName(row[5]);
    const qty = toInt(row[7]);
    if (key && qty) reserved.set(key, (reserved.get(key) || 0) + qty);
  }
  return reserved;
}

// 8 chars from a 32-symbol alphabet — collision-safe at the user's scale.
function generateInternalOrderId() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no I/O/0/1
  const bytes = new Array(8);
  for (let i = 0; i < 8; i++) bytes[i] = alphabet[Math.floor(Math.random() * alphabet.length)];
  return bytes.join("");
}

// one-time: write headers to row 1 of WebOrders + WebOrdersArchive (creates the
// archive if missing). Run manually before going live.
function setupOrdersSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const orders = ss.getSheetByName(ORDERS_SHEET_NAME);
  if (!orders) throw new Error('Missing "' + ORDERS_SHEET_NAME + '" sheet.');
  const archive = ss.getSheetByName(ARCHIVE_SHEET_NAME) || ss.insertSheet(ARCHIVE_SHEET_NAME);
  for (const sheet of [orders, archive]) {
    sheet.getRange(1, 1, 1, WEBORDERS_HEADERS.length)
         .setValues([WEBORDERS_HEADERS])
         .setFontWeight("bold");
  }
  Logger.log("Headers written to WebOrders and WebOrdersArchive.");
}

// moves Fulfilled/Cancelled orders into WebOrdersArchive (time trigger or manual).
// Holds the script lock so it can't race doPost; preserves the header row.
function archiveCompletedOrders() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) { Logger.log("Archive: couldn't acquire lock."); return; }
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const orders  = ss.getSheetByName(ORDERS_SHEET_NAME);
    const archive = ss.getSheetByName(ARCHIVE_SHEET_NAME);
    if (!orders || !archive) { Logger.log("Archive: missing sheet."); return; }
    if (orders.getLastRow() < 2) return;

    const data = orders.getRange(2, 1, orders.getLastRow() - 1, WEBORDERS_HEADERS.length).getValues();

    // Map orderId -> status (first non-blank)
    const statusByOrder = new Map();
    for (const row of data) {
      const orderId = String(row[0] || "").trim();
      const status  = String(row[1] || "").trim().toLowerCase();
      if (orderId && status && !statusByOrder.has(orderId)) statusByOrder.set(orderId, status);
    }

    const toArchive = [];
    const toKeep = [];
    for (const row of data) {
      const orderId = String(row[0] || "").trim();
      const status = statusByOrder.get(orderId) || "";
      if (orderId && COMPLETED_STATUSES.has(status)) toArchive.push(row);
      else toKeep.push(row);
    }

    if (toArchive.length === 0) return;

    archive.getRange(archive.getLastRow() + 1, 1, toArchive.length, WEBORDERS_HEADERS.length).setValues(toArchive);

    // Rewrite WebOrders: clear data rows, then write the keep set.
    orders.getRange(2, 1, data.length, WEBORDERS_HEADERS.length).clearContent().clearDataValidations();
    if (toKeep.length) {
      orders.getRange(2, 1, toKeep.length, WEBORDERS_HEADERS.length).setValues(toKeep);
      // Reapply dropdown validation to first row of each surviving order.
      const seen = new Set();
      const rule = SpreadsheetApp.newDataValidation()
        .requireValueInList(STATUS_VALUES, true).setAllowInvalid(false).build();
      for (let i = 0; i < toKeep.length; i++) {
        const orderId = String(toKeep[i][0] || "").trim();
        if (orderId && !seen.has(orderId)) {
          orders.getRange(2 + i, 2).setDataValidation(rule);
          seen.add(orderId);
        }
      }
    }
    SpreadsheetApp.flush();
    Logger.log(`Archived ${toArchive.length} row(s) across ${new Set(toArchive.map(r => r[0])).size} order(s).`);
  } finally {
    lock.releaseLock();
  }
}

function doGet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const stockSheet = ss.getSheetByName(STOCK_SHEET_NAME);
  if (!stockSheet) {
    return jsonResponse({ error: 'Missing "Stock" sheet.' });
  }

  const stockData = readStockData(stockSheet);
  if (stockData.size === 0) return jsonResponse({});

  const reserved = computeReservations(ss.getSheetByName(ORDERS_SHEET_NAME));

  const payload = {};
  stockData.forEach((info, key) => {
    const available = Math.max(0, info.stock - (reserved.get(key) || 0));
    payload[key] = {
      stock: available,
      price: info.price,
      next_stock: info.next_stock,
      weeks: info.weeks
    };
  });
  return jsonResponse(payload);
}

// Order submission. POST text/plain JSON: { action:"order", turnstileToken,
// items, [orderId|charName] }. Generates an internal orderId; the customer's
// value (client ID or charName) goes to customerRef. Materials clamped to
// (Stock!B − reservations); response carries `adjusted` for clamped lines.
function doPost(e) {
  let body;
  try {
    body = JSON.parse(e?.postData?.contents || "{}");
  } catch (err) {
    return jsonResponse({ ok: false, error: "Invalid JSON body." });
  }

  if (body.action !== "order") {
    return jsonResponse({ ok: false, error: "Unknown action." });
  }

  const turnstileToken = String(body.turnstileToken || "").trim();
  if (!turnstileToken) return jsonResponse({ ok: false, error: "Missing verification token." });
  if (!verifyTurnstile(turnstileToken)) return jsonResponse({ ok: false, error: "Verification failed." });

  const rawOrderId = String(body.orderId || "").trim();
  const charName   = String(body.charName || "").trim().slice(0, 100);
  let customerRef;
  if (rawOrderId) {
    if (!/^[A-Z0-9]{20}$/.test(rawOrderId)) return jsonResponse({ ok: false, error: "Invalid Order ID." });
    customerRef = rawOrderId;
  } else if (charName) {
    customerRef = charName;
  } else {
    return jsonResponse({ ok: false, error: "Missing Order ID or character name." });
  }

  const items = Array.isArray(body.items) ? body.items : [];
  if (items.length === 0) return jsonResponse({ ok: false, error: "No items in order." });

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const stockSheet  = ss.getSheetByName(STOCK_SHEET_NAME);
  const ordersSheet = ss.getSheetByName(ORDERS_SHEET_NAME);
  if (!stockSheet)  return jsonResponse({ ok: false, error: 'Missing "Stock" sheet.' });
  if (!ordersSheet) return jsonResponse({ ok: false, error: 'Missing "WebOrders" sheet.' });

  const stockData = readStockData(stockSheet);
  for (const item of items) {
    const key = normalizeName(item.name);
    if (!stockData.has(key)) return jsonResponse({ ok: false, error: "Order contains an unrecognised item." });
  }

  // Lock around read-validate-write so concurrent orders can't both consume
  // the same last material unit.
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return jsonResponse({ ok: false, error: "Server busy, please retry." });

  try {
    const reserved = computeReservations(ordersSheet);
    const orderId = generateInternalOrderId();
    const timestamp = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
    const adjusted = [];
    const lineSpecs = [];

    // Pass 1: clamp materials. Lines clamped to 0 are dropped.
    for (const item of items) {
      const name = String(item.name || "").trim();
      const key = normalizeName(name);
      const info = stockData.get(key);
      const requestedQty = toInt(item.qty);
      if (requestedQty <= 0) continue;

      const isMaterial = String(item.category || "").trim().toLowerCase() === "materials";
      let acceptedQty = requestedQty;
      if (isMaterial) {
        const available = Math.max(0, info.stock - (reserved.get(key) || 0));
        if (requestedQty > available) {
          acceptedQty = available;
          adjusted.push({ name, requestedQty, acceptedQty, isMaterial: true });
        }
      } else if (requestedQty > Math.max(0, info.stock - (reserved.get(key) || 0))) {
        // Non-material over-order — flag but don't clamp (corp will fulfill later).
        adjusted.push({
          name, requestedQty, acceptedQty,
          isMaterial: false,
          available: Math.max(0, info.stock - (reserved.get(key) || 0))
        });
      }
      if (acceptedQty <= 0) continue;

      lineSpecs.push({
        key,
        name,
        category: String(item.category || "").trim(),
        qty: acceptedQty,
        unitPrice: info.price || 0,
        extras: Array.isArray(item.extras) ? item.extras : []
      });
    }

    if (lineSpecs.length === 0) {
      return jsonResponse({ ok: false, error: "Nothing in stock for any of the requested items.", adjusted });
    }

    // orderTotal computed AFTER clamping
    const orderTotal = lineSpecs.reduce((sum, line) => {
      let total = line.unitPrice * line.qty;
      line.extras.forEach(ex => {
        const exPrice = stockData.get(normalizeName(ex.name))?.price || 0;
        total += exPrice * toInt(ex.qty);
      });
      return sum + total;
    }, 0);

    // build rows; status only on the first row. Col E = key, col F = display name.
    const rows = [];
    let isFirst = true;
    for (const line of lineSpecs) {
      const lineTotal = line.unitPrice * line.qty;
      rows.push([
        orderId, isFirst ? "New" : "", customerRef, timestamp,
        line.key, line.name, line.category, line.qty,
        line.unitPrice, lineTotal, orderTotal, false
      ]);
      isFirst = false;
      for (const ex of line.extras) {
        const exName  = String(ex.name || "").trim();
        const exQty   = toInt(ex.qty);
        const exPrice = stockData.get(normalizeName(exName))?.price || 0;
        rows.push([
          orderId, "", customerRef, timestamp,
          line.key, exName, line.category, exQty,
          exPrice, exPrice * exQty, orderTotal, true
        ]);
      }
    }

    const firstRowOnSheet = ordersSheet.getLastRow() + 1;
    ordersSheet.getRange(firstRowOnSheet, 1, rows.length, WEBORDERS_HEADERS.length).setValues(rows);

    // Dropdown validation on the status cell of the first row only.
    const statusRule = SpreadsheetApp.newDataValidation()
      .requireValueInList(STATUS_VALUES, true)
      .setAllowInvalid(false)
      .build();
    ordersSheet.getRange(firstRowOnSheet, 2).setDataValidation(statusRule);

    SpreadsheetApp.flush();
    return jsonResponse({
      ok: true,
      orderId,
      customerRef,
      total: orderTotal,
      rowsWritten: rows.length,
      adjusted
    });
  } finally {
    lock.releaseLock();
  }
}

// verifies a Turnstile token (secret in Script Properties TURNSTILE_SECRET);
// true on success, false on any failure
function verifyTurnstile(token) {
  const secret = PropertiesService.getScriptProperties().getProperty("TURNSTILE_SECRET");
  if (!secret) {
    Logger.log("Turnstile: TURNSTILE_SECRET script property is not set.");
    return false;
  }

  try {
    const response = UrlFetchApp.fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "post",
      payload: { secret, response: token },
      muteHttpExceptions: true
    });
    const result = JSON.parse(response.getContentText() || "{}");
    if (result.success === true) return true;
    Logger.log("Turnstile rejected token: " + JSON.stringify(result["error-codes"] || []));
    return false;
  } catch (err) {
    Logger.log("Turnstile verification threw: " + err);
    return false;
  }
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function toInt(value) {
  const parsed = parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function toNumber(value) {
  const parsed = Number(String(value ?? "").trim().replace(/,/g, ""));
  return Number.isFinite(parsed) ? Math.max(0, parsed) : null;
}

function toText(value) {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), "yyyy-MM-dd");
  }
  return String(value || "").trim();
}

// Pulls best Buy/Sell for Stock!A names from Jita, Amarr, C-J6MT → cols F:K
// (row 2+); also overwrites Stock!B with the corp "Sales" hangar count. Cols
// C–E untouched. Names sent to ESI as-is, matched back by normalizeName.
// Jita/Amarr: public ESI. Auth scopes (see authSetupStep1/2):
//   esi-markets.structure_markets.v1          (C-J6MT prices)
//   esi-assets.read_corporation_assets.v1     (Sales hangar)
//   esi-corporations.read_divisions.v1        (find Sales hangar by name)
const ESI_BASE         = "https://esi.evetech.net/latest";
const ESI_AUTH_BASE    = "https://login.eveonline.com/v2/oauth";
const CJ6MT_STRUCTURE  = 1049588174021;

function pullPrices() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const src = ss.getSheetByName(STOCK_SHEET_NAME);
  if (!src) throw new Error('Missing "' + STOCK_SHEET_NAME + '" sheet.');
  if (src.getLastRow() < 2) throw new Error('"' + STOCK_SHEET_NAME + '" sheet is empty.');

  // item names from A2:A
  const lastRow = src.getLastRow();
  const aValues = src.getRange(2, 1, lastRow - 1, 1).getValues().flat();
  const names = [];
  for (let i = 0; i < aValues.length; i++) {
    const name = String(aValues[i] || "").trim();
    if (!name) continue;
    names.push(name);
  }

  // 1. resolve names → type_ids (keyed by normalizeName)
  const typeIds = {};
  for (let i = 0; i < names.length; i += 500) {
    const batch = names.slice(i, i + 500);
    const resp = UrlFetchApp.fetch(ESI_BASE + "/universe/ids/", {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(batch),
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error("universe/ids failed: " + resp.getContentText());
    }
    const data = JSON.parse(resp.getContentText());
    (data.inventory_types || []).forEach(t => typeIds[normalizeName(t.name)] = t.id);
  }

  // 2. access token (for C-J6MT orders + corp assets); skip both if auth fails
  let accessToken = null;
  let tokenError = null;
  try {
    accessToken = getAccessToken();
  } catch (e) {
    tokenError = e.message;
    Logger.log("Auth skipped: " + tokenError);
  }

  // 2a. C-J6MT structure book (all types)
  let cjOrders = [];
  let cjError = tokenError;
  if (accessToken) {
    try {
      cjOrders = fetchStructureOrders(CJ6MT_STRUCTURE, accessToken);
    } catch (e) {
      cjError = e.message;
      Logger.log("C-J6MT skipped: " + cjError);
    }
  }

  // 2b. corp "Sales" hangar (overwrites Stock!B); needs Director + asset/division scopes
  let salesStockByType = null;  // null = couldn't read (don't overwrite B)
  let salesError = tokenError;
  if (accessToken) {
    try {
      const charId = getCharacterIdFromToken(accessToken);
      const corpId = fetchCorporationId(charId);
      const assets = fetchCorporationAssets(corpId, accessToken);
      const divisions = fetchCorpDivisions(corpId, accessToken);
      const sales = divisions.find(d => String(d.name || "").trim().toLowerCase() === "sales");
      if (!sales) throw new Error('No hangar division named "Sales".');
      const flag = "CorpSAG" + sales.division;
      salesStockByType = {};
      for (const a of assets) {
        if (a.location_flag === flag) {
          salesStockByType[a.type_id] = (salesStockByType[a.type_id] || 0) + (a.quantity || 0);
        }
      }
    } catch (e) {
      salesError = e.message;
      Logger.log("Sales hangar skipped: " + salesError);
    }
  }

  const HUBS = [
    { label: "Jita",   region: 10000002, station: 60003760, structure: false },
    { label: "Amarr",  region: 10000043, station: 60008494, structure: false },
    { label: "C-J6MT", structure: true }
  ];

  // 3. per item: 6 hub prices → F:K; rewrite Stock!B to the Sales count
  //    (start from current values for one atomic write)
  const currentB = src.getRange(2, 2, names.length, 1).getValues();
  const priceRows = [];
  for (let i = 0; i < names.length; i++) {
    const tid = typeIds[normalizeName(names[i])];
    if (!tid) { priceRows.push(["", "", "", "", "", ""]); continue; }

    const row = [];
    for (const hub of HUBS) {
      const orders = hub.structure
        ? cjOrders.filter(o => o.type_id === tid)
        : fetchRegionOrders(hub.region, tid).filter(o => o.location_id === hub.station);
      const buys  = orders.filter(o =>  o.is_buy_order).map(o => o.price);
      const sells = orders.filter(o => !o.is_buy_order).map(o => o.price);
      row.push(buys.length  ? Math.max(...buys)  : "");
      row.push(sells.length ? Math.min(...sells) : "");
    }
    priceRows.push(row);

    if (salesStockByType) {
      currentB[i][0] = salesStockByType[tid] || 0;
    }
  }

  const mainHeaders = ["Jita Buy", "Jita Sell", "Amarr Buy", "Amarr Sell", "C-J6MT Buy", "C-J6MT Sell"];
  src.getRange(1, 6, 1, mainHeaders.length).setValues([mainHeaders]).setFontWeight("bold");
  src.getRange(2, 6, priceRows.length, mainHeaders.length).setValues(priceRows);
  if (salesStockByType) src.getRange(2, 2, currentB.length, 1).setValues(currentB);

  if (cjError)     src.getRange(1, 10).setNote("C-J6MT skipped: " + cjError);
  if (salesError && !cjError) src.getRange(1, 2).setNote("Sales hangar: " + salesError);
}

// ESI fetch with 420 (rate-limit) + 502/503/504 backoff and error-budget awareness:
// 420 waits X-Esi-Error-Limit-Reset (capped); 5xx retries with exponential backoff
// (×3); pauses briefly when <10 errors remain in the budget.
function esiFetch(url, options) {
  options = options || { muteHttpExceptions: true };
  if (!options.muteHttpExceptions) options.muteHttpExceptions = true;

  const MAX_ATTEMPTS = 4;
  let lastResp = null;
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const resp = UrlFetchApp.fetch(url, options);
    const code = resp.getResponseCode();
    const hdrs = resp.getHeaders();
    const remain = parseInt(hdrs["x-esi-error-limit-remain"] || hdrs["X-Esi-Error-Limit-Remain"] || "100", 10);
    lastResp = resp;

    if (code === 420) {
      const reset = parseInt(hdrs["x-esi-error-limit-reset"] || hdrs["X-Esi-Error-Limit-Reset"] || "30", 10);
      const wait = Math.min(Math.max(reset, 5), 65) * 1000;
      Logger.log(`ESI 420 on ${url} — sleeping ${wait/1000}s before retry`);
      Utilities.sleep(wait);
      continue;
    }
    if (code === 502 || code === 503 || code === 504) {
      const wait = Math.min(2000 * Math.pow(2, attempt), 8000);
      Logger.log(`ESI ${code} on ${url} — sleeping ${wait/1000}s before retry (attempt ${attempt + 1}/${MAX_ATTEMPTS})`);
      Utilities.sleep(wait);
      continue;
    }
    // Be polite when the error budget is nearly drained
    if (remain < 10) Utilities.sleep(2000);
    return resp;
  }
  return lastResp;
}

function fetchRegionOrders(regionId, typeId) {
  let all = [];
  let page = 1;
  while (true) {
    const url = `${ESI_BASE}/markets/${regionId}/orders/?type_id=${typeId}&order_type=all&page=${page}`;
    const resp = esiFetch(url);
    if (resp.getResponseCode() !== 200) break;
    const chunk = JSON.parse(resp.getContentText() || "[]");
    if (!chunk.length) break;
    all = all.concat(chunk);
    const headers = resp.getHeaders();
    const pages = parseInt(headers["x-pages"] || headers["X-Pages"] || "1", 10);
    if (page >= pages) break;
    page++;
  }
  return all;
}

function fetchCorporationId(characterId) {
  const resp = esiFetch(`${ESI_BASE}/characters/${characterId}/`);
  if (resp.getResponseCode() !== 200) {
    throw new Error(`characters/${characterId} HTTP ${resp.getResponseCode()}: ${resp.getContentText()}`);
  }
  const data = JSON.parse(resp.getContentText());
  if (!data.corporation_id) throw new Error("No corporation_id in character profile.");
  return data.corporation_id;
}

function fetchCorpDivisions(corporationId, accessToken) {
  const resp = esiFetch(`${ESI_BASE}/corporations/${corporationId}/divisions/`, {
    headers: { Authorization: "Bearer " + accessToken },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error(`corporations/${corporationId}/divisions HTTP ${resp.getResponseCode()}: ${resp.getContentText()}`);
  }
  const data = JSON.parse(resp.getContentText() || "{}");
  return Array.isArray(data.hangar) ? data.hangar : [];
}

function fetchCorporationAssets(corporationId, accessToken) {
  let all = [];
  let page = 1;
  while (true) {
    const url = `${ESI_BASE}/corporations/${corporationId}/assets/?page=${page}`;
    const resp = esiFetch(url, {
      headers: { Authorization: "Bearer " + accessToken },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error(`corporations/${corporationId}/assets HTTP ${resp.getResponseCode()}: ${resp.getContentText()}`);
    }
    const chunk = JSON.parse(resp.getContentText() || "[]");
    if (!chunk.length) break;
    all = all.concat(chunk);
    const headers = resp.getHeaders();
    const pages = parseInt(headers["x-pages"] || headers["X-Pages"] || "1", 10);
    if (page >= pages) break;
    page++;
  }
  return all;
}

// Decode a JWT payload (base64url) without verifying — we only need the `sub`
// claim, which ESI sets to "CHARACTER:EVE:<id>".
function getCharacterIdFromToken(token) {
  const parts = String(token).split(".");
  if (parts.length !== 3) throw new Error("Access token is not a JWT.");
  let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const text = Utilities.newBlob(Utilities.base64Decode(b64)).getDataAsString();
  const payload = JSON.parse(text);
  const m = String(payload.sub || "").match(/CHARACTER:EVE:(\d+)/);
  if (!m) throw new Error("Character id not found in token sub claim.");
  return parseInt(m[1], 10);
}

function fetchStructureOrders(structureId, accessToken) {
  let all = [];
  let page = 1;
  while (true) {
    const url = `${ESI_BASE}/markets/structures/${structureId}/?page=${page}`;
    const resp = esiFetch(url, {
      headers: { Authorization: "Bearer " + accessToken },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error(`structures/${structureId} HTTP ${resp.getResponseCode()}: ${resp.getContentText()}`);
    }
    const chunk = JSON.parse(resp.getContentText() || "[]");
    if (!chunk.length) break;
    all = all.concat(chunk);
    const headers = resp.getHeaders();
    const pages = parseInt(headers["x-pages"] || headers["X-Pages"] || "1", 10);
    if (page >= pages) break;
    page++;
  }
  return all;
}

// === ESI OAuth ===
//
// One-time setup for C-J6MT prices + Sales hangar count:
// 1) Go to https://developers.eveonline.com/applications and create an application.
//      Connection Type: Authentication & API Access
//      Permissions:     esi-markets.structure_markets.v1
//                       esi-assets.read_corporation_assets.v1
//                       esi-corporations.read_divisions.v1
//      Callback URL:    https://localhost/callback   (or any URL you control)
//    Sales hangar additionally requires that the authed character holds the
//    Director role in the corporation.
// 2) Apps Script: Project Settings → Script Properties → add three properties:
//      EVE_CLIENT_ID       (from the app page)
//      EVE_CLIENT_SECRET   (from the app page)
//      EVE_CALLBACK_URL    (exactly what you set above)
// 3) Run authSetupStep1(). Open the URL printed in the Execution log, log in with
//    the character that has docking access at C-J6MT, and authorize.
// 4) Your browser will be redirected to your callback URL. Copy the value of the
//    "code" query parameter from the address bar.
// 5) Run authSetupStep2("paste_the_code_here"). On success it stores
//    EVE_REFRESH_TOKEN and you're done — pullPrices() will use it automatically.

function authSetupStep1() {
  const props = PropertiesService.getScriptProperties();
  const clientId = props.getProperty("EVE_CLIENT_ID");
  const callback = props.getProperty("EVE_CALLBACK_URL");
  if (!clientId || !callback) {
    throw new Error("Set EVE_CLIENT_ID and EVE_CALLBACK_URL in Script Properties first.");
  }
  const state = Utilities.getUuid();
  props.setProperty("EVE_AUTH_STATE", state);

  const url = `${ESI_AUTH_BASE}/authorize/` +
    `?response_type=code` +
    `&redirect_uri=${encodeURIComponent(callback)}` +
    `&client_id=${encodeURIComponent(clientId)}` +
    `&scope=${encodeURIComponent("esi-markets.structure_markets.v1 esi-assets.read_corporation_assets.v1 esi-corporations.read_divisions.v1")}` +
    `&state=${state}`;
  Logger.log("Open this URL in your browser, authorize, then copy the `code` query param from the redirect:");
  Logger.log(url);
}

function authSetupStep2(code) {
  if (!code) throw new Error('Pass the auth code: authSetupStep2("the_code_from_the_redirect")');
  const props = PropertiesService.getScriptProperties();
  const clientId = props.getProperty("EVE_CLIENT_ID");
  const secret   = props.getProperty("EVE_CLIENT_SECRET");
  if (!clientId || !secret) throw new Error("Missing EVE_CLIENT_ID or EVE_CLIENT_SECRET.");

  const resp = UrlFetchApp.fetch(`${ESI_AUTH_BASE}/token`, {
    method: "post",
    headers: {
      Authorization: "Basic " + Utilities.base64Encode(clientId + ":" + secret)
    },
    payload: { grant_type: "authorization_code", code: String(code).trim() },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("Token exchange failed: " + resp.getContentText());
  }
  const data = JSON.parse(resp.getContentText());
  props.setProperty("EVE_REFRESH_TOKEN", data.refresh_token);
  props.deleteProperty("EVE_AUTH_STATE");
  Logger.log("Refresh token stored. Run pullPrices() now.");
}

// Diagnostic: prints the character + scopes granted on the current refresh
// token. Run this when you get 401s to confirm which scopes are actually live.
function authDebug() {
  const token = getAccessToken();
  const parts = token.split(".");
  let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const payload = JSON.parse(Utilities.newBlob(Utilities.base64Decode(b64)).getDataAsString());
  Logger.log("Character:  " + payload.name + " (" + payload.sub + ")");
  Logger.log("Expires:    " + new Date(payload.exp * 1000));
  const scopes = Array.isArray(payload.scp) ? payload.scp : [payload.scp];
  Logger.log("Scopes (" + scopes.length + "):");
  scopes.forEach(s => Logger.log("  - " + s));
}

function getAccessToken() {
  const props = PropertiesService.getScriptProperties();
  const refresh  = props.getProperty("EVE_REFRESH_TOKEN");
  const clientId = props.getProperty("EVE_CLIENT_ID");
  const secret   = props.getProperty("EVE_CLIENT_SECRET");
  if (!refresh)  throw new Error("No EVE_REFRESH_TOKEN. Run authSetupStep1 / authSetupStep2.");
  if (!clientId || !secret) throw new Error("Missing EVE_CLIENT_ID or EVE_CLIENT_SECRET.");

  const resp = UrlFetchApp.fetch(`${ESI_AUTH_BASE}/token`, {
    method: "post",
    headers: {
      Authorization: "Basic " + Utilities.base64Encode(clientId + ":" + secret)
    },
    payload: { grant_type: "refresh_token", refresh_token: refresh },
    muteHttpExceptions: true
  });
  if (resp.getResponseCode() !== 200) {
    throw new Error("Refresh failed: " + resp.getContentText());
  }
  const data = JSON.parse(resp.getContentText());
  // ESI rotates refresh tokens — persist the new one
  if (data.refresh_token && data.refresh_token !== refresh) {
    props.setProperty("EVE_REFRESH_TOKEN", data.refresh_token);
  }
  return data.access_token;
}

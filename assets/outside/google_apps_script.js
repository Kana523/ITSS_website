const STOCK_SHEET_NAME = "Stock";
const ORDERS_SHEET_NAME = "WebOrders";


function buildPriceMap(sheet) {
  if (!sheet || sheet.getLastRow() < 2) return new Map();
  const rows = sheet.getRange(2, 1, sheet.getLastRow() - 1, 3).getValues();
  const map = new Map();
  for (const row of rows) {
    const sku = String(row[0] || "").trim().toLowerCase();
    const price = toNumber(row[2]);
    if (sku && price !== null) map.set(sku, price);
  }
  return map;
}

function doGet() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(STOCK_SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ error: 'Missing "Stock" sheet.' });
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({});
  }

  const rows = sheet.getRange(2, 1, lastRow - 1, 5).getValues();
  const payload = {};

  for (const row of rows) {
    const sku = String(row[0] || "").trim().toLowerCase();
    if (!sku) continue;

    payload[sku] = {
      stock: toInt(row[1]),
      price: toNumber(row[2]),
      next_stock: toText(row[3]),
      weeks: toNumber(row[4])
    };
  }

  return jsonResponse(payload);
}

// Frontend posts as text/plain (to avoid the CORS preflight Apps Script can't answer)
// with a JSON body: { action: "order", turnstileToken, items, and ONE of:
//   - orderId: 20-char [A-Z0-9] string (Order ID flow), OR
//   - charName: free-form string (Character Name flow).
// Whichever is provided is written into the first column of each row.
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
  if (!turnstileToken) {
    return jsonResponse({ ok: false, error: "Missing verification token." });
  }
  if (!verifyTurnstile(turnstileToken)) {
    return jsonResponse({ ok: false, error: "Verification failed." });
  }

  const rawOrderId = String(body.orderId || "").trim();
  const charName = String(body.charName || "").trim().slice(0, 100);

  let identifier;
  if (rawOrderId) {
    if (!/^[A-Z0-9]{20}$/.test(rawOrderId)) {
      return jsonResponse({ ok: false, error: "Invalid Order ID." });
    }
    identifier = rawOrderId;
  } else if (charName) {
    identifier = charName;
  } else {
    return jsonResponse({ ok: false, error: "Missing Order ID or character name." });
  }

  const items = Array.isArray(body.items) ? body.items : [];
  if (items.length === 0) {
    return jsonResponse({ ok: false, error: "No items in order." });
  }

  // Load authoritative prices — one batch read, same spreadsheet as doGet
  const stockSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(STOCK_SHEET_NAME);
  if (!stockSheet) {
    return jsonResponse({ ok: false, error: 'Missing "Stock" sheet.' });
  }
  const priceMap = buildPriceMap(stockSheet);

  for (const item of items) {
    const sku = String(item.sku || "").trim().toLowerCase();
    if (!priceMap.has(sku)) {
      return jsonResponse({ ok: false, error: "Order contains an unrecognised item." });
    }
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ORDERS_SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ ok: false, error: 'Missing "WebOrders" sheet.' });
  }

  const tz = Session.getScriptTimeZone();
  const timestamp = Utilities.formatDate(new Date(), tz, "yyyy-MM-dd HH:mm:ss");

  const orderTotal = items.reduce((sum, item) => {
    const sku = String(item.sku || "").trim().toLowerCase();
    const unitPrice = priceMap.get(sku) || 0;
    const itemQty = toInt(item.qty);
    let line = unitPrice * itemQty;
    (Array.isArray(item.extras) ? item.extras : []).forEach((ex) => {
      const exPrice = priceMap.get(String(ex.name || "").trim().toLowerCase()) || 0;
      line += exPrice * toInt(ex.qty);
    });
    return sum + line;
  }, 0);

  const rows = [];
  items.forEach((item) => {
    const sku = String(item.sku || "").trim().toLowerCase();
    const name = String(item.name || "").trim();
    const category = String(item.category || "").trim();
    const qty = toInt(item.qty);
    const unitPrice = priceMap.get(sku) || 0;
    const lineTotal = unitPrice * qty;

    rows.push([
      identifier, timestamp, sku, name, category, qty, unitPrice, lineTotal, orderTotal
    ]);

    (Array.isArray(item.extras) ? item.extras : []).forEach((ex) => {
      const exName = String(ex.name || "").trim();
      const exQty = toInt(ex.qty);
      const exPrice = priceMap.get(exName.toLowerCase()) || 0;
      rows.push([
        identifier, timestamp, sku, exName, category, exQty, exPrice, exPrice * exQty, orderTotal
      ]);
    });
  });

  if (rows.length === 0) {
    return jsonResponse({ ok: false, error: "No valid rows to write." });
  }

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);

  return jsonResponse({ ok: true, identifier, total: orderTotal, rowsWritten: rows.length });
}

// Verifies a Cloudflare Turnstile token. Secret comes from Script Properties (TURNSTILE_SECRET).
// Returns true on success, false on any failure (network, missing secret, rejected token).
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

// Pulls best Buy/Sell prices for SKUs in column A of the "Stock" sheet from
// Jita 4-4, Amarr VIII, and C-J6MT Keepstar, plus the authed character's
// personal inventory, the corporation's inventory, and (for rows marked as
// "Material" in column N) a combined char+corp count held directly at the
// C-J6MT structure.
// Writes to columns F:M and O (headers in row 1, data from row 2). Column N
// is user-owned (Type) and never overwritten. Columns B–E (stock, price,
// next_stock, weeks) are left untouched.
// SKUs are dash-separated (e.g. "sylramic-fibers"); they're converted to
// spaces ("sylramic fibers") for the ESI name->id lookup.
// Jita/Amarr: public ESI, no auth. Other columns require ESI OAuth scopes:
//   esi-markets.structure_markets.v1   (C-J6MT prices)
//   esi-assets.read_assets.v1          (Char Stock, Sale Stock char part)
//   esi-assets.read_corporation_assets.v1   (Corp Stock, Sale Stock corp part — needs Director)
// See authSetupStep1/2.
const ESI_BASE         = "https://esi.evetech.net/latest";
const ESI_AUTH_BASE    = "https://login.eveonline.com/v2/oauth";
const CJ6MT_STRUCTURE  = 1049588174021;

function pullPrices() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const src = ss.getSheetByName(STOCK_SHEET_NAME);
  if (!src) throw new Error('Missing "' + STOCK_SHEET_NAME + '" sheet.');
  if (src.getLastRow() < 2) throw new Error('"' + STOCK_SHEET_NAME + '" sheet is empty.');

  // Skip header row. Read SKUs from A2:A and Types from N2:N (user-managed).
  const lastRow = src.getLastRow();
  const aValues = src.getRange(2, 1, lastRow - 1, 1).getValues().flat();
  const nValues = src.getRange(2, 14, lastRow - 1, 1).getValues().flat();
  const skus = [];
  const typeBySku = {};
  for (let i = 0; i < aValues.length; i++) {
    const sku = String(aValues[i] || "").trim();
    if (!sku) continue;
    skus.push(sku);
    typeBySku[sku] = String(nValues[i] || "").trim().toLowerCase();
  }

  // SKU "sylramic-fibers" -> query name "sylramic fibers"
  const skuToQuery = {};
  const queryNames = skus.map(sku => {
    const q = sku.replace(/-/g, " ");
    skuToQuery[sku] = q;
    return q;
  });

  // 1. Resolve names -> type_ids
  const typeIds = {};
  for (let i = 0; i < queryNames.length; i += 500) {
    const batch = queryNames.slice(i, i + 500);
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
    (data.inventory_types || []).forEach(t => typeIds[t.name.toLowerCase()] = t.id);
  }

  // 2. Fetch access token once. Used for both C-J6MT structure orders and
  //    the authed character's asset list. If auth fails, both are skipped.
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

  // 2b. Character assets summed by type_id (sum across all locations).
  //     Also build a separate map for items located directly at C-J6MT
  //     (used for the materials-only "Sale Stock" column).
  let charStockByType = {};
  let saleStockByType = {};
  let assetsError = tokenError;
  let charId = null;
  if (accessToken) {
    try {
      charId = getCharacterIdFromToken(accessToken);
      const assets = fetchCharacterAssets(charId, accessToken);
      for (const a of assets) {
        charStockByType[a.type_id] = (charStockByType[a.type_id] || 0) + (a.quantity || 0);
        if (a.location_id === CJ6MT_STRUCTURE) {
          saleStockByType[a.type_id] = (saleStockByType[a.type_id] || 0) + (a.quantity || 0);
        }
      }
    } catch (e) {
      assetsError = e.message;
      Logger.log("Char assets skipped: " + assetsError);
    }
  }

  // 2c. Corporation assets summed by type_id. Needs Director role + corp assets scope.
  //     Items at C-J6MT also feed Sale Stock.
  let corpStockByType = {};
  let corpError = tokenError;
  if (accessToken && charId) {
    try {
      const corpId = fetchCorporationId(charId);
      const assets = fetchCorporationAssets(corpId, accessToken);
      for (const a of assets) {
        corpStockByType[a.type_id] = (corpStockByType[a.type_id] || 0) + (a.quantity || 0);
        if (a.location_id === CJ6MT_STRUCTURE) {
          saleStockByType[a.type_id] = (saleStockByType[a.type_id] || 0) + (a.quantity || 0);
        }
      }
    } catch (e) {
      corpError = e.message;
      Logger.log("Corp assets skipped: " + corpError);
    }
  }

  const HUBS = [
    { label: "Jita",   region: 10000002, station: 60003760, structure: false },
    { label: "Amarr",  region: 10000043, station: 60008494, structure: false },
    { label: "C-J6MT", structure: true }
  ];

  // 3. Per item: 6 hub prices + char inventory + corp inventory go to F:M.
  //    Sale Stock (column O) is computed only when column N type == "material".
  const priceRows = [];
  const saleRows = [];
  for (const sku of skus) {
    const tid = typeIds[skuToQuery[sku].toLowerCase()];
    if (!tid) { priceRows.push(["", "", "", "", "", "", "", ""]); saleRows.push([""]); continue; }

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
    row.push(charStockByType[tid] || 0);
    row.push(corpStockByType[tid] || 0);
    priceRows.push(row);

    const isMaterial = typeBySku[sku] === "material" || typeBySku[sku] === "materials";
    saleRows.push([isMaterial ? (saleStockByType[tid] || 0) : ""]);
  }

  // Write headers F1:M1 (skip N — user owns it) and O1, then data F2:M and O2:O.
  const mainHeaders = ["Jita Buy", "Jita Sell", "Amarr Buy", "Amarr Sell", "C-J6MT Buy", "C-J6MT Sell", "Char Stock", "Corp Stock"];
  src.getRange(1, 6, 1, mainHeaders.length).setValues([mainHeaders]).setFontWeight("bold");
  src.getRange(1, 15).setValue("Sale Stock").setFontWeight("bold");
  src.getRange(2, 6, priceRows.length, mainHeaders.length).setValues(priceRows);
  src.getRange(2, 15, saleRows.length, 1).setValues(saleRows);
  if (cjError)     src.getRange(1, 10).setNote("C-J6MT skipped: " + cjError);
  if (assetsError) src.getRange(1, 12).setNote("Char Stock skipped: " + assetsError);
  if (corpError)   src.getRange(1, 13).setNote("Corp Stock skipped: " + corpError);
}

// ESI fetch with automatic 420 (rate limit) backoff and error-budget awareness.
// On 420 it waits for X-Esi-Error-Limit-Reset seconds (capped) and retries once.
// If less than 10 errors remain in the budget, it pauses briefly to let it recover.
function esiFetch(url, options) {
  options = options || { muteHttpExceptions: true };
  if (!options.muteHttpExceptions) options.muteHttpExceptions = true;

  for (let attempt = 0; attempt < 2; attempt++) {
    const resp = UrlFetchApp.fetch(url, options);
    const code = resp.getResponseCode();
    const hdrs = resp.getHeaders();
    const remain = parseInt(hdrs["x-esi-error-limit-remain"] || hdrs["X-Esi-Error-Limit-Remain"] || "100", 10);

    if (code === 420) {
      const reset = parseInt(hdrs["x-esi-error-limit-reset"] || hdrs["X-Esi-Error-Limit-Reset"] || "30", 10);
      const wait = Math.min(Math.max(reset, 5), 65) * 1000;
      Logger.log(`ESI 420 on ${url} — sleeping ${wait/1000}s before retry`);
      Utilities.sleep(wait);
      continue;
    }
    // Be polite when the error budget is nearly drained
    if (remain < 10) Utilities.sleep(2000);
    return resp;
  }
  // Final attempt — return whatever comes back (caller decides)
  return UrlFetchApp.fetch(url, options);
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

function fetchCharacterAssets(characterId, accessToken) {
  let all = [];
  let page = 1;
  while (true) {
    const url = `${ESI_BASE}/characters/${characterId}/assets/?page=${page}`;
    const resp = esiFetch(url, {
      headers: { Authorization: "Bearer " + accessToken },
      muteHttpExceptions: true
    });
    if (resp.getResponseCode() !== 200) {
      throw new Error(`characters/${characterId}/assets HTTP ${resp.getResponseCode()}: ${resp.getContentText()}`);
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
// One-time setup for C-J6MT + character/corp inventory access:
// 1) Go to https://developers.eveonline.com/applications and create an application.
//      Connection Type: Authentication & API Access
//      Permissions:     esi-markets.structure_markets.v1
//                       esi-assets.read_assets.v1
//                       esi-assets.read_corporation_assets.v1
//      Callback URL:    https://localhost/callback   (or any URL you control)
//    Corp Stock additionally requires that the authed character has the
//    Director role in the corporation (or the corp role that ESI maps to
//    "Director" for assets — Accountant/Junior Accountant alone won't do).
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
    `&scope=${encodeURIComponent("esi-markets.structure_markets.v1 esi-assets.read_assets.v1 esi-assets.read_corporation_assets.v1")}` +
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

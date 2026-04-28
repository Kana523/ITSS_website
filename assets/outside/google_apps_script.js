const STOCK_SHEET_NAME = "Stock";
const ORDERS_SHEET_NAME = "WebOrders";

function doGet() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(STOCK_SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ error: 'Missing "Stock" sheet.' });
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({});
  }

  const rows = sheet.getRange(2, 1, lastRow - 1, 4).getValues();
  const payload = {};

  for (const row of rows) {
    const sku = String(row[0] || "").trim().toLowerCase();
    if (!sku) continue;

    payload[sku] = {
      stock: toInt(row[1]),
      price: toNumber(row[2]),
      next_stock: toText(row[3])
    };
  }

  return jsonResponse(payload);
}

// Frontend posts as text/plain (to avoid the CORS preflight Apps Script can't answer)
// with a JSON body: { action: "order", orderId, turnstileToken, items: [{ sku, name, category, qty, price, extras: [{ name, price, qty }] }] }
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

  const orderId = String(body.orderId || "").trim();
  if (!/^[A-Z0-9]{20}$/.test(orderId)) {
    return jsonResponse({ ok: false, error: "Invalid Order ID." });
  }

  const items = Array.isArray(body.items) ? body.items : [];
  if (items.length === 0) {
    return jsonResponse({ ok: false, error: "No items in order." });
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(ORDERS_SHEET_NAME);
  if (!sheet) {
    return jsonResponse({ ok: false, error: 'Missing "WebOrders" sheet.' });
  }

  const tz = Session.getScriptTimeZone();
  const timestamp = Utilities.formatDate(new Date(), tz, "yyyy-MM-dd HH:mm:ss");

  const orderTotal = items.reduce((sum, item) => {
    const itemPrice = toNumber(item.price) || 0;
    const itemQty = toInt(item.qty);
    let line = itemPrice * itemQty;
    (Array.isArray(item.extras) ? item.extras : []).forEach((ex) => {
      const exPrice = toNumber(ex.price);
      if (exPrice !== null) line += exPrice * toInt(ex.qty);
    });
    return sum + line;
  }, 0);

  const rows = [];
  items.forEach((item) => {
    const sku = String(item.sku || "").trim();
    const name = String(item.name || "").trim();
    const category = String(item.category || "").trim();
    const qty = toInt(item.qty);
    const unitPrice = toNumber(item.price) || 0;
    const lineTotal = unitPrice * qty;

    rows.push([
      orderId, timestamp, sku, name, category, qty, unitPrice, lineTotal, orderTotal, "item"
    ]);

    (Array.isArray(item.extras) ? item.extras : []).forEach((ex) => {
      const exQty = toInt(ex.qty);
      const exPrice = toNumber(ex.price) || 0;
      rows.push([
        orderId, timestamp, sku, String(ex.name || "").trim(), category, exQty, exPrice, exPrice * exQty, orderTotal, "extra"
      ]);
    });
  });

  if (rows.length === 0) {
    return jsonResponse({ ok: false, error: "No valid rows to write." });
  }

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);

  return jsonResponse({ ok: true, orderId, total: orderTotal, rowsWritten: rows.length });
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

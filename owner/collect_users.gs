/**
 * Naukri Job Automation: user list.
 *
 * Paste this into the Apps Script editor of YOUR Google Sheet (Extensions > Apps Script) and
 * deploy it as a web app. Each person who continues past the tool's first welcome step is
 * added as a row: when they first and last registered, name, email, install ID, app version.
 * Full steps: owner/SETUP.md
 */

const SHEET_NAME = "Users";
const HEADERS = ["First seen", "Last seen", "Name", "Email", "Install ID", "App version"];
const INSTALL_ID_COLUMN = 5;
const MAX_LENGTH = 200;

function doPost(e) {
  let details;
  try {
    details = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply({ ok: false, error: "not JSON" });
  }

  const name = clean(details.name);
  const email = clean(details.email);
  const installId = clean(details.install_id);
  const version = clean(details.app_version);
  if (!name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !/^[0-9a-f]{32}$/.test(installId)) {
    return reply({ ok: false, error: "missing or invalid details" });
  }

  // One request at a time, so two people registering together cannot overwrite each other.
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return reply({ ok: false, error: "busy, try again" });
  }
  try {
    const sheet = usersSheet();
    const now = new Date();
    const row = findInstall(sheet, installId);
    if (row) {
      // Same copy of the tool registering again: update it instead of adding a second row.
      sheet.getRange(row, 2, 1, 3).setValues([[now, asText(name), asText(email)]]);
      sheet.getRange(row, 6).setValue(asText(version));
    } else {
      sheet.appendRow([now, now, asText(name), asText(email), installId, asText(version)]);
    }
  } finally {
    lock.releaseLock();
  }
  return reply({ ok: true });
}

function usersSheet() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = book.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = book.insertSheet(SHEET_NAME);
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function findInstall(sheet, installId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return 0;
  const ids = sheet.getRange(2, INSTALL_ID_COLUMN, lastRow - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (ids[i][0] === installId) return i + 2;
  }
  return 0;
}

function clean(value) {
  return String(value == null ? "" : value).trim().slice(0, MAX_LENGTH);
}

// Anyone can send anything to this link. A value starting with = + - or @ would otherwise be
// run by Sheets as a formula, so a leading apostrophe forces it to stay plain text.
function asText(value) {
  return /^[=+\-@\t\r]/.test(value) ? "'" + value : value;
}

function reply(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

/**
 * Naukri Job Automation: your applications, in your own Google Sheet.
 *
 * Paste this into the Apps Script editor of YOUR Sheet (Extensions > Apps Script), deploy it as
 * a web app, and paste the web app link into the tool's Settings page. The tool then sends each
 * application here. One row per Naukri job: a job sent again updates its row, it is never added
 * twice. The full steps are on the tool's Settings page and in the README.
 */

const TAB = "Applications";
const COLUMNS = [
  ["applied_on", "Applied On"],
  ["company", "Company"],
  ["title", "Job Title"],
  ["location", "Location"],
  ["experience", "Experience"],
  ["salary", "Salary"],
  ["skills", "Key Skills"],
  ["match_score", "Match Score"],
  ["status", "Status"],
  ["apply_link", "Apply Link"],
  ["naukri_link", "Naukri Link"],
  ["cv_used", "CV Used"],
  ["role", "Role"],
  ["notes", "Notes"],
  ["updated_on", "Updated On"],
  ["job_id", "Naukri Job ID"],
];
const JOB_ID_COLUMN = COLUMNS.length; // the last column
const MAX_ROWS = 200;
const MAX_LENGTH = 1000;

function doPost(e) {
  let body;
  try {
    body = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply({ ok: false, error: "not JSON" });
  }
  if (!Array.isArray(body.rows)) {
    return reply({ ok: false, error: "no rows" });
  }
  const rows = body.rows.slice(0, MAX_ROWS);

  // One request at a time, so two sends cannot write over each other.
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(20000);
  } catch (err) {
    return reply({ ok: false, error: "busy, try again" });
  }
  try {
    const sheet = applicationsTab();
    const rowOfJob = jobRows(sheet);
    let saved = 0;
    rows.forEach(function (row) {
      const jobId = clean(row.job_id);
      if (!jobId) return;
      const values = COLUMNS.map(function (column) {
        // The job ID always goes in as text (leading apostrophe), so an ID starting with 0 keeps it.
        return column[0] === "job_id" ? "'" + jobId : asText(clean(row[column[0]]));
      });
      if (rowOfJob[jobId]) {
        sheet.getRange(rowOfJob[jobId], 1, 1, values.length).setValues([values]);
      } else {
        sheet.appendRow(values);
        rowOfJob[jobId] = sheet.getLastRow();
      }
      saved++;
    });
    return reply({ ok: true, saved: saved });
  } finally {
    lock.releaseLock();
  }
}

function applicationsTab() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = book.getSheetByName(TAB);
  if (!sheet) {
    sheet = book.insertSheet(TAB);
    sheet.appendRow(COLUMNS.map(function (column) { return column[1]; }));
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, COLUMNS.length).setFontWeight("bold");
    // Job IDs can start with 0. As plain text they keep it; as numbers they would lose it.
    sheet.getRange(1, JOB_ID_COLUMN, sheet.getMaxRows(), 1).setNumberFormat("@");
  }
  return sheet;
}

// Naukri job ID -> row number, for every row already on the tab.
function jobRows(sheet) {
  const found = {};
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return found;
  const ids = sheet.getRange(2, JOB_ID_COLUMN, lastRow - 1, 1).getDisplayValues();
  for (let i = 0; i < ids.length; i++) {
    if (ids[i][0]) found[ids[i][0]] = i + 2;
  }
  return found;
}

function clean(value) {
  return String(value == null ? "" : value).trim().slice(0, MAX_LENGTH);
}

// Job titles and notes come from the web. A value starting with = + - or @ would otherwise be
// run by Sheets as a formula, so a leading apostrophe forces it to stay plain text.
function asText(value) {
  return /^[=+\-@\t\r]/.test(value) ? "'" + value : value;
}

function reply(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

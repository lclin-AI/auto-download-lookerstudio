#!/usr/bin/env python3
"""
export_and_upload.py

Daily automation:
  1. Query the BigQuery table/view that backs the Looker Studio
     "Cancellation Details" table on the Express - Wet Market Sales Report.
  2. Write the result to a CSV using the filename pattern the downstream
     report tool expects: <FILENAME_PREFIX><MMDD> with no file extension.
  3. Upload it to the target Drive folder as a Google Sheet.

Auth: a single Google Cloud SERVICE ACCOUNT is used for both BigQuery and
Drive. Nothing sensitive is stored in this repo. All configuration comes from
environment variables (populated from GitHub Actions Secrets). See README.md.

This script is READ-ONLY against the data source. It only creates/uploads a
Sheet; it never modifies the source data.
"""

import csv
import io
import os
import sys
import datetime as _dt

from google.oauth2 import service_account
from google.cloud import bigquery
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


# ---- Configuration (from environment / GitHub Secrets) ---------------------

# Path to the service-account JSON key file. In CI this is written from the
# GCP_SA_KEY secret before this script runs (see the workflow).
SA_KEY_PATH = os.environ.get("GCP_SA_KEY_PATH", "sa_key.json")

# BigQuery source that feeds the "Cancellation Details" table.
# Provide EITHER a fully-qualified table  (project.dataset.table)
# OR a full custom SQL query via BQ_QUERY. BQ_QUERY wins if both are set.
BQ_PROJECT = os.environ.get("BQ_PROJECT", "")          # billing/query project
BQ_TABLE = os.environ.get("BQ_TABLE", "")              # project.dataset.table
BQ_QUERY = os.environ.get("BQ_QUERY", "")              # optional custom SQL

# Google Drive destination folder (the "Cancellation Rate Raw" folder).
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

# Filename prefix expected by the report tool. It globs
# "Report_Cancellation Monitoring_*.csv" and picks the most recent.
FILENAME_PREFIX = os.environ.get(
    "FILENAME_PREFIX", "Express - Wet Market Sales Report_Cancellation Monitoring_表格_"
)

# The 24 columns the report tool reads, in order. If BQ_QUERY is not supplied
# the script SELECTs these columns from BQ_TABLE. Adjust in one place only.
COLUMNS = [
    "order_date",
    "delivery_date",
    "order_number",
    "order_entry_id",
    "order_entry_id_A",
    "order_entry_id_B",
    "carline_code",
    "shelf_name",
    "combined_order_status",
    "Wet_Market",
    "Store_Name",
    "sku_id",
    "sku_name_chi",
    "express_main_cat_name_zh",
    "sub_cat1_name_zh",
    "sku_cancel_reason",
    "sku_cs_refund_reason",
    "REFUND_REPORT_CANCEL_reason",
    "quantity",
    "dispatched_quantity",
    "refund_quantity",
    "refund_amount",
    "refund_mall_dollar",
]

SCOPES = [
    "https://www.googleapis.com/auth/bigquery.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def _fail(msg: str) -> "None":
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(1)


def _credentials():
    if not os.path.exists(SA_KEY_PATH):
        _fail(
            "Service account key not found at "
            + SA_KEY_PATH
            + ". In CI it is written from the GCP_SA_KEY secret."
        )
    return service_account.Credentials.from_service_account_file(
        SA_KEY_PATH, scopes=SCOPES
    )


def _build_query() -> str:
    if BQ_QUERY.strip():
        return BQ_QUERY
    if not BQ_TABLE.strip():
        _fail("Set either BQ_QUERY or BQ_TABLE (project.dataset.table).")
    cols = ", ".join("`" + c + "`" for c in COLUMNS)
    return "SELECT " + cols + " FROM " + "`" + BQ_TABLE + "`"


def fetch_rows(creds):
    """Run the read-only query and return (header, iterator-of-rows)."""
    project = BQ_PROJECT or getattr(creds, "project_id", None)
    if not project:
        _fail("Set BQ_PROJECT (the project used to run the query).")
    client = bigquery.Client(project=project, credentials=creds)
    query = _build_query()
    print("Running BigQuery job in project " + str(project) + " ...")
    job = client.query(query)
    result = job.result()  # waits for completion
    header = [f.name for f in result.schema]
    return header, result


def write_csv(header, rows) -> "tuple":
    """Write rows to an in-memory UTF-8-SIG CSV. Returns (filename, bytes)."""
    stamp = _dt.datetime.now().strftime("%m%d")
    filename = FILENAME_PREFIX + stamp
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    n = 0
    for row in rows:
        writer.writerow(list(row.values()))
        n += 1
    print("Wrote " + str(n) + " data rows to " + filename)
    # utf-8-sig so the report tool (which reads with a BOM) parses cleanly.
    data = buf.getvalue().encode("utf-8-sig")
    return filename, data


def upload_to_drive(creds, filename: str, data: bytes) -> str:
    if not DRIVE_FOLDER_ID.strip():
        _fail("Set DRIVE_FOLDER_ID (the destination Drive folder).")
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    media = MediaIoBaseUpload(
        io.BytesIO(data), mimetype="text/csv", resumable=True
    )
    metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID], "mimeType": "application/vnd.google-apps.spreadsheet"}
    created = (
        service.files()
        .create(body=metadata, media_body=media, fields="id,name", supportsAllDrives=True)
        .execute()
    )
    print("Uploaded to Drive: " + created.get("name") + " (id " + created.get("id") + ")")
    return created.get("id")


def main() -> "None":
    creds = _credentials()
    header, rows = fetch_rows(creds)
    filename, data = write_csv(header, rows)
    upload_to_drive(creds, filename, data)
    print("Done.")


if __name__ == "__main__":
    main()

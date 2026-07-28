# auto-download-lookerstudio

Daily automation that exports the **Cancellation Details** dataset (the data
behind the "Cancellation Monitoring" table on the *Express - Wet Market Sales
Report* in Looker Studio) and uploads it as a CSV to a Google Drive folder.
The CSV is then picked up by the downstream 貨品取消率分析 report tool.

The job runs unattended via GitHub Actions on a daily schedule, using a Google
Cloud **service account** for both BigQuery (read) and Google Drive (upload).
Nothing sensitive is stored in this repository.

## How it works

1. GitHub Actions runs once a day (see .github/workflows/daily-export.yml).
2. export_and_upload.py runs a READ-ONLY BigQuery query for the Cancellation
   Details columns.
3. It writes a UTF-8-SIG CSV named
   `Report_Cancellation Monitoring_<YYYYMMDD>.csv` (the pattern the report
   tool globs for and loads the most recent of).
4. It uploads that CSV to the target Drive folder via the Drive API.

## What YOU need to set up (once)

These steps involve credentials and account access, so you must do them
yourself. The code only reads them from GitHub Secrets/Variables.

### 1. Create a Google Cloud service account

- In Google Cloud Console, create a service account in the project that owns
  the BigQuery dataset behind the report.
- Grant it **BigQuery Data Viewer** + **BigQuery Job User** on that project/dataset.
- Create a **JSON key** for it and download the key file.

### 2. Give the service account access to the data and the Drive folder

- BigQuery: make sure the service account can read the table/view that feeds
  the Cancellation Details table.
- Drive: open the destination folder in Google Drive and **Share** it with the
  service account's email (the `client_email` in the JSON key), with at least
  *Editor* access, so it can upload files.
  (Sharing must be done by you — it changes access control.)

### 3. Find the BigQuery source

You need the fully-qualified source that feeds the Cancellation Details table.
In Looker Studio: Resource → Manage added data sources → open the data source
used by that table → note the project / dataset / table (or the custom SQL).
Provide either the table id or a full SQL query (see secrets below).

### 4. Add GitHub Secrets and Variables

Repo → **Settings → Secrets and variables → Actions**.

Secrets (Settings → Secrets):

| Secret | Value |
| --- | --- |
| `GCP_SA_KEY` | The entire contents of the service-account JSON key file |
| `BQ_PROJECT` | GCP project id used to run the query |
| `BQ_TABLE` | `project.dataset.table` that feeds Cancellation Details (omit if using BQ_QUERY) |
| `BQ_QUERY` | (optional) full SQL query; overrides BQ_TABLE if set |
| `DRIVE_FOLDER_ID` | The destination Drive folder id (from the folder URL) |

Variables (Settings → Variables), optional:

| Variable | Default |
| --- | --- |
| `FILENAME_PREFIX` | `Report_Cancellation Monitoring_` |

### 5. (Optional) adjust the schedule

Edit the `cron` in .github/workflows/daily-export.yml. It is in **UTC**.
The default `30 22 * * *` is 22:30 UTC = 06:30 HKT (next day).

## Run it manually

Actions tab → **Daily Cancellation Details export** → *Run workflow*.
Use this to test after adding the secrets.

## The columns

The script selects these columns (edit the `COLUMNS` list in
export_and_upload.py to change them). `Store_Name` holds the 街市 value and
`Wet_Market` holds the 店舖 value in this dataset.

```
order_date, delivery_date, order_number, order_entry_id, order_entry_id_A,
order_entry_id_B, carline_code, shelf_name, combined_order_status, Wet_Market,
Store_Name, sku_id, sku_name_chi, express_main_cat_name_zh, sub_cat1_name_zh,
sku_cancel_reason, sku_cs_refund_reason, REFUND_REPORT_CANCEL_reason, quantity,
dispatched_quantity, refund_quantity, refund_amount, refund_mall_dollar
```

## Security notes

- Read-only against BigQuery; the job only creates/uploads a CSV.
- The service-account key exists only on the runner during the job and is
  removed afterwards; it is git-ignored and never committed.
- This repo is public: never commit the JSON key, .env, or generated CSVs.

# Document Download Feature

## Overview

The Miami-Dade Court Docket Monitor now automatically downloads court documents that are available through "View Docket Image" links in the **Dockets** and **Extra Documents** tabs.

## How It Works

When the monitor detects new dockets or extra documents with downloadable files:

1. **Detection**: Checks for "View Docket Image" icons/links in the first column of docket tables
2. **Download**: Automatically clicks the link and saves the PDF document
3. **Naming**: Files are named as `{case_number}-{docket_description}.pdf`
   - Example: `F-25-024957-REPORT-RE-NEBBIA-HEARING.pdf`
4. **Tracking**: Remembers which documents have been downloaded to avoid duplicates
5. **Storage**: All documents are saved to the `court_documents/` directory (configurable)

## Configuration

### Enable/Disable Downloads

**In config file (ricardo.json, sina.json, etc.):**
```json
{
  "defendant_first_name": "Ricardo",
  "defendant_last_name": "Deuker",
  "defendant_sex": "Male",
  "poll_interval": 600,
  "download_documents": true,
  "documents_dir": "court_documents"
}
```

**Via command line:**
```bash
# Downloads enabled by default
python3 deuker-monitor.py -c ricardo.json --once

# Disable downloads
python3 deuker-monitor.py -c ricardo.json --once --no-downloads

# Custom download directory
python3 deuker-monitor.py -c ricardo.json --once --documents-dir /path/to/docs
```

## File Naming

Documents are named using this pattern:
```
{case_number}-{sanitized_docket_description}.pdf
```

**Examples:**
- `F-25-024957-REPORT-RE-NEBBIA-HEARING.pdf`
- `F-25-024957-CURRENT-BOND-STATUS.pdf`
- `F-24-012345-ARRAIGNMENT-ORDER.pdf`

**Duplicate Handling:**
If a file with the same name already exists, a counter is added:
- `F-25-024957-REPORT-RE-NEBBIA-HEARING-1.pdf`
- `F-25-024957-REPORT-RE-NEBBIA-HEARING-2.pdf`

## Document Sources

The monitor checks two locations for documents:

### 1. Dockets Tab
Standard docket entries with "View Docket Image" icons in the table.

### 2. Extra Documents Tab
Additional court documents that may be available in a separate "EXTRA DOCUMENTS" tab on the case page.

## Download Tracking

Downloaded documents are tracked in two ways:

1. **In-Memory**: During each run, the monitor tracks which documents have been downloaded
2. **Persistent State**: Document IDs are saved to the state file (e.g., `docket_monitor_deuker_ricardo.json`)

This ensures:
- ✅ Documents are only downloaded once
- ✅ No duplicate downloads even across multiple runs
- ✅ Efficient use of bandwidth and storage

## State File Updates

The state file now includes a `seen_documents` array:

```json
{
  "seen_charges": [...],
  "seen_dockets": [...],
  "seen_documents": [
    "F-25-024957_7_REPORT RE: NEBBIA HEARING",
    "F-25-024957_6_CURRENT BOND STATUS",
    ...
  ],
  "case_info": {...}
}
```

## Directory Structure

```
deuker-monitor/
├── court_documents/           # Downloaded PDFs (default location)
│   ├── F-25-024957-REPORT-RE-NEBBIA-HEARING.pdf
│   ├── F-25-024957-CURRENT-BOND-STATUS.pdf
│   └── ...
├── ricardo.json               # Config file
├── docket_monitor_deuker_ricardo.json  # State file with document tracking
└── deuker-monitor.py          # Main script
```

## Command-Line Options

```
--no-downloads          Disable automatic document downloads
--documents-dir DIR     Directory to store downloaded documents (default: court_documents)
```

## Examples

### Download documents for Ricardo
```bash
python3 deuker-monitor.py -c ricardo.json --once
```

### Check cases without downloading documents
```bash
python3 deuker-monitor.py -c ricardo.json --once --no-downloads
```

### Download to custom directory
```bash
python3 deuker-monitor.py -c ricardo.json --once --documents-dir ~/Documents/court-files
```

### Monitor multiple defendants with downloads
```bash
python3 deuker-monitor.py -c ricardo.json -c sina.json --once
```
Each defendant's documents will be saved to the same directory (or their individual configured directories).

## Troubleshooting

### Documents not downloading

1. **Check logs**: Look for messages like "📥 Downloaded: filename.pdf"
2. **Verify document exists**: Not all dockets have downloadable documents
3. **Check permissions**: Ensure write access to the documents directory
4. **Browser issues**: The download uses Playwright's download handler - check for browser errors

### Files with generic names

If a docket description is empty or contains only special characters, the file will be named:
```
F-25-024957-extra-doc-1.pdf
```

### Download timeout

Downloads have a 30-second timeout. If a document is very large or the connection is slow, it may timeout. Check the logs for timeout errors.

## Technical Details

### Document Detection
The script checks the first column of docket tables for:
- `<img>` tags (view icons)
- `<a>` tags (download links)

### Download Mechanism
Uses Playwright's `page.expect_download()` context manager to:
1. Set up download listener
2. Click the download link
3. Wait for download to complete
4. Save to specified location

### Deduplication
Documents are identified by: `{case_number}_{din}_{docket_description}`

This unique ID is stored in `seen_documents` to prevent re-downloading.

## Performance

- Downloads are processed sequentially with 0.5s delay between each
- Only new documents (not in `seen_documents`) are downloaded
- Downloads happen after charge/docket extraction is complete
- Does not significantly impact overall monitoring performance

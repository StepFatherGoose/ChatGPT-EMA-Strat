# SPY First-30-Minute High-of-Day Analysis

This repository contains a Python script to analyze 1-minute SPY intraday data and test whether a strong move in the first 30 minutes is associated with the high of day (HOD) being established before 10:00 AM ET.

## Script

- `spy_first30_hod_analysis.py`

## What it computes per day

Using regular trading hours only (9:30 AM to 4:00 PM ET):

- `session_open`: open price at 9:30
- `first30_high`: highest high between 9:30 and 9:59 (first 30 minutes)
- `day_high`: highest high between 9:30 and 16:00
- `day_high_time`: first timestamp where `day_high` occurs

For each threshold in default:

`[0.005, 0.0075, 0.01, 0.0125, 0.015]`

it reports:

- qualifying days where `(first30_high - session_open) / session_open >= threshold`
- days where `day_high_time < 10:00 AM ET`
- probability = successes / qualifying days

## Usage

```bash
python spy_first30_hod_analysis.py --input /path/to/spy_1min.csv --output-dir analysis_output
```

If your timestamps are naive and not ET, specify the timezone:

```bash
python spy_first30_hod_analysis.py --input /path/to/spy_1min.csv --input-tz UTC
```

## Input requirements

CSV with at least:

- timestamp column: `timestamp` (or `datetime`, `date`, `time`)
- `open`
- `high`

## Output files

- `analysis_output/threshold_summary.csv`
- `analysis_output/daily_metrics.csv`
- `analysis_output/threshold_probability.png`

## Data quality handling

The script safely handles:

- missing values (drops rows with missing timestamp/open/high)
- duplicate minute bars (keeps first bar per timestamp)
- timezone normalization to America/New_York
- filtering to regular market hours only
- skipping invalid sessions missing a 9:30 open bar

# Payroll runbook (lock-in)

Use this every pay period so Fixed Ops Hub stays faster than the old spreadsheet workflow.

## Before you start

1. Wait for Streamlit Cloud to finish redeploying after any `main` push.
2. Confirm sidebar shows **Database ONLINE**.
3. Open **Payroll** and set the pay-period dates (or let the flag sheet fill them).

## Technicians (fast path)

1. Upload **TECH FLAG SHEETS.pdf** once (CDK *Technician Timecard for Payroll*).
2. Upload **Ignite upsell** `.xlsx` once.
3. Enter only **training hrs / SPIFF / notes**.
4. Export PDF → check **Complete & Save to Reports**.

**Locked-in behavior**

- Newer jammed CDK lines (glued Tech#/date, missing Actual, negative credits) still parse.
- Flag PDF is parsed **once per upload**, then cached for the session.
- Draft edits save **locally**; cloud backup of the big PDF happens on **Complete**.
- NaN values from Excel never break Supabase backup.

If hours look wrong: clear the uploader and re-upload the PDF once (don’t keep re-parsing by refreshing).

## Receptionists

1. Upload **CASHIERS*.xlsx** once.
2. Confirm Megan Schneider / Brandy / others show appointment counts.
3. Type over **Appointments set** when the report is wrong — RecallPulse recalculates.
4. Complete & Save.

**Locked-in roster codes**

| Person | Taker code |
|--------|------------|
| Megan Schneider | `22SCHNEIDERM` |
| Brandy Sistrunk | `22SISTRUNKB` |
| Misty Carver | `22CARVERM` |
| Jennifer Cleary | `22CLEARYJ` |
| Kayla Hoffman | `22HOFFMANK` |
| Samantha Rodriguez | `22RODRIGUEZS` |
| Serenity Skinner | `22SKINNERS` |

Unmatched codes after upload show a yellow warning — add them under **Manage team roster** with that taker code, then re-upload.

## Advisors

1. Upload the advisor **PAYROLL** `.xlsx`.
2. Adjust SPIFF / notes as needed.
3. Complete & Save.

## Do not “fix” without tests

These regressions are guarded by `tests/test_payroll_lockin.py` (plus flag/JSON/RecallPulse tests):

```bash
python3 -m unittest tests.test_payroll_lockin tests.test_recall_pulse_bonus tests.test_json_safe tests.test_flag_pdf_parser -v
```

If a future CDK export format breaks parsing, **extend the parser + add a test** — don’t remove the jammed-line / negative-hour support that July 2026 needed.

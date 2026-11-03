# Data · Resonant Gaps (Issue 02)

No raw data is committed. Each country page carries only the aggregate figures it needs, built into its `index.html`.

## Sierra Leone (demo)

- **Publisher:** DHIS2 / HISP Centre, University of Oslo. Public demo instance `play.im.dhis2.org/dev` (DHIS2 2.44-SNAPSHOT), the Sierra Leone demo database.
- **What it is:** a training and testing database modelled on Sierra Leone's health system. Organisation units follow the real country; much of the data is synthetic or regenerated each year. It is not official Sierra Leone health data.
- **Accessed:** 3 November 2026, through the public DHIS2 Web API.
- **Scope:** January–December 2025, monthly. 1,166 facilities, 13 districts.
  - Data value sets for: Child Health, Reproductive Health, Morbidity, PMTCT monthly summary, ART monthly summary, Mortality < 5 years
  - Form completeness registrations for the same forms
  - Population data set (Total population < 1 year and others, 2024–2026)
  - Coverage indicator definitions (e.g. BCG Coverage < 1y)
- **Personal data:** none. Only aggregate counts per facility and month.
- **Terms:** DHIS2 software is BSD-3 licensed. The demo database is published openly by the DHIS2 project for training and testing; credit *DHIS2 Sierra Leone demo database, HISP Centre, University of Oslo*.

## How cells are read

| Code | Meaning |
|---|---|
| value | a number was stored |
| blank | the monthly form was sent, this field is empty (zero, or not filled: the export cannot tell) |
| no report | the monthly form was not sent |
| zero | an explicit zero was stored (none found: no followed field keeps zeros) |

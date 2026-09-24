# Fundamental source pilot and go/no-go record

The point-in-time track is admitted in bounded pilots. A pilot manifest must
be saved alongside the coverage report before a return calculation is run.
`cheshire_cat.fundamental_coverage.build_pilot_manifest` produces this record
and quarantines evidence with unknown publication timing or missing source
identity, URL, or checksum.
The following is the required record shape:

```json
{
  "version": "fundamental-pilot-v1",
  "issuers": ["ACME"],
  "periods": ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"],
  "sources": ["SEC-XBRL", "AMF"],
  "publication_policy": "SEC filing date-only; issuer deposit date when archived",
  "reconciliation": "required before scale-up",
  "unknown_or_quarantined_records": 0,
  "decision": "go|no-go|pilot-only"
}
```

SEC company-facts rows are linked by accession and filing date; archived SEC
or official AMF artifacts retain their source URL and SHA-256 checksum. SEC
quarter, YTD, annual, and amended observations remain distinct. Yahoo annual
statements are useful for latest overviews, but their publication timing is
unknown and they remain excluded from verified historical features.

The ingestion jobs are resumable and idempotent. `fundamental_ingestion_state`
records each source/symbol as `in_progress`, `complete`, `empty`,
`unavailable`, or `failed`, with row counts and the last error. The coverage
API exposes those states so not-yet-downloaded and unavailable records cannot
be mistaken for missing facts or zero-valued facts.

Scale-up is a go decision only when reconciliation covers reported values,
units, fiscal periods, amendments, and source artifacts for the selected pilot.
An unsupported issuer or date remains quarantined; this workflow never fills
it with a current provider snapshot or an invented publication date.

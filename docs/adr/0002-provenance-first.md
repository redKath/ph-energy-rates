# 2. Every rate points back to its source document

## Context

Agencies and utilities are each authoritative for their own figures. A dataset that copies numbers without a trail cannot be audited or corrected.

## Decision

Each rate references a source document with its URL, fetch time and SHA-256. The raw bytes are archived before parsing, so extraction can be re-run. A document with an already-stored hash is not processed again. The API and exports expose the provenance.

## Consequences

- Any value can be checked against its original.
- Pages that change on every fetch (a CSRF token in BENECO's page) create a new source document each run, though duplicate rates are skipped by value.
- Archive storage grows; it sits behind an interface so local disk can be swapped for object storage.

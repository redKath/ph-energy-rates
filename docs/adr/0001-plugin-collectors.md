# 1. One collector module per utility, discovered automatically

## Context

Each utility publishes in its own format and changes it without notice. About 142 utilities will need support.

## Decision

A collector is one module implementing `discover` and `extract`, exposing a `collector` instance. The registry imports every module in the package. The pipeline, storage and API know nothing about individual utilities.

## Consequences

- Adding a utility is one file plus fixtures and tests; breaking one source cannot break another.
- Utilities with the same pattern (listing page to PDFs) repeat code. Declarative source configs are the planned fix once there are enough similar sources.

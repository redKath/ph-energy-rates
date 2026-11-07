# 4. Explicit collector registry

## Context

Collectors were found by importing every module in the `collectors` package by name. Which collectors exist was not visible in the code, and each module had to build its own instance, so a collector could not receive dependencies such as an OCR engine from the caller.

## Decision

`collectors/registry.py` builds the collectors in a visible list and passes each its dependencies. Adding a utility adds one line there.

## Consequences

- A reader can see every supported utility, and every dependency of each, in one place.
- Tests construct collectors with fakes.
- Forgetting the registry line means the utility is silently not collectable; `tests/test_registry.py` checks the known utilities are present.

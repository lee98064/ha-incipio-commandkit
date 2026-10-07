# Changelog

## 0.1.1 — 2026-10-07

- Fix all three sensors showing `unknown` even when HomeKit has valid measurements: compare the characteristic status to `HapStatusCode.SUCCESS` rather than integer `0`.
- Test against real aiohomekit 4.0.1 status enums and accessory models, using sanitized CMNDKT-004 firmware 10219 metadata.
- Add regressions for successful readings, native cache updates, and error recovery; retain the existing polling and read-only boundary tests (14 tests total).
- Existing installations can overwrite the component files and restart Home Assistant Core; no integration removal or HomeKit re-pairing is needed.

## 0.1.0 — 2026-10-07

- Add voltage, current and power sensors for an already paired CMNDKT-004.
- Reuse Home Assistant's existing HomeKit Device connection and native polling lock.
- Resolve characteristics by UUID, with a selectable 5- or 10-second refresh interval.
- Include English and Traditional Chinese setup text, HACS metadata and installation instructions.
- Add 11 offline boundary tests. Live HAOS validation remains pending; unit mappings are inferred.

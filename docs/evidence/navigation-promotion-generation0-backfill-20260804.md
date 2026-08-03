# Navigation promotion generation-0 backfill — 2026-08-04

## Result

The currently traceable direct Runtime promotions were reconstructed through the
new standard layers without changing the operating N100 Decision DB.

- Operating snapshot cases: 88
- Human Gold cases: 63
- Rows marked `real_device`: 25
- Runtime-traceable promoted cases: 14
- Older `uxa_*` imported real-device cases without a current Runtime session: 11
- Runtime episodes exported: 7 (46 observed steps)
- Accepted/applied promotion groups recovered: 6
- App Knowledge packets: 3 (YouTube, Netflix, X)
- Generated procedures/macros: 0
- Staging cases after projection: 88
- SQLite `quick_check`: `ok`
- Foreign-key errors: 0
- Operating DB changed: no
- Activation attempted: no

## Generation identity

- Generation: `generation_92648fdee0389cc62a911ac4`
- Base Decision snapshot SHA-256:
  `368312622e5b747750ca1bf941ba6fff5855b92cd0b706aace1725831b1aa312`
- Interaction Episode artifact SHA-256:
  `b58da244e64acafa7c88dfcc71cb3bff96633a161e9b1ece61f14383484cb156`
- Sealed promotion artifact SHA-256:
  `212fb402c3d3b3dc28955606b4a7abce938228ca32540ed6fbbea1cb5f1e3ca5`
- Manifest SHA-256:
  `a49a5a61431dbfbaf6b448aed814a62f80ad2fbe0922ff51bc436d547f715874`
- Projected staging DB SHA-256:
  `368312622e5b747750ca1bf941ba6fff5855b92cd0b706aace1725831b1aa312`

The staging hash exactly equals the base snapshot because all 14 projected case
IDs were already present in the operating snapshot. This is the intended
provenance backfill result, not a new data expansion.

## Provenance boundary

The 14 recovered cases are:

- YouTube: 6 source steps across 2 Runtime sessions;
- Netflix: 2 source steps across 2 Runtime sessions;
- X: 6 source steps across 3 Runtime sessions, including the accepted recovery
  group.

The remaining 11 `real_device` rows use `uxa_*` source IDs from an older common
data import (Discord 2, YouTube 6, Samsung launcher 3). No matching session
exists in the current Runtime DB. They remain preserved in the base snapshot,
but were not fabricated into `interaction-episode.v1` or canonical App Knowledge.
They require the original common episode artifacts for full provenance recovery.

## Why activation was not performed

The Decision DB declares two validation apps but currently contains zero
verified decision cases from them; all 88 verified cases belong to collection
apps. Therefore a frozen validation-only performance regression cannot yet run.
Using collection cases would leak promotion data, and using locked holdout apps
would consume the final generalization set. The new tool correctly leaves the
operating DB unchanged until a real validation case DB exists.

## Local and N100 artifacts

Local generated artifacts are kept under the ignored directory:

`.artifacts/promotion-pipeline-v2-20260804/`

The N100 copy is deployed under:

`/home/kyle/exitguide/runtime/promotion-pipeline-v2-staging-20260804/`


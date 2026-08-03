# Navigation Promotion Pipeline v2

## Purpose

The promotion pipeline turns observed runtime actions into traceable, versioned
navigation knowledge. It does not train Solar or EXAONE, replay a Gold path, or
write an app-specific macro.

```text
Runtime DB (append-only observations)
  -> interaction-episode.v1 (normalized common experience)
  -> knowledge-promotion.v1 (candidate and source-consistency review)
  -> sealed App Knowledge generation (immutable JSON artifacts)
  -> staging Decision DB projection (no Runtime DB access)
  -> frozen validation-app regression
  -> atomic activation + rollback receipt
```

The operating Decision DB is only a search projection. The sealed App Knowledge
generation is the canonical promoted record.

## Boundaries

- `source_consistency_only` confirms that accepted evidence still matches its
  source episode. It is not a performance regression test.
- Activation requires a second replay using a frozen case DB containing only
  apps assigned to the `validation` split.
- `locked_holdout` apps cannot be used for promotion tuning or activation.
- Whole procedures are deliberately emitted as an empty list. A generation
  contains decisions and transitions, not executable app paths.
- The legacy direct `apply` route is disabled unless
  `--allow-legacy-direct-apply` is explicitly supplied.
- A transport or executor failure remains separate from a navigation failure.

## Commands

### 1. Export normalized episodes

```bash
python scripts/Promote-NavigationRuntimeExperiences.py export-episode \
  --runtime-db runtime.sqlite \
  --session SESSION_ID \
  --output interaction-episodes.v1.jsonl
```

Only candidate inventories already normalized in Runtime DB are exported.
Scores or candidates are never reconstructed by guessing.

### 2. Generate and source-check candidates

```bash
python scripts/Promote-NavigationRuntimeExperiences.py generate \
  --episodes interaction-episodes.v1.jsonl \
  --output promotion-candidates.v1.jsonl

python scripts/Promote-NavigationRuntimeExperiences.py accept \
  --episodes interaction-episodes.v1.jsonl \
  --input promotion-candidates.v1.jsonl \
  --output accepted-promotions.v1.jsonl
```

### 3. Seal an immutable generation

```bash
python scripts/Promote-NavigationRuntimeExperiences.py build-generation \
  --episodes interaction-episodes.v1.jsonl \
  --input accepted-promotions.v1.jsonl \
  --base-decision-db operating-snapshot.sqlite \
  --output-root navigation-generations
```

The generated directory is content-addressed, refuses overwrite, records SHA-256
for every artifact, and contains one canonical App Knowledge packet per app.

### 4. Project to staging

```bash
python scripts/Promote-NavigationRuntimeExperiences.py project \
  --generation-dir navigation-generations/GENERATION_ID \
  --output staging-decision.sqlite \
  --report projection-report.json
```

Projection reads only the sealed generation. `runtime_db_accessed=false` is
recorded in its report.

### 5. Run the fixed validation regression

```bash
python scripts/Promote-NavigationRuntimeExperiences.py regression \
  --generation-dir navigation-generations/GENERATION_ID \
  --projection-report projection-report.json \
  --baseline-db operating-snapshot.sqlite \
  --staging-db staging-decision.sqlite \
  --cases-db frozen-validation-cases.sqlite \
  --output regression-report.json
```

The gate rejects an empty case set, mixed splits, collection apps, and locked
holdout apps. It fails on any tracked accuracy or recovery regression and on any
dangerous automatic click.

### 6. Activate or roll back

```bash
python scripts/Promote-NavigationRuntimeExperiences.py activate \
  --generation-dir navigation-generations/GENERATION_ID \
  --projection-report projection-report.json \
  --regression-report regression-report.json \
  --staging-db staging-decision.sqlite \
  --operating-db navigation-decision.sqlite \
  --backup pre-activation.sqlite \
  --active-pointer active-generation.json \
  --receipt activation-receipt.json

python scripts/Promote-NavigationRuntimeExperiences.py rollback \
  --activation-receipt activation-receipt.json \
  --active-pointer active-generation.json \
  --receipt rollback-receipt.json
```

Activation verifies the generation, projection hash, validation-case identity,
staging DB hash, and passed regression report before atomic replacement.
Rollback refuses to proceed if either the active DB or backup changed after the
activation receipt was written.

## Tests

`apps/api/tests/navigation_promotion_pipeline_unit.py` covers:

- two Runtime sessions exported to valid `interaction-episode.v1`;
- source-consistent candidate acceptance;
- immutable generation and canonical App Knowledge validation;
- Runtime-independent staging projection;
- validation-only and locked-holdout guards;
- activation and exact rollback.


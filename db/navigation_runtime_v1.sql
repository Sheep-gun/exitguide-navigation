PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS navigation_runtime_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS navigation_dataset_split_manifest (
    manifest_version TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    app_package TEXT PRIMARY KEY,
    app_name TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('collection', 'validation', 'locked_holdout')),
    reason TEXT NOT NULL,
    existing_decision_cases INTEGER NOT NULL CHECK (existing_decision_cases >= 0),
    available_on_device INTEGER NOT NULL CHECK (available_on_device IN (0, 1)),
    priority_app INTEGER NOT NULL CHECK (priority_app IN (0, 1)),
    locked_at TEXT NOT NULL,
    CHECK (split <> 'locked_holdout' OR existing_decision_cases = 0)
);

CREATE INDEX IF NOT EXISTS idx_runtime_dataset_split
    ON navigation_dataset_split_manifest(split, app_package);

CREATE TABLE IF NOT EXISTS navigation_sessions (
    session_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    app_package TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT '',
    locale TEXT NOT NULL,
    goal_text_redacted TEXT NOT NULL,
    goal_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'stopped', 'reached', 'failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS navigation_decisions (
    decision_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES navigation_sessions(session_id),
    step_ordinal INTEGER NOT NULL CHECK (step_ordinal >= 0),
    screen_fingerprint TEXT NOT NULL,
    screen_payload_json TEXT NOT NULL CHECK (json_valid(screen_payload_json)),
    goal_id TEXT,
    plan_stage TEXT NOT NULL,
    plan_json TEXT NOT NULL CHECK (json_valid(plan_json)),
    action_name TEXT NOT NULL CHECK (action_name IN (
        'click', 'scroll', 'back', 'wait_and_observe', 'stop_for_user'
    )),
    candidate_id TEXT,
    scroll_direction TEXT CHECK (scroll_direction IS NULL OR scroll_direction IN ('up', 'down')),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    score_margin REAL NOT NULL CHECK (score_margin BETWEEN 0.0 AND 1.0),
    reflection_on_demand INTEGER NOT NULL CHECK (reflection_on_demand IN (0, 1)),
    planner_provider TEXT NOT NULL,
    planner_fallback_used INTEGER NOT NULL CHECK (planner_fallback_used IN (0, 1)),
    safety_status TEXT NOT NULL CHECK (safety_status IN ('allowed', 'replaced_with_safe_action')),
    safety_reason TEXT NOT NULL,
    destination_match_before REAL NOT NULL CHECK (destination_match_before BETWEEN 0.0 AND 1.0),
    evidence_case_ids_json TEXT NOT NULL CHECK (json_valid(evidence_case_ids_json)),
    candidate_values_json TEXT NOT NULL CHECK (json_valid(candidate_values_json)),
    created_at TEXT NOT NULL,
    UNIQUE(session_id, step_ordinal),
    CHECK (
        (action_name = 'click' AND candidate_id IS NOT NULL AND scroll_direction IS NULL)
        OR (action_name = 'scroll' AND candidate_id IS NULL AND scroll_direction IS NOT NULL)
        OR (action_name IN ('back', 'wait_and_observe', 'stop_for_user')
            AND candidate_id IS NULL AND scroll_direction IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS navigation_observations (
    observation_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE REFERENCES navigation_decisions(decision_id),
    connectivity_status TEXT NOT NULL CHECK (connectivity_status IN (
        'observed', 'device_disconnected', 'transport_error'
    )),
    next_screen_fingerprint TEXT,
    state_changed INTEGER CHECK (state_changed IS NULL OR state_changed IN (0, 1)),
    outcome_type TEXT NOT NULL CHECK (outcome_type IN (
        'navigated', 'destination_reached', 'no_change', 'wrong_destination',
        'external_app', 'login_required', 'popup', 'infinite_feed',
        'network_error', 'blocked', 'unknown'
    )),
    progress_label TEXT NOT NULL CHECK (progress_label IN (
        'reached', 'advanced', 'unchanged', 'regressed', 'unknown'
    )),
    destination_match_before REAL CHECK (destination_match_before IS NULL OR destination_match_before BETWEEN 0.0 AND 1.0),
    destination_match_after REAL CHECK (destination_match_after IS NULL OR destination_match_after BETWEEN 0.0 AND 1.0),
    failure_class TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    CHECK (
        connectivity_status = 'observed'
        OR (next_screen_fingerprint IS NULL AND state_changed IS NULL
            AND destination_match_after IS NULL AND progress_label = 'unknown')
    )
);

-- A lossless, normalized projection of every screen that participated in a
-- runtime decision.  `before` is captured by /decide and `after` by /observe.
-- This is the collection substrate used to export the shared
-- interaction-episode.v1 contract without reconstructing candidates later.
CREATE TABLE IF NOT EXISTS navigation_screen_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES navigation_decisions(decision_id),
    observation_id TEXT REFERENCES navigation_observations(observation_id),
    phase TEXT NOT NULL CHECK (phase IN ('before', 'after')),
    screen_fingerprint TEXT NOT NULL,
    window_title_redacted TEXT NOT NULL,
    activity_name_redacted TEXT NOT NULL,
    navigation_depth INTEGER CHECK (navigation_depth IS NULL OR navigation_depth >= 0),
    candidate_set_status TEXT NOT NULL DEFAULT 'complete'
        CHECK (candidate_set_status IN ('complete', 'partial', 'unavailable')),
    screen_payload_json TEXT NOT NULL CHECK (json_valid(screen_payload_json)),
    captured_at TEXT NOT NULL,
    UNIQUE(decision_id, phase),
    CHECK (
        (phase = 'before' AND observation_id IS NULL)
        OR (phase = 'after' AND observation_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS navigation_screen_candidates (
    snapshot_id TEXT NOT NULL REFERENCES navigation_screen_snapshots(snapshot_id)
        ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    observed_payload_json TEXT NOT NULL CHECK (json_valid(observed_payload_json)),
    memory_score REAL CHECK (memory_score IS NULL OR memory_score BETWEEN 0.0 AND 1.0),
    verifier_score REAL CHECK (verifier_score IS NULL OR verifier_score BETWEEN 0.0 AND 1.0),
    final_score REAL CHECK (final_score IS NULL OR final_score BETWEEN 0.0 AND 1.0),
    score_source TEXT NOT NULL DEFAULT '',
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'blocked')),
    terminal INTEGER NOT NULL DEFAULT 0 CHECK (terminal IN (0, 1)),
    dangerous_final INTEGER NOT NULL DEFAULT 0 CHECK (dangerous_final IN (0, 1)),
    forbidden INTEGER NOT NULL DEFAULT 0 CHECK (forbidden IN (0, 1)),
    selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
    PRIMARY KEY(snapshot_id, candidate_id),
    UNIQUE(snapshot_id, ordinal)
);

-- Execution details are deliberately separate from connectivity.  A lost
-- device/API connection therefore cannot be mislabeled as a navigation miss.
CREATE TABLE IF NOT EXISTS navigation_step_executions (
    decision_id TEXT PRIMARY KEY REFERENCES navigation_decisions(decision_id),
    observation_id TEXT NOT NULL UNIQUE REFERENCES navigation_observations(observation_id),
    execution_status TEXT NOT NULL CHECK (execution_status IN (
        'not_executed', 'executed', 'device_disconnected',
        'transport_error', 'executor_error'
    )),
    execution_succeeded INTEGER CHECK (execution_succeeded IS NULL OR execution_succeeded IN (0, 1)),
    observed_signal TEXT NOT NULL,
    recovery_action TEXT CHECK (recovery_action IS NULL OR recovery_action IN (
        'click', 'scroll', 'back', 'wait_and_observe', 'stop_for_user'
    )),
    candidate_forbidden INTEGER NOT NULL DEFAULT 0 CHECK (candidate_forbidden IN (0, 1)),
    reflection_level TEXT NOT NULL CHECK (reflection_level IN (
        'none', 'action', 'trajectory', 'global'
    )),
    reflection_reason TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS navigation_api_response_cache (
    request_kind TEXT NOT NULL CHECK (request_kind IN ('decide', 'observe')),
    request_id TEXT NOT NULL,
    response_json TEXT NOT NULL CHECK (json_valid(response_json)),
    created_at TEXT NOT NULL,
    PRIMARY KEY(request_kind, request_id)
);

CREATE TABLE IF NOT EXISTS navigation_recovery_memory (
    session_id TEXT NOT NULL REFERENCES navigation_sessions(session_id),
    screen_fingerprint TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    failure_signature TEXT NOT NULL,
    strike_count INTEGER NOT NULL DEFAULT 1 CHECK (strike_count > 0),
    forbidden INTEGER NOT NULL DEFAULT 1 CHECK (forbidden IN (0, 1)),
    recovery_action TEXT NOT NULL CHECK (recovery_action IN (
        'back', 'scroll', 'wait_and_observe', 'stop_for_user', 'reselect'
    )),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(session_id, screen_fingerprint, candidate_id, failure_signature)
);

CREATE TABLE IF NOT EXISTS navigation_knowledge_revision_queue (
    revision_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES navigation_sessions(session_id),
    decision_id TEXT NOT NULL REFERENCES navigation_decisions(decision_id),
    goal_id TEXT,
    first_failure_step INTEGER NOT NULL CHECK (first_failure_step >= 0),
    revision_operator TEXT NOT NULL CHECK (revision_operator IN (
        'Add', 'Delete', 'Update', 'Highlight'
    )),
    proposed_patch_json TEXT NOT NULL CHECK (json_valid(proposed_patch_json)),
    source TEXT NOT NULL CHECK (source IN ('observed_transition', 'human_review')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'approved', 'rejected', 'applied'
    )),
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_runtime_decisions_session
    ON navigation_decisions(session_id, step_ordinal);
CREATE INDEX IF NOT EXISTS idx_runtime_observations_outcome
    ON navigation_observations(outcome_type, connectivity_status, observed_at);
CREATE INDEX IF NOT EXISTS idx_runtime_recovery_forbidden
    ON navigation_recovery_memory(session_id, screen_fingerprint, forbidden)
    WHERE forbidden = 1;
CREATE INDEX IF NOT EXISTS idx_runtime_revision_status
    ON navigation_knowledge_revision_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_runtime_snapshots_session
    ON navigation_screen_snapshots(decision_id, phase, captured_at);
CREATE INDEX IF NOT EXISTS idx_runtime_candidates_selected
    ON navigation_screen_candidates(selected, forbidden, risk_level)
    WHERE selected = 1 OR forbidden = 1;

INSERT OR REPLACE INTO navigation_runtime_metadata(key, value) VALUES
    ('schema_version', '4'),
    ('database_kind', 'navigation_runtime_events'),
    ('promotion_policy', 'offline_validation_required'),
    ('interaction_contract', 'exitguide.interaction-episode.v1');

PRAGMA user_version = 4;

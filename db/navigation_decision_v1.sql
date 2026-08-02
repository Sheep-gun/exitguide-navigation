PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS navigation_db_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    goal_id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    operation TEXT NOT NULL,
    description TEXT NOT NULL,
    risk_class TEXT NOT NULL CHECK (risk_class IN ('low', 'medium', 'high')),
    terminal_action_policy TEXT NOT NULL
        CHECK (terminal_action_policy IN ('safe_navigation', 'stop_for_user')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS goal_phrases (
    phrase_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    locale TEXT NOT NULL,
    phrase TEXT NOT NULL,
    normalized_phrase TEXT NOT NULL,
    phrase_kind TEXT NOT NULL DEFAULT 'synonym'
        CHECK (phrase_kind IN ('canonical', 'synonym', 'negative', 'ambiguous')),
    source_type TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    UNIQUE(goal_id, locale, normalized_phrase, phrase_kind)
);

CREATE TABLE IF NOT EXISTS goal_relations (
    source_goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    target_goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL
        CHECK (relation_type IN ('opposite', 'related', 'prerequisite', 'specialization')),
    PRIMARY KEY(source_goal_id, target_goal_id, relation_type),
    CHECK(source_goal_id <> target_goal_id)
);

CREATE TABLE IF NOT EXISTS destination_signatures (
    signature_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    required_features_json TEXT NOT NULL CHECK (json_valid(required_features_json)),
    optional_features_json TEXT NOT NULL CHECK (json_valid(optional_features_json)),
    forbidden_features_json TEXT NOT NULL CHECK (json_valid(forbidden_features_json)),
    terminal_features_json TEXT NOT NULL CHECK (json_valid(terminal_features_json)),
    match_threshold REAL NOT NULL CHECK (match_threshold BETWEEN 0.0 AND 1.0),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    UNIQUE(goal_id, name, version)
);

CREATE TABLE IF NOT EXISTS affordance_roles (
    role_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    default_risk_level TEXT NOT NULL CHECK (default_risk_level IN ('low', 'medium', 'high', 'blocked')),
    terminal INTEGER NOT NULL DEFAULT 0 CHECK (terminal IN (0, 1))
);

CREATE TABLE IF NOT EXISTS affordance_role_aliases (
    alias_id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL REFERENCES affordance_roles(role_id) ON DELETE CASCADE,
    locale TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    negative_context_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(negative_context_json)),
    UNIQUE(role_id, locale, normalized_alias)
);

CREATE TABLE IF NOT EXISTS semantic_screens (
    screen_id TEXT PRIMARY KEY,
    semantic_fingerprint TEXT NOT NULL UNIQUE,
    title_normalized TEXT NOT NULL,
    region_roles_json TEXT NOT NULL CHECK (json_valid(region_roles_json)),
    navigation_depth INTEGER CHECK (navigation_depth IS NULL OR navigation_depth >= 0),
    auth_state TEXT NOT NULL
        CHECK (auth_state IN ('unknown', 'logged_out', 'logged_in', 'reauthentication')),
    surface_type TEXT NOT NULL
        CHECK (surface_type IN ('native', 'webview', 'hybrid', 'system', 'unknown')),
    semantic_tokens_json TEXT NOT NULL CHECK (json_valid(semantic_tokens_json)),
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screen_observations (
    observation_id TEXT PRIMARY KEY,
    screen_id TEXT NOT NULL REFERENCES semantic_screens(screen_id) ON DELETE CASCADE,
    app_package TEXT NOT NULL,
    app_version TEXT NOT NULL,
    locale TEXT NOT NULL,
    accessibility_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(accessibility_json)),
    ocr_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(ocr_json)),
    vlm_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(vlm_json)),
    source_type TEXT NOT NULL
        CHECK (source_type IN ('human_gold', 'real_device', 'android_control', 'synthetic', 'model_inference')),
    captured_at TEXT NOT NULL,
    UNIQUE(screen_id, app_package, app_version, locale, source_type, captured_at)
);

CREATE TABLE IF NOT EXISTS affordances (
    affordance_id TEXT PRIMARY KEY,
    screen_id TEXT NOT NULL REFERENCES semantic_screens(screen_id) ON DELETE CASCADE,
    candidate_key TEXT NOT NULL,
    label TEXT NOT NULL,
    normalized_label TEXT NOT NULL,
    icon_semantics TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL,
    parent_semantics TEXT NOT NULL DEFAULT '',
    nearby_text TEXT NOT NULL DEFAULT '',
    position_bucket TEXT NOT NULL DEFAULT 'unknown'
        CHECK (position_bucket IN ('top', 'middle', 'bottom', 'overlay', 'unknown')),
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'blocked')),
    dangerous_final INTEGER NOT NULL DEFAULT 0 CHECK (dangerous_final IN (0, 1)),
    function_roles_json TEXT NOT NULL CHECK (json_valid(function_roles_json)),
    source_element_key TEXT NOT NULL DEFAULT '',
    UNIQUE(screen_id, candidate_key)
);

CREATE TABLE IF NOT EXISTS decision_cases (
    case_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
    screen_id TEXT NOT NULL REFERENCES semantic_screens(screen_id),
    goal_text_normalized TEXT NOT NULL,
    goal_conditions_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(goal_conditions_json)),
    chosen_action TEXT NOT NULL
        CHECK (chosen_action IN ('click', 'scroll', 'back', 'wait_and_observe', 'stop_for_user')),
    chosen_affordance_id TEXT REFERENCES affordances(affordance_id),
    scroll_direction TEXT CHECK (scroll_direction IS NULL OR scroll_direction IN ('up', 'down')),
    expected_destination_signature_id TEXT REFERENCES destination_signatures(signature_id),
    source_app_package TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_step_ordinal INTEGER NOT NULL CHECK (source_step_ordinal >= 0),
    source_type TEXT NOT NULL
        CHECK (source_type IN ('human_gold', 'real_device', 'android_control', 'synthetic', 'model_inference')),
    evidence_weight REAL NOT NULL CHECK (evidence_weight BETWEEN 0.0 AND 1.0),
    observed_at TEXT NOT NULL,
    UNIQUE(source_type, source_record_id, source_step_ordinal),
    CHECK (
        (chosen_action = 'click' AND chosen_affordance_id IS NOT NULL AND scroll_direction IS NULL)
        OR (chosen_action = 'scroll' AND chosen_affordance_id IS NULL AND scroll_direction IS NOT NULL)
        OR (chosen_action IN ('back', 'wait_and_observe', 'stop_for_user')
            AND chosen_affordance_id IS NULL AND scroll_direction IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS transition_outcomes (
    outcome_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE REFERENCES decision_cases(case_id) ON DELETE CASCADE,
    next_screen_id TEXT REFERENCES semantic_screens(screen_id),
    outcome_type TEXT NOT NULL CHECK (outcome_type IN (
        'navigated', 'destination_reached', 'no_change', 'wrong_destination',
        'external_app', 'login_required', 'popup', 'infinite_feed',
        'network_error', 'blocked', 'unknown'
    )),
    connectivity_status TEXT NOT NULL CHECK (connectivity_status IN (
        'observed', 'device_disconnected', 'transport_error', 'not_observed'
    )),
    state_changed INTEGER CHECK (state_changed IS NULL OR state_changed IN (0, 1)),
    destination_match_before REAL CHECK (destination_match_before IS NULL OR destination_match_before BETWEEN 0.0 AND 1.0),
    destination_match_after REAL CHECK (destination_match_after IS NULL OR destination_match_after BETWEEN 0.0 AND 1.0),
    distance_before REAL CHECK (distance_before IS NULL OR distance_before BETWEEN 0.0 AND 1.0),
    distance_after REAL CHECK (distance_after IS NULL OR distance_after BETWEEN 0.0 AND 1.0),
    distance_method TEXT NOT NULL DEFAULT 'not_measured',
    progress_label TEXT NOT NULL CHECK (progress_label IN (
        'reached', 'advanced', 'unchanged', 'regressed', 'unknown'
    )),
    failure_class TEXT NOT NULL DEFAULT '',
    external_target TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    CHECK (
        connectivity_status = 'observed'
        OR (state_changed IS NULL AND next_screen_id IS NULL AND progress_label = 'unknown')
    )
);

CREATE TABLE IF NOT EXISTS recovery_memories (
    recovery_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
    screen_id TEXT NOT NULL REFERENCES semantic_screens(screen_id),
    forbidden_affordance_id TEXT REFERENCES affordances(affordance_id),
    failure_signature TEXT NOT NULL,
    recovery_action TEXT NOT NULL
        CHECK (recovery_action IN ('back', 'scroll', 'wait_and_observe', 'stop_for_user')),
    recovery_direction TEXT CHECK (recovery_direction IS NULL OR recovery_direction IN ('up', 'down')),
    result_outcome_type TEXT NOT NULL,
    recovered INTEGER NOT NULL DEFAULT 0 CHECK (recovered IN (0, 1)),
    source_case_id TEXT REFERENCES decision_cases(case_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'goal', 'destination_signature', 'screen', 'affordance', 'decision_case',
        'transition_outcome', 'recovery_memory'
    )),
    entity_id TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'human_gold', 'real_device', 'android_control', 'synthetic', 'model_inference'
    )),
    source_ref TEXT NOT NULL,
    verification_count INTEGER NOT NULL DEFAULT 1 CHECK (verification_count >= 0),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    app_package TEXT NOT NULL DEFAULT '',
    app_version TEXT NOT NULL DEFAULT '',
    locale TEXT NOT NULL DEFAULT '',
    last_verified_at TEXT NOT NULL,
    UNIQUE(entity_type, entity_id, source_type, source_ref)
);

CREATE TABLE IF NOT EXISTS evaluation_app_splits (
    split_version TEXT NOT NULL,
    app_package TEXT NOT NULL,
    split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test')),
    reason TEXT NOT NULL,
    PRIMARY KEY(split_version, app_package)
);

CREATE TABLE IF NOT EXISTS retrieval_events (
    retrieval_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
    query_screen_fingerprint TEXT NOT NULL,
    current_candidate_keys_json TEXT NOT NULL CHECK (json_valid(current_candidate_keys_json)),
    retrieved_case_ids_json TEXT NOT NULL CHECK (json_valid(retrieved_case_ids_json)),
    excluded_app_package TEXT NOT NULL DEFAULT '',
    selected_action TEXT NOT NULL DEFAULT '',
    selected_candidate_key TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS goal_phrase_fts USING fts5(
    goal_id UNINDEXED,
    phrase,
    tokenize='unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS decision_case_fts USING fts5(
    case_id UNINDEXED,
    goal_id UNINDEXED,
    search_text,
    tokenize='unicode61'
);

CREATE INDEX IF NOT EXISTS idx_goal_phrases_normalized
    ON goal_phrases(locale, normalized_phrase, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_destination_signatures_goal
    ON destination_signatures(goal_id, match_threshold DESC);
CREATE INDEX IF NOT EXISTS idx_role_aliases_normalized
    ON affordance_role_aliases(locale, normalized_alias, confidence DESC);
CREATE INDEX IF NOT EXISTS idx_screen_observations_app
    ON screen_observations(app_package, locale, app_version, screen_id);
CREATE INDEX IF NOT EXISTS idx_affordances_screen
    ON affordances(screen_id, normalized_label, role);
CREATE INDEX IF NOT EXISTS idx_affordances_dangerous
    ON affordances(screen_id, dangerous_final) WHERE dangerous_final = 1;
CREATE INDEX IF NOT EXISTS idx_decision_cases_goal_screen
    ON decision_cases(goal_id, screen_id, evidence_weight DESC);
CREATE INDEX IF NOT EXISTS idx_decision_cases_holdout
    ON decision_cases(source_app_package, goal_id, source_type);
CREATE INDEX IF NOT EXISTS idx_outcomes_progress
    ON transition_outcomes(progress_label, outcome_type, connectivity_status);
CREATE INDEX IF NOT EXISTS idx_outcomes_success
    ON transition_outcomes(case_id, destination_match_after DESC)
    WHERE connectivity_status = 'observed' AND progress_label IN ('reached', 'advanced');
CREATE INDEX IF NOT EXISTS idx_recovery_goal_failure
    ON recovery_memories(goal_id, failure_signature, recovered DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_entity
    ON evidence_records(entity_type, entity_id, confidence DESC, last_verified_at DESC);

CREATE VIEW IF NOT EXISTS verified_decision_cases AS
SELECT
    c.case_id,
    c.goal_id,
    c.screen_id,
    c.goal_text_normalized,
    c.goal_conditions_json,
    c.chosen_action,
    c.chosen_affordance_id,
    c.scroll_direction,
    c.source_app_package,
    c.source_type,
    c.evidence_weight,
    s.semantic_fingerprint,
    s.title_normalized,
    s.auth_state,
    s.surface_type,
    s.semantic_tokens_json,
    a.label AS chosen_label,
    a.normalized_label AS chosen_normalized_label,
    a.role AS chosen_role,
    a.function_roles_json,
    a.risk_level,
    a.dangerous_final,
    o.outcome_type,
    o.connectivity_status,
    o.progress_label,
    o.destination_match_after
FROM decision_cases AS c
JOIN semantic_screens AS s ON s.screen_id = c.screen_id
LEFT JOIN affordances AS a ON a.affordance_id = c.chosen_affordance_id
LEFT JOIN transition_outcomes AS o ON o.case_id = c.case_id
WHERE c.evidence_weight >= 0.6;

PRAGMA user_version = 1;

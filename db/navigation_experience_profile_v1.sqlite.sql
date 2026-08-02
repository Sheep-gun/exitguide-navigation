-- ExitGuide Navigation Experience Profile v1
--
-- Non-destructive standards profile layered on Navigation Decision DB v1.
-- The existing runtime tables remain unchanged so the current retriever keeps
-- working.  This migration is applied only to a copied database and advances
-- SQLite user_version from 1 to 2.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS navigation_standard_profiles (
    profile_id TEXT PRIMARY KEY,
    profile_version TEXT NOT NULL,
    title TEXT NOT NULL,
    json_schema_dialect TEXT NOT NULL,
    default_language_tag TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_term_mappings (
    mapping_id TEXT PRIMARY KEY,
    local_entity TEXT NOT NULL,
    local_field TEXT NOT NULL,
    standard_name TEXT NOT NULL,
    standard_term_uri TEXT NOT NULL,
    mapping_kind TEXT NOT NULL
        CHECK (mapping_kind IN ('exact', 'close', 'extension')),
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(local_entity, local_field, standard_term_uri)
);

-- W3C SKOS profile for Goal Ontology.
CREATE TABLE IF NOT EXISTS goal_concept_schemes (
    scheme_id TEXT PRIMARY KEY,
    scheme_uri TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    default_language_tag TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_standard_concepts (
    goal_id TEXT PRIMARY KEY REFERENCES goals(goal_id) ON DELETE CASCADE,
    scheme_id TEXT NOT NULL REFERENCES goal_concept_schemes(scheme_id),
    concept_uri TEXT NOT NULL UNIQUE,
    notation TEXT NOT NULL UNIQUE,
    concept_status TEXT NOT NULL DEFAULT 'active'
        CHECK (concept_status IN ('active', 'deprecated'))
);

CREATE TABLE IF NOT EXISTS goal_label_mappings (
    phrase_id TEXT PRIMARY KEY REFERENCES goal_phrases(phrase_id) ON DELETE CASCADE,
    skos_property_uri TEXT NOT NULL,
    language_tag TEXT NOT NULL,
    mapping_kind TEXT NOT NULL
        CHECK (mapping_kind IN ('exact', 'extension'))
);

CREATE TABLE IF NOT EXISTS goal_relation_mappings (
    source_goal_id TEXT NOT NULL,
    target_goal_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    predicate_uri TEXT NOT NULL,
    mapping_kind TEXT NOT NULL
        CHECK (mapping_kind IN ('exact', 'close', 'extension')),
    PRIMARY KEY (source_goal_id, target_goal_id, relation_type),
    FOREIGN KEY (source_goal_id, target_goal_id, relation_type)
        REFERENCES goal_relations(source_goal_id, target_goal_id, relation_type)
        ON DELETE CASCADE
);

-- Versioned contracts for Android Accessibility/OCR/VLM observations.
CREATE TABLE IF NOT EXISTS observation_contracts (
    observation_id TEXT PRIMARY KEY
        REFERENCES screen_observations(observation_id) ON DELETE CASCADE,
    accessibility_contract_uri TEXT NOT NULL,
    accessibility_profile TEXT NOT NULL
        CHECK (accessibility_profile IN ('android_accessibility_node_subset_v1', 'not_available')),
    ocr_contract_uri TEXT NOT NULL,
    vlm_contract_uri TEXT NOT NULL,
    normalization_version TEXT NOT NULL
);

-- RLDS-compatible Episode/Step projection.  decision_cases remains the
-- canonical ExitGuide decision row; experience_steps supplies RLDS flags.
CREATE TABLE IF NOT EXISTS experience_episodes (
    episode_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES goals(goal_id),
    source_type TEXT NOT NULL
        CHECK (source_type IN ('human_gold', 'real_device', 'synthetic', 'model_inference')),
    source_record_id TEXT NOT NULL,
    source_app_package TEXT NOT NULL,
    app_version TEXT NOT NULL DEFAULT '',
    language_tag TEXT NOT NULL,
    split_version TEXT NOT NULL DEFAULT 'app-disjoint-v1',
    split TEXT NOT NULL CHECK (split IN ('train', 'validation', 'test', 'unassigned')),
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    end_reason TEXT NOT NULL
        CHECK (end_reason IN ('destination_reached', 'user_handoff', 'failed', 'truncated', 'unknown')),
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    UNIQUE(source_type, source_record_id)
);

CREATE TABLE IF NOT EXISTS experience_steps (
    case_id TEXT PRIMARY KEY REFERENCES decision_cases(case_id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL REFERENCES experience_episodes(episode_id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL CHECK (step_index >= 0),
    is_first INTEGER NOT NULL CHECK (is_first IN (0, 1)),
    is_last INTEGER NOT NULL CHECK (is_last IN (0, 1)),
    is_terminal INTEGER NOT NULL CHECK (is_terminal IN (0, 1)),
    reward REAL,
    discount REAL CHECK (discount IS NULL OR discount BETWEEN 0.0 AND 1.0),
    reward_semantics TEXT NOT NULL DEFAULT 'exitguide_progress_v1',
    step_metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(step_metadata_json)),
    UNIQUE(episode_id, step_index),
    CHECK (is_terminal = 0 OR is_last = 1)
);

-- W3C PROV-O relational profile for Evidence and Confidence.
CREATE TABLE IF NOT EXISTS provenance_agents (
    agent_id TEXT PRIMARY KEY,
    agent_uri TEXT NOT NULL UNIQUE,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('person', 'organization', 'software')),
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_activities (
    activity_id TEXT PRIMARY KEY,
    activity_uri TEXT NOT NULL UNIQUE,
    activity_type TEXT NOT NULL,
    associated_agent_id TEXT NOT NULL REFERENCES provenance_agents(agent_id),
    source_ref TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attributes_json)),
    UNIQUE(activity_type, source_ref)
);

CREATE TABLE IF NOT EXISTS evidence_provenance (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
    entity_uri TEXT NOT NULL,
    generated_by_activity_id TEXT NOT NULL REFERENCES provenance_activities(activity_id),
    attributed_to_agent_id TEXT NOT NULL REFERENCES provenance_agents(agent_id),
    derived_from_ref TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_standard_mapping_local
    ON standard_term_mappings(local_entity, local_field, mapping_kind);
CREATE INDEX IF NOT EXISTS idx_goal_concepts_scheme
    ON goal_standard_concepts(scheme_id, notation);
CREATE INDEX IF NOT EXISTS idx_goal_labels_language
    ON goal_label_mappings(language_tag, skos_property_uri);
CREATE INDEX IF NOT EXISTS idx_episodes_goal_split
    ON experience_episodes(goal_id, split, source_app_package);
CREATE INDEX IF NOT EXISTS idx_steps_episode
    ON experience_steps(episode_id, step_index);
CREATE INDEX IF NOT EXISTS idx_prov_activity_agent
    ON provenance_activities(associated_agent_id, ended_at);
CREATE INDEX IF NOT EXISTS idx_prov_evidence_entity
    ON evidence_provenance(entity_uri, generated_at);

CREATE VIEW IF NOT EXISTS skos_goal_concepts_v1 AS
SELECT
    c.concept_uri,
    c.notation,
    c.scheme_id,
    g.goal_id,
    g.description,
    p.phrase,
    l.language_tag,
    l.skos_property_uri
FROM goal_standard_concepts AS c
JOIN goals AS g ON g.goal_id = c.goal_id
LEFT JOIN goal_phrases AS p ON p.goal_id = g.goal_id
LEFT JOIN goal_label_mappings AS l ON l.phrase_id = p.phrase_id;

CREATE VIEW IF NOT EXISTS rlds_experience_steps_v1 AS
SELECT
    e.episode_id,
    x.step_index,
    x.is_first,
    x.is_last,
    x.is_terminal,
    c.screen_id AS observation_screen_id,
    c.chosen_action AS action,
    c.chosen_affordance_id AS action_candidate_id,
    c.scroll_direction,
    x.reward,
    x.discount,
    o.next_screen_id,
    o.outcome_type,
    o.connectivity_status,
    o.progress_label
FROM experience_steps AS x
JOIN experience_episodes AS e ON e.episode_id = x.episode_id
JOIN decision_cases AS c ON c.case_id = x.case_id
LEFT JOIN transition_outcomes AS o ON o.case_id = c.case_id;

CREATE VIEW IF NOT EXISTS prov_evidence_entities_v1 AS
SELECT
    p.entity_uri,
    e.entity_type,
    e.entity_id,
    p.generated_by_activity_id,
    p.attributed_to_agent_id,
    p.derived_from_ref,
    p.generated_at,
    e.confidence,
    e.verification_count
FROM evidence_provenance AS p
JOIN evidence_records AS e ON e.evidence_id = p.evidence_id;

PRAGMA user_version = 2;

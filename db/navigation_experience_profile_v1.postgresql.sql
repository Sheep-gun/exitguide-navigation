-- ExitGuide Navigation Experience Profile v1 - PostgreSQL 15+
-- Prerequisite: the Navigation Decision DB core tables (goals,
-- goal_phrases, goal_relations, screen_observations, decision_cases,
-- evidence_records, ...) have been migrated with the same primary keys.

BEGIN;

CREATE TABLE IF NOT EXISTS navigation_standard_profiles (
    profile_id text PRIMARY KEY,
    profile_version text NOT NULL,
    title text NOT NULL,
    json_schema_dialect text NOT NULL,
    default_language_tag text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_term_mappings (
    mapping_id text PRIMARY KEY,
    local_entity text NOT NULL,
    local_field text NOT NULL,
    standard_name text NOT NULL,
    standard_term_uri text NOT NULL,
    mapping_kind text NOT NULL CHECK (mapping_kind IN ('exact', 'close', 'extension')),
    notes text NOT NULL DEFAULT '',
    UNIQUE(local_entity, local_field, standard_term_uri)
);

CREATE TABLE IF NOT EXISTS goal_concept_schemes (
    scheme_id text PRIMARY KEY,
    scheme_uri text NOT NULL UNIQUE,
    title text NOT NULL,
    version text NOT NULL,
    default_language_tag text NOT NULL
);

CREATE TABLE IF NOT EXISTS goal_standard_concepts (
    goal_id text PRIMARY KEY REFERENCES goals(goal_id) ON DELETE CASCADE,
    scheme_id text NOT NULL REFERENCES goal_concept_schemes(scheme_id),
    concept_uri text NOT NULL UNIQUE,
    notation text NOT NULL UNIQUE,
    concept_status text NOT NULL DEFAULT 'active'
        CHECK (concept_status IN ('active', 'deprecated'))
);

CREATE TABLE IF NOT EXISTS goal_label_mappings (
    phrase_id text PRIMARY KEY REFERENCES goal_phrases(phrase_id) ON DELETE CASCADE,
    skos_property_uri text NOT NULL,
    language_tag text NOT NULL,
    mapping_kind text NOT NULL CHECK (mapping_kind IN ('exact', 'extension'))
);

CREATE TABLE IF NOT EXISTS goal_relation_mappings (
    source_goal_id text NOT NULL,
    target_goal_id text NOT NULL,
    relation_type text NOT NULL,
    predicate_uri text NOT NULL,
    mapping_kind text NOT NULL CHECK (mapping_kind IN ('exact', 'close', 'extension')),
    PRIMARY KEY (source_goal_id, target_goal_id, relation_type),
    FOREIGN KEY (source_goal_id, target_goal_id, relation_type)
        REFERENCES goal_relations(source_goal_id, target_goal_id, relation_type)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS observation_contracts (
    observation_id text PRIMARY KEY REFERENCES screen_observations(observation_id) ON DELETE CASCADE,
    accessibility_contract_uri text NOT NULL,
    accessibility_profile text NOT NULL
        CHECK (accessibility_profile IN ('android_accessibility_node_subset_v1', 'not_available')),
    ocr_contract_uri text NOT NULL,
    vlm_contract_uri text NOT NULL,
    normalization_version text NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_episodes (
    episode_id text PRIMARY KEY,
    goal_id text NOT NULL REFERENCES goals(goal_id),
    source_type text NOT NULL
        CHECK (source_type IN ('human_gold', 'real_device', 'synthetic', 'model_inference')),
    source_record_id text NOT NULL,
    source_app_package text NOT NULL,
    app_version text NOT NULL DEFAULT '',
    language_tag text NOT NULL,
    split_version text NOT NULL DEFAULT 'app-disjoint-v1',
    split text NOT NULL CHECK (split IN ('train', 'validation', 'test', 'unassigned')),
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    end_reason text NOT NULL
        CHECK (end_reason IN ('destination_reached', 'user_handoff', 'failed', 'truncated', 'unknown')),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(source_type, source_record_id)
);

CREATE TABLE IF NOT EXISTS experience_steps (
    case_id text PRIMARY KEY REFERENCES decision_cases(case_id) ON DELETE CASCADE,
    episode_id text NOT NULL REFERENCES experience_episodes(episode_id) ON DELETE CASCADE,
    step_index integer NOT NULL CHECK (step_index >= 0),
    is_first boolean NOT NULL,
    is_last boolean NOT NULL,
    is_terminal boolean NOT NULL,
    reward double precision,
    discount double precision CHECK (discount IS NULL OR discount BETWEEN 0.0 AND 1.0),
    reward_semantics text NOT NULL DEFAULT 'exitguide_progress_v1',
    step_metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(episode_id, step_index),
    CHECK (NOT is_terminal OR is_last)
);

CREATE TABLE IF NOT EXISTS provenance_agents (
    agent_id text PRIMARY KEY,
    agent_uri text NOT NULL UNIQUE,
    agent_type text NOT NULL CHECK (agent_type IN ('person', 'organization', 'software')),
    display_name text NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_activities (
    activity_id text PRIMARY KEY,
    activity_uri text NOT NULL UNIQUE,
    activity_type text NOT NULL,
    associated_agent_id text NOT NULL REFERENCES provenance_agents(agent_id),
    source_ref text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    attributes_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(activity_type, source_ref)
);

CREATE TABLE IF NOT EXISTS evidence_provenance (
    evidence_id text PRIMARY KEY REFERENCES evidence_records(evidence_id) ON DELETE CASCADE,
    entity_uri text NOT NULL,
    generated_by_activity_id text NOT NULL REFERENCES provenance_activities(activity_id),
    attributed_to_agent_id text NOT NULL REFERENCES provenance_agents(agent_id),
    derived_from_ref text NOT NULL,
    generated_at timestamptz NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_episode_metadata_gin
    ON experience_episodes USING gin (metadata_json);
CREATE INDEX IF NOT EXISTS idx_activity_attributes_gin
    ON provenance_activities USING gin (attributes_json);

CREATE OR REPLACE VIEW skos_goal_concepts_v1 AS
SELECT c.concept_uri, c.notation, c.scheme_id, g.goal_id, g.description,
       p.phrase, l.language_tag, l.skos_property_uri
FROM goal_standard_concepts c
JOIN goals g ON g.goal_id = c.goal_id
LEFT JOIN goal_phrases p ON p.goal_id = g.goal_id
LEFT JOIN goal_label_mappings l ON l.phrase_id = p.phrase_id;

CREATE OR REPLACE VIEW rlds_experience_steps_v1 AS
SELECT e.episode_id, x.step_index, x.is_first, x.is_last, x.is_terminal,
       c.screen_id AS observation_screen_id, c.chosen_action AS action,
       c.chosen_affordance_id AS action_candidate_id, c.scroll_direction,
       x.reward, x.discount, o.next_screen_id, o.outcome_type,
       o.connectivity_status, o.progress_label
FROM experience_steps x
JOIN experience_episodes e ON e.episode_id = x.episode_id
JOIN decision_cases c ON c.case_id = x.case_id
LEFT JOIN transition_outcomes o ON o.case_id = c.case_id;

CREATE OR REPLACE VIEW prov_evidence_entities_v1 AS
SELECT p.entity_uri, e.entity_type, e.entity_id,
       p.generated_by_activity_id, p.attributed_to_agent_id,
       p.derived_from_ref, p.generated_at, e.confidence,
       e.verification_count
FROM evidence_provenance p
JOIN evidence_records e ON e.evidence_id = p.evidence_id;

COMMIT;

-- seed_gold.sql — the integration-test "cassette": a small, hand-built set of gold-mart rows that
-- mirror the real shapes, crafted to exercise every code path. Applied to a throwaway Postgres
-- (testcontainers / CI `services: postgres`) by tests/integration/conftest.py. Idempotent (DROP+CREATE).
--
-- recall_event_id = md5(source || '|' || source_recall_id) so the detail endpoint's computed key
-- (md5("SOURCE|recall_id")) matches a seeded row. Scenarios covered (mart_recall_summary):
--   FDA F-1001  active (Class I), 2 product names, recall-level UPC (gold object shape [{"upc":...}])
--   FDA F-1006  inactive (Class III), same firm as F-1001 (firm substring "acme" -> 2 hits)
--   CPSC 24-003 is_active NULL (tri-state), classification NULL, product_names/hins NULL (-> [])
--   USDA U-2002 inactive (Class II), MULTI-FIRM rollup, state codes array, retracted
--   NHTSA 24V-004 is_active NULL, models array
--   USCG USCG-005 active (severity H), HIN array
-- product_search / firm_profile tables are added by later commits (C6/C7).

drop table if exists mart_recall_summary;

create table mart_recall_summary (
    recall_event_id            text primary key,
    source                     text        not null,
    source_recall_id           text        not null,
    title                      text,
    recall_reason              text,
    url                        text,
    announced_at               timestamptz,
    published_at               timestamptz not null,
    classification             text,
    risk_level                 text,
    lifecycle_status           text,
    is_active                  boolean,
    reason_category            text,
    distribution_scope         text        not null,
    distribution_states        text,
    distribution_state_codes   text[],
    distribution_country_codes text[],
    hazards                    jsonb,
    product_upcs               jsonb,
    corrective_action          text,
    consequence_of_defect      text,
    primary_firm_name          text,
    firm_count                 bigint      not null,
    firms                      jsonb       not null,
    product_count              bigint      not null,
    product_names              jsonb,
    models                     jsonb,
    hins                       jsonb,
    first_seen_at              timestamptz,
    last_seen_at               timestamptz,
    edit_count                 integer,
    is_currently_active        boolean,
    was_ever_retracted         boolean,
    edit_event_count           bigint      not null,
    has_been_edited            boolean     not null,
    search_vector              tsvector
);

create index mart_recall_summary_source_published on mart_recall_summary (source, published_at);
create index mart_recall_summary_is_active on mart_recall_summary (is_active);
create index mart_recall_summary_classification on mart_recall_summary (classification);
create index mart_recall_summary_published_desc_evt on mart_recall_summary (published_at desc, recall_event_id);
create index mart_recall_summary_sv_gin on mart_recall_summary using gin (search_vector);

insert into mart_recall_summary (
    recall_event_id, source, source_recall_id, title, recall_reason, url, announced_at, published_at,
    classification, risk_level, lifecycle_status, is_active, reason_category, distribution_scope,
    distribution_states, distribution_state_codes, distribution_country_codes, hazards, product_upcs,
    corrective_action, consequence_of_defect, primary_firm_name, firm_count, firms, product_count,
    product_names, models, hins, first_seen_at, last_seen_at, edit_count, is_currently_active,
    was_ever_retracted, edit_event_count, has_been_edited
) values
-- CPSC 24-003: newest, is_active NULL, classification NULL, models only (product_names/hins NULL)
(md5('CPSC|24-003'), 'CPSC', '24-003', 'Globex Heater Fire Hazard', 'Overheating risk',
 'https://example.test/cpsc/24-003', null, '2026-06-01 10:00:00+00',
 null, null, null, null, null, 'Unspecified',
 null, null, null, '[{"name": "Fire"}]', null,
 'Stop use and contact Globex', 'Burn and fire injuries', 'Globex Corporation', 1,
 '[{"firm_id": "11111111111111111111111111111111", "name": "Globex Corporation", "role": "manufacturer", "match_confidence": "exact_name"}]',
 1, null, '["GX-100"]', null, '2026-06-01 11:00:00+00', '2026-06-02 11:00:00+00', 1, null, null, 0, false),

-- FDA F-1006: inactive, Class III, same firm as F-1001 (Acme)
(md5('FDA|F-1006'), 'FDA', 'F-1006', 'Acme Cereal Undeclared Milk', 'Undeclared allergen (milk)',
 'https://example.test/fda/F-1006', '2026-05-12 00:00:00+00', '2026-05-12 09:00:00+00',
 'Class III', null, 'Completed', false, null, 'Nationwide',
 'Nationwide', null, null, null, '[{"upc": "099999999999"}]',
 'Return to store for refund', 'Allergic reaction', 'Acme Foods Inc', 1,
 '[{"firm_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "name": "Acme Foods Inc", "role": "establishment", "match_confidence": "fei_exact"}]',
 1, '["Acme Cereal 12oz"]', null, null, '2026-05-12 10:00:00+00', '2026-05-13 10:00:00+00', 1, null, null, 0, false),

-- FDA F-1001: active, Class I, 2 product names, recall-level UPC, announced_at set
(md5('FDA|F-1001'), 'FDA', 'F-1001', 'Acme Peanut Butter Salmonella', 'Possible Salmonella contamination',
 'https://example.test/fda/F-1001', '2026-05-10 00:00:00+00', '2026-05-10 12:00:00+00',
 'Class I', null, 'Ongoing', true, null, 'Nationwide',
 'Nationwide', null, null, null, '[{"upc": "012345678905"}]',
 'Do not eat; discard', 'Salmonella infection', 'Acme Foods Inc', 1,
 '[{"firm_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "name": "Acme Foods Inc", "role": "establishment", "match_confidence": "fei_exact"}]',
 2, '["Acme Peanut Butter 16oz", "Acme Peanut Butter 32oz"]', null, null,
 '2026-05-10 13:00:00+00', '2026-05-11 13:00:00+00', 2, null, null, 1, true),

-- USDA U-2002: inactive, Class II, MULTI-FIRM, state codes, retracted
(md5('USDA|U-2002'), 'USDA', 'U-2002', 'Tyson Frozen Chicken Strips Recall', 'Possible foreign matter',
 'https://example.test/usda/U-2002', '2026-04-15 00:00:00+00', '2026-04-15 08:00:00+00',
 'Class II', 'Low - Class II', 'Closed Recall', false, 'Other Contamination', 'Regional',
 'CA, OR, WA', '{CA,OR,WA}', '{MX,GB}', null, null,
 'Return to place of purchase', 'Choking hazard', 'Tyson Foods', 2,
 '[{"firm_id": "22222222222222222222222222222222", "name": "Tyson Foods", "role": "establishment", "match_confidence": "usda_unambiguous"}, {"firm_id": "33333333333333333333333333333333", "name": "Cold Storage Co", "role": "distributor", "match_confidence": "name_variant_exact"}]',
 1, '["Frozen Chicken Strips 24oz"]', null, null, '2026-04-15 09:00:00+00', '2026-04-16 09:00:00+00',
 3, false, true, 4, true),

-- NHTSA 24V-004: is_active NULL, models array
(md5('NHTSA|24V-004'), 'NHTSA', '24V-004', 'Honda Fuel Pump Recall', 'Fuel pump may fail',
 'https://example.test/nhtsa/24V-004', null, '2026-03-20 07:00:00+00',
 null, null, null, null, null, 'Nationwide',
 null, null, null, null, null,
 'Dealer will replace fuel pump', 'Engine stall', 'Honda Motor Co', 1,
 '[{"firm_id": "44444444444444444444444444444444", "name": "Honda Motor Co", "role": "manufacturer", "match_confidence": "exact_name"}]',
 2, null, '["Civic", "Accord"]', null, '2026-03-20 08:00:00+00', '2026-03-21 08:00:00+00',
 1, true, false, 0, false),

-- USCG USCG-005: active, severity H, HIN array
(md5('USCG|USCG-005'), 'USCG', 'USCG-005', 'Boaty Hull Defect', 'Hull may crack',
 'https://example.test/uscg/USCG-005', null, '2026-02-10 06:00:00+00',
 'H', null, 'Open', true, null, 'Unspecified',
 null, null, null, null, null,
 'Contact manufacturer for inspection', 'Sinking hazard', 'Boaty Mfg', 1,
 '[{"firm_id": "55555555555555555555555555555555", "name": "Boaty Mfg", "role": "manufacturer", "match_confidence": "uscg_mic_unambiguous"}]',
 1, null, null, '["ABC12345D404"]', '2026-02-10 07:00:00+00', '2026-02-11 07:00:00+00',
 1, null, null, 0, false);

-- Recall-grain FTS vector (Option B): mirrors gold's setweight buckets — A=title,
-- B=product_names(flattened)+primary_firm_name, C=recall_reason, D=consequence_of_defect.
-- Populated post-insert (like the product_search vector below).
update mart_recall_summary set search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A')
    || setweight(
        to_tsvector(
            'english',
            coalesce(
                (select string_agg(elem, ' ') from jsonb_array_elements_text(product_names) t(elem)), ''
            )
            || ' ' || coalesce(primary_firm_name, '')
        ),
        'B'
    )
    || setweight(to_tsvector('english', coalesce(recall_reason, '')), 'C')
    || setweight(to_tsvector('english', coalesce(consequence_of_defect, '')), 'D');

-- ---------------------------------------------------------------------------------------------------
-- mart_product_search (C6). One row per recalled product; recall_event_id links to a recall above.
-- search_vector is populated by the UPDATE below (mirrors the dbt-stored tsvector). recall_product_upcs
-- carries the recall-level UPCs as an array of objects [{"upc":"X"}] (the real gold shape; the
-- per-product `upc` column is NULL, as in production).
-- ---------------------------------------------------------------------------------------------------

drop table if exists mart_product_search;

create table mart_product_search (
    recall_product_id   text primary key,
    recall_event_id     text        not null,
    source              text        not null,
    source_recall_id    text        not null,
    product_name        text,
    product_description text,
    model               text,
    type                text,
    model_year          text,
    hin                 text,
    upc                 text,
    recall_title        text,
    classification      text,
    risk_level          text,
    published_at        timestamptz not null,
    url                 text,
    is_active           boolean,
    firm_name           text,
    recall_product_upcs jsonb,
    search_vector       tsvector
);

create index mart_product_search_hin on mart_product_search (hin);
create index mart_product_search_model on mart_product_search (model);
create index mart_product_search_upc on mart_product_search (upc);
create index mart_product_search_recall_event on mart_product_search (recall_event_id);
create index mart_product_search_sv_gin on mart_product_search using gin (search_vector);
create index mart_product_search_upcs_gin on mart_product_search using gin (recall_product_upcs);

insert into mart_product_search (
    recall_product_id, recall_event_id, source, source_recall_id, product_name, product_description,
    model, type, model_year, hin, upc, recall_title, classification, risk_level, published_at, url,
    is_active, firm_name, recall_product_upcs
) values
('rp-001', md5('FDA|F-1001'), 'FDA', 'F-1001', 'Acme Peanut Butter 16oz', 'Creamy peanut butter spread',
 null, 'Food', null, null, null, 'Acme Peanut Butter Salmonella', 'Class I', null,
 '2026-05-10 12:00:00+00', 'https://example.test/fda/F-1001', true, 'Acme Foods Inc', '[{"upc": "012345678905"}]'),
('rp-002', md5('NHTSA|24V-004'), 'NHTSA', '24V-004', 'Honda Civic', 'Compact sedan',
 'Civic', 'Vehicle', '2019', null, null, 'Honda Fuel Pump Recall', null, null,
 '2026-03-20 07:00:00+00', 'https://example.test/nhtsa/24V-004', null, 'Honda Motor Co', null),
('rp-003', md5('NHTSA|24V-004'), 'NHTSA', '24V-004', 'Honda Accord', 'Midsize sedan',
 'Accord', 'Vehicle', '2020', null, null, 'Honda Fuel Pump Recall', null, null,
 '2026-03-20 07:00:00+00', 'https://example.test/nhtsa/24V-004', null, 'Honda Motor Co', null),
('rp-004', md5('USCG|USCG-005'), 'USCG', 'USCG-005', 'Boaty 30ft Hull', 'Fiberglass boat hull',
 null, 'Boat', null, 'ABC12345D404', null, 'Boaty Hull Defect', 'H', null,
 '2026-02-10 06:00:00+00', 'https://example.test/uscg/USCG-005', true, 'Boaty Mfg', null),
('rp-005', md5('FDA|F-1006'), 'FDA', 'F-1006', 'Acme Cereal 12oz', 'Breakfast cereal',
 null, 'Food', null, null, null, 'Acme Cereal Undeclared Milk', 'Class III', null,
 '2026-05-12 09:00:00+00', 'https://example.test/fda/F-1006', false, 'Acme Foods Inc', '[{"upc": "099999999999"}]');

update mart_product_search set search_vector = to_tsvector('english',
    coalesce(product_name, '') || ' ' || coalesce(product_description, '') || ' ' ||
    coalesce(recall_title, '') || ' ' || coalesce(firm_name, ''));

-- ---------------------------------------------------------------------------------------------------
-- mart_firm_profile (C7). One row per canonical firm. firm_id is a 32-char md5 hex (matches the
-- firms[].firm_id values in the recall rows). Sidecar columns carry the post-R5 names
-- (firm_usda/uscg/fda_attributes). Covers: a CPSC firm (no sidecar), single-source firms, and a
-- cross-source firm with two populated sidecars.
-- ---------------------------------------------------------------------------------------------------

drop table if exists mart_firm_profile;

create table mart_firm_profile (
    firm_id              text primary key,
    canonical_name       text    not null,
    normalized_name      text    not null,
    observed_names       jsonb,
    observed_company_ids jsonb,
    alternate_names      jsonb,
    total_recalls        bigint  not null,
    active_recalls       bigint  not null,
    first_recall_at      timestamptz,
    last_recall_at       timestamptz,
    roles                jsonb,
    recalls_by_source    jsonb,
    distinct_products    numeric not null,
    firm_usda_attributes jsonb,
    firm_uscg_attributes jsonb,
    firm_fda_attributes  jsonb
);

create index mart_firm_profile_normalized_name on mart_firm_profile (normalized_name);

insert into mart_firm_profile (
    firm_id, canonical_name, normalized_name, observed_names, observed_company_ids, alternate_names,
    total_recalls, active_recalls, first_recall_at, last_recall_at, roles, recalls_by_source,
    distinct_products, firm_usda_attributes, firm_uscg_attributes, firm_fda_attributes
) values
-- Acme Foods Inc — FDA only, FDA sidecar populated
('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'Acme Foods Inc', 'acme foods', '["Acme Foods Inc", "ACME FOODS"]',
 '["1000000001"]', '["Acme"]', 2, 1, '2026-05-10 12:00:00+00', '2026-05-12 09:00:00+00',
 '["establishment"]', '{"FDA": 2}', 3, null, null,
 '[{"firm_fei_num": 1000000001, "firm_legal_nam": "ACME FOODS INC", "firm_city_nam": "Springfield", "firm_state_cd": "IL", "firm_country_nam": "USA"}]'),
-- Globex Corporation — CPSC only, NO sidecar (CPSC is name-keyed)
('11111111111111111111111111111111', 'Globex Corporation', 'globex', '["Globex Corporation"]',
 '[]', '[]', 1, 0, '2026-06-01 10:00:00+00', '2026-06-01 10:00:00+00',
 '["manufacturer"]', '{"CPSC": 1}', 1, null, null, null),
-- Tyson Foods — USDA only, USDA sidecar populated
('22222222222222222222222222222222', 'Tyson Foods', 'tyson foods', '["Tyson Foods"]',
 '["M12345"]', '[]', 1, 0, '2026-04-15 08:00:00+00', '2026-04-15 08:00:00+00',
 '["establishment"]', '{"USDA": 1}', 1,
 '[{"establishment_id": "M12345", "establishment_name": "TYSON FOODS", "city": "Springdale", "state": "AR", "status_regulated_est": ""}]',
 null, null),
-- Boaty Mfg — USCG only, USCG sidecar populated
('55555555555555555555555555555555', 'Boaty Mfg', 'boaty mfg', '["Boaty Mfg"]',
 '["BMC"]', '[]', 1, 1, '2026-02-10 06:00:00+00', '2026-02-10 06:00:00+00',
 '["manufacturer"]', '{"USCG": 1}', 1, null,
 '[{"mic": "BMC", "company_name": "Boaty Mfg", "city": "Miami", "state": "FL", "status": "Active", "mic_has_prior_holder": false, "prior_holders": []}]',
 null),
-- MultiCorp — CROSS-SOURCE (FDA + USDA), two sidecars populated
('cccccccccccccccccccccccccccccccc', 'MultiCorp LLC', 'multicorp', '["MultiCorp LLC", "Multi Corp"]',
 '["2000000002", "M99999"]', '[]', 2, 1, '2026-01-05 09:00:00+00', '2026-03-01 09:00:00+00',
 '["establishment"]', '{"FDA": 1, "USDA": 1}', 4,
 '[{"establishment_id": "M99999", "establishment_name": "MULTICORP PLANT", "state": "TX"}]',
 null,
 '[{"firm_fei_num": 2000000002, "firm_legal_nam": "MULTICORP LLC", "firm_city_nam": "Austin", "firm_state_cd": "TX"}]');

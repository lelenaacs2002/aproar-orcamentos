-- NÃO é necessário para rodar a V1. É a base prevista para a V2.

create table if not exists orcamento_review_state (
    card_id text primary key,
    review_status text not null default 'pending',
    pending_owner_type text not null default 'engineering',
    pending_reason text,
    last_chase_at timestamptz,
    last_engineer_response_at timestamptz,
    accepted_at timestamptz,
    accepted_by text,
    budget_owner text,
    updated_at timestamptz not null default now()
);

create table if not exists orcamento_event_log (
    id bigserial primary key,
    card_id text not null,
    event_type text not null,
    actor text,
    owner_type text,
    details text,
    trello_action_id text unique,
    occurred_at timestamptz not null default now()
);

create index if not exists idx_orcamento_event_log_card_date
    on orcamento_event_log (card_id, occurred_at desc);

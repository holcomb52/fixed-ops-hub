-- Stellantis warranty audit: one stored manual plus optional RO audit history.
-- Run in Supabase SQL Editor if Warranty Audit cloud save reports a missing table.
-- Safe to re-run. The Streamlit app uses the service_role key, which bypasses RLS.
-- No policies are granted to anon/authenticated.

create table if not exists warranty_manuals (
    id uuid primary key,
    filename text not null,
    title text not null default '',
    page_count integer not null default 0,
    chunk_count integer not null default 0,
    text_characters integer not null default 0,
    is_active boolean not null default true,
    warnings jsonb not null default '[]'::jsonb,
    chunks jsonb not null default '[]'::jsonb,
    uploaded_at timestamptz not null default now(),
    updated_at timestamptz default now()
);

-- One active warranty manual and one active audit guide.
alter table warranty_manuals add column if not exists document_kind text not null default 'warranty_manual';

drop index if exists warranty_manuals_one_active_idx;
create unique index if not exists warranty_manuals_one_active_per_kind_idx
    on warranty_manuals (document_kind)
    where is_active;

create index if not exists warranty_manuals_uploaded_idx
    on warranty_manuals (uploaded_at desc);

create table if not exists warranty_audit_runs (
    id uuid primary key,
    ro_number text,
    source_name text,
    status text not null default 'completed' check (status in ('completed')),
    snapshot jsonb not null,
    finding_count integer not null default 0,
    critical_count integer not null default 0,
    manual_id uuid,
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_warranty_audit_runs_completed
    on warranty_audit_runs (completed_at desc);

-- Pictures for the claim currently being collected. The phone inserts a row
-- as each picture is added so a desktop session can show it immediately.
create table if not exists warranty_claim_live_photos (
    sha text primary key,
    name text not null,
    position integer not null,
    jpeg_b64 text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_warranty_claim_live_photos_position
    on warranty_claim_live_photos (position);

alter table warranty_manuals enable row level security;
alter table warranty_audit_runs enable row level security;
alter table warranty_claim_live_photos enable row level security;

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

-- Only one manual is active. Replacing a manual deactivates the previous row.
create unique index if not exists warranty_manuals_one_active_idx
    on warranty_manuals (is_active)
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

alter table warranty_manuals enable row level security;
alter table warranty_audit_runs enable row level security;

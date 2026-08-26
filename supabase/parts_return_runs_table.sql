-- Parts return allowance plans (Reports → Parts Returns)
-- Run in Supabase SQL Editor if cloud sync reports a missing table.

create table if not exists parts_return_runs (
    id uuid primary key default gen_random_uuid(),
    pay_period text not null,
    status text not null default 'completed' check (status in ('draft', 'completed')),
    snapshot jsonb not null,
    grand_total numeric(12, 2),
    tech_count numeric(10, 2),
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_parts_return_runs_period
    on parts_return_runs (pay_period desc);
create index if not exists idx_parts_return_runs_completed
    on parts_return_runs (completed_at desc);

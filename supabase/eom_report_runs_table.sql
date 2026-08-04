-- Fixed Ops end-of-month controller reports (Reports → EOM Report)
-- Run once in Supabase SQL Editor.

create table if not exists eom_report_runs (
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

create index if not exists idx_eom_report_runs_period
    on eom_report_runs (pay_period desc);
create index if not exists idx_eom_report_runs_completed
    on eom_report_runs (completed_at desc);

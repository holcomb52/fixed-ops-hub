-- CSI / NPS bonus runs (Reports → CSI Bonus)
-- Run in Supabase SQL Editor if cloud sync reports a missing table.

create table if not exists csi_bonus_runs (
    id uuid primary key default gen_random_uuid(),
    pay_period text not null,
    status text not null default 'completed' check (status in ('draft', 'completed')),
    snapshot jsonb not null,
    grand_total numeric(12, 2),
    employee_name text,
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_csi_bonus_runs_period
    on csi_bonus_runs (pay_period desc);
create index if not exists idx_csi_bonus_runs_completed
    on csi_bonus_runs (completed_at desc);

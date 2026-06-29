-- Run once in Supabase if advisor/receptionist payroll cloud backup fails
-- (error: Could not find the table 'public.advisor_payroll_runs')

-- Service advisor payroll runs (Reports → Service Advisor Payroll)
create table if not exists advisor_payroll_runs (
    id uuid primary key default gen_random_uuid(),
    pay_period text not null,
    status text not null default 'completed' check (status in ('draft', 'completed')),
    snapshot jsonb not null,
    grand_total numeric(12, 2),
    advisor_count integer,
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_advisor_payroll_runs_period on advisor_payroll_runs (pay_period desc);
create index if not exists idx_advisor_payroll_runs_completed on advisor_payroll_runs (completed_at desc);

-- Receptionist payroll runs (Reports → Receptionist Payroll)
create table if not exists receptionist_payroll_runs (
    id uuid primary key default gen_random_uuid(),
    pay_period text not null,
    status text not null default 'completed' check (status in ('draft', 'completed')),
    snapshot jsonb not null,
    grand_total numeric(12, 2),
    employee_count integer,
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_receptionist_payroll_runs_period on receptionist_payroll_runs (pay_period desc);
create index if not exists idx_receptionist_payroll_runs_completed on receptionist_payroll_runs (completed_at desc);

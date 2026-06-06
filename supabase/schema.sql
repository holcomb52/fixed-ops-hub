-- Run this in Supabase: SQL Editor → New query → paste → Run

create table if not exists employees (
    id uuid primary key default gen_random_uuid(),
    full_name text not null,
    role text default 'Technician',
    hourly_rate numeric(10, 2) default 0,
    status text default 'active' check (status in ('active', 'inactive')),
    created_at timestamptz default now()
);

create table if not exists pay_periods (
    id uuid primary key default gen_random_uuid(),
    start_date date not null,
    end_date date not null,
    frequency text not null check (frequency in ('Weekly', 'Bi-weekly', 'Semi-monthly', 'Monthly')),
    status text default 'open' check (status in ('open', 'closed', 'processing')),
    created_at timestamptz default now()
);

-- Completed technician payroll runs (Reports → Technician Payroll)
create table if not exists tech_payroll_runs (
    id uuid primary key default gen_random_uuid(),
    pay_period text not null,
    status text not null default 'completed' check (status in ('draft', 'completed')),
    snapshot jsonb not null,
    flag_pdf_filename text,
    flag_pdf_base64 text,
    grand_total numeric(12, 2),
    grand_hours numeric(10, 2),
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_tech_payroll_runs_period on tech_payroll_runs (pay_period desc);
create index if not exists idx_tech_payroll_runs_completed on tech_payroll_runs (completed_at desc);

-- Completed service advisor payroll runs (Reports → Service Advisor Payroll)
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

-- Sample data (optional — remove if you want a blank slate)
insert into employees (full_name, role, hourly_rate) values
    ('Alex Rivera', 'Service Advisor', 28.50),
    ('Jordan Kim', 'Technician', 32.00),
    ('Sam Patel', 'Parts Manager', 30.00)
on conflict do nothing;

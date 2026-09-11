-- Service Advisor daily training logs (Reports → Advisor Training)
-- Run in Supabase SQL Editor if cloud sync reports a missing table.

create table if not exists advisor_training_logs (
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

create index if not exists idx_advisor_training_logs_period
    on advisor_training_logs (pay_period desc);
create index if not exists idx_advisor_training_logs_completed
    on advisor_training_logs (completed_at desc);
create index if not exists idx_advisor_training_logs_employee
    on advisor_training_logs (employee_name);

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

-- Completed receptionist payroll runs (Reports → Receptionist Payroll)
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

-- Live payroll rosters (advisor / technician / receptionist team lists)
create table if not exists payroll_rosters (
    roster_key text primary key,
    data jsonb not null,
    updated_at timestamptz default now()
);

-- Saved warranty ELR analysis runs (Reports → Warranty ELR Analysis)
create table if not exists warranty_labor_runs (
    id uuid primary key default gen_random_uuid(),
    run_label text not null,
    source_name text not null,
    sheet_name text not null,
    status text not null default 'saved' check (status in ('draft', 'saved')),
    snapshot jsonb not null,
    effective_labor_rate numeric(12, 2),
    included_rows integer,
    total_rows integer,
    completed_at timestamptz,
    updated_at timestamptz default now(),
    created_at timestamptz default now()
);

create index if not exists idx_warranty_labor_runs_completed on warranty_labor_runs (completed_at desc);

-- Saved customer-pay labor rate grids (Reports → Labor Rate Grids)
create table if not exists labor_rate_runs (
    id uuid primary key,
    run_label text not null,
    status text not null default 'saved',
    snapshot jsonb not null,
    target_elr numeric,
    strong_avg_elr numeric,
    base_elr numeric,
    strong_lo numeric,
    strong_hi numeric,
    pct_above_target numeric,
    pct_below_target numeric,
    created_at timestamptz default now(),
    completed_at timestamptz,
    updated_at timestamptz default now()
);

create index if not exists labor_rate_runs_completed_at_idx
    on labor_rate_runs (completed_at desc);

-- Warranty Administrator monthly bonus (Reports → Warranty Admin Bonus)
create table if not exists warranty_admin_bonus_runs (
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

create index if not exists idx_warranty_admin_bonus_runs_period
    on warranty_admin_bonus_runs (pay_period desc);
create index if not exists idx_warranty_admin_bonus_runs_completed
    on warranty_admin_bonus_runs (completed_at desc);

-- Fixed Ops end-of-month controller reports (Reports → EOM Report)
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

-- Parts return allowance plans (Reports → Parts Returns)
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

-- Parts stocking plans from 6MS reports (Reports → Parts Stocking)
create table if not exists parts_stocking_runs (
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

create index if not exists idx_parts_stocking_runs_period
    on parts_stocking_runs (pay_period desc);
create index if not exists idx_parts_stocking_runs_completed
    on parts_stocking_runs (completed_at desc);

-- CSI / NPS bonus runs (Reports → CSI Bonus)
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

-- Service Advisor daily training logs (Reports → Advisor Training)
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

-- Stellantis warranty audit: one active warranty manual, one active audit guide,
-- and optional RO audit history.
-- Existing projects can run supabase/warranty_audit_tables.sql instead.
create table if not exists warranty_manuals (
    id uuid primary key,
    filename text not null,
    title text not null default '',
    page_count integer not null default 0,
    chunk_count integer not null default 0,
    text_characters integer not null default 0,
    is_active boolean not null default true,
    document_kind text not null default 'warranty_manual',
    warnings jsonb not null default '[]'::jsonb,
    chunks jsonb not null default '[]'::jsonb,
    uploaded_at timestamptz not null default now(),
    updated_at timestamptz default now()
);

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

create table if not exists warranty_claim_live_photos (
    sha text primary key,
    name text not null,
    position integer not null,
    jpeg_b64 text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_warranty_claim_live_photos_position
    on warranty_claim_live_photos (position);

-- Lock down the Data API. The Streamlit app uses the service_role key, which
-- bypasses RLS. No policies are granted to anon/authenticated, so a leaked
-- publishable/anon key cannot read payroll or saved reports.
-- Existing projects: also run supabase/enable_rls.sql.
alter table employees enable row level security;
alter table pay_periods enable row level security;
alter table tech_payroll_runs enable row level security;
alter table advisor_payroll_runs enable row level security;
alter table receptionist_payroll_runs enable row level security;
alter table payroll_rosters enable row level security;
alter table warranty_labor_runs enable row level security;
alter table labor_rate_runs enable row level security;
alter table warranty_admin_bonus_runs enable row level security;
alter table eom_report_runs enable row level security;
alter table parts_return_runs enable row level security;
alter table parts_stocking_runs enable row level security;
alter table csi_bonus_runs enable row level security;
alter table advisor_training_logs enable row level security;
alter table warranty_manuals enable row level security;
alter table warranty_audit_runs enable row level security;
alter table warranty_claim_live_photos enable row level security;

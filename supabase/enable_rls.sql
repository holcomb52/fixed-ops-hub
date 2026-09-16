-- Run once on an existing Supabase project that was created from an older
-- schema.sql (tables already exist, but RLS was never enabled).
-- Safe to re-run. The Streamlit app must keep using the service_role key.

alter table if exists employees enable row level security;
alter table if exists pay_periods enable row level security;
alter table if exists tech_payroll_runs enable row level security;
alter table if exists advisor_payroll_runs enable row level security;
alter table if exists receptionist_payroll_runs enable row level security;
alter table if exists payroll_rosters enable row level security;
alter table if exists warranty_labor_runs enable row level security;
alter table if exists labor_rate_runs enable row level security;
alter table if exists warranty_admin_bonus_runs enable row level security;
alter table if exists eom_report_runs enable row level security;
alter table if exists parts_return_runs enable row level security;
alter table if exists parts_stocking_runs enable row level security;
alter table if exists csi_bonus_runs enable row level security;
alter table if exists advisor_training_logs enable row level security;

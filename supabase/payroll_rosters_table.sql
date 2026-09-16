-- Run once in Supabase so advisor/tech/receptionist roster edits persist on Streamlit Cloud

create table if not exists payroll_rosters (
    roster_key text primary key,
    data jsonb not null,
    updated_at timestamptz default now()
);

alter table payroll_rosters enable row level security;

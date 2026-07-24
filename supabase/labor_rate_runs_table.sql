-- Optional: cloud sync for Labor Rate grids saved to Reports
-- Run in Supabase SQL Editor if you want these across devices / Streamlit Cloud

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

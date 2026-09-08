-- Run this once in the Supabase project's SQL Editor before the robot
-- brain uses SUPABASE_URL/SUPABASE_KEY. Holds the robot's persisted
-- physical needs (currently just hunger) as a single row, same shape as
-- 001_learned_skills.sql.
create table if not exists robot_needs (
    id text primary key,
    data jsonb not null,
    updated_at timestamptz not null default now()
);

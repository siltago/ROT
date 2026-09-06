-- Run this once in the Supabase project's SQL Editor before the robot
-- brain uses SUPABASE_URL/SUPABASE_KEY. See PROJECT.md / the skills
-- feature notes for the full setup walkthrough.
create table if not exists learned_skills (
    id text primary key,
    name text unique not null,
    data jsonb not null,
    created_at timestamptz not null default now()
);

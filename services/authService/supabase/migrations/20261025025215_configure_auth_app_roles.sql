begin;

-- Keep backfill, uniqueness and initialization atomic with concurrent signups.
lock table auth.users in share row exclusive mode;

do $$
begin
    if exists (
        select 1 from auth.users
        where raw_app_meta_data is not null
          and jsonb_typeof(raw_app_meta_data) <> 'object'
    ) then
        raise exception 'Application metadata must be a JSON object';
    end if;
    if exists (
        select 1 from auth.users
        where raw_app_meta_data ? 'app_role'
          and coalesce(raw_app_meta_data ->> 'app_role', '')
              not in ('cliente', 'administrador')
    ) then
        raise exception 'Review existing unknown application roles before migrating';
    end if;
    if exists (
        select 1 from auth.users
        where raw_app_meta_data ->> 'app_role' = 'administrador'
          and email_confirmed_at is null
    ) then
        raise exception 'An administrator must have a confirmed email';
    end if;
end;
$$;

-- Preserve provider metadata and any administrator assigned beforehand.
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
    || jsonb_build_object('app_role', 'cliente')
where not (coalesce(raw_app_meta_data, '{}'::jsonb) ? 'app_role');

-- Supabase Cloud restricts indexes on managed auth tables.
-- A private singleton row provides concurrency-safe uniqueness in our own schema.
create table integration.auth_admin_assignment (
    singleton boolean primary key default true check (singleton),
    user_id uuid not null unique references auth.users(id) on delete cascade
);
alter table integration.auth_admin_assignment enable row level security;
revoke all on table integration.auth_admin_assignment
    from public, anon, authenticated, service_role, supabase_auth_admin;

-- Bootstrap the guardrail from protected metadata; two existing admins fail atomically.
insert into integration.auth_admin_assignment (singleton, user_id)
select true, id from auth.users
where raw_app_meta_data ->> 'app_role' = 'administrador';

create function integration.enforce_auth_app_role()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    if tg_op = 'INSERT' then
        if new.raw_app_meta_data is not null
           and jsonb_typeof(new.raw_app_meta_data) <> 'object' then
            raise exception using errcode = '23514',
                message = 'Application metadata must be a JSON object';
        end if;
        -- Signup never grants administrator privileges, including Admin API signup.
        new.raw_app_meta_data = coalesce(new.raw_app_meta_data, '{}'::jsonb)
            || jsonb_build_object('app_role', 'cliente');
    else
        if jsonb_typeof(new.raw_app_meta_data) is distinct from 'object'
           or coalesce(new.raw_app_meta_data ->> 'app_role', '')
              not in ('cliente', 'administrador') then
            raise exception using errcode = '23514',
                message = 'Invalid application role';
        end if;
        if new.raw_app_meta_data ->> 'app_role' = 'administrador'
           and new.email_confirmed_at is null then
            raise exception using errcode = '23514',
                message = 'An administrator must have a confirmed email';
        end if;
        if new.raw_app_meta_data ->> 'app_role' = 'administrador' then
            insert into integration.auth_admin_assignment as assignment
                (singleton, user_id) values (true, new.id)
            on conflict (singleton) do update
                set user_id = excluded.user_id
                where assignment.user_id = excluded.user_id;
            if not found then
                raise exception using errcode = '23505',
                    message = 'Another administrator already exists';
            end if;
        else
            delete from integration.auth_admin_assignment where user_id = new.id;
        end if;
    end if;
    return new;
end;
$$;

revoke all on function integration.enforce_auth_app_role()
    from public, anon, authenticated, service_role;
grant execute on function integration.enforce_auth_app_role()
    to supabase_auth_admin;

create trigger auth_users_enforce_app_role
    before insert or update of raw_app_meta_data on auth.users
    for each row execute function integration.enforce_auth_app_role();

commit;

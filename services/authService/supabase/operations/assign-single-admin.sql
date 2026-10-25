begin;

do $$
declare
    target_id uuid := 'a55772da-a5f6-475f-b2d3-d9b1db955d9b'::uuid;
    target_email_confirmed timestamptz;
begin
    select email_confirmed_at into target_email_confirmed
    from auth.users where id = target_id for update;
    if not found then
        raise exception 'The target identity does not exist';
    end if;
    if target_email_confirmed is null then
        raise exception 'Confirm the target email before granting administrator';
    end if;
    if exists (
        select 1 from auth.users
        where id <> target_id
          and raw_app_meta_data ->> 'app_role' = 'administrador'
    ) then
        raise exception 'Another administrator already exists';
    end if;

    update auth.users
    set raw_app_meta_data = raw_app_meta_data
        || jsonb_build_object('app_role', 'administrador')
    where id = target_id;
    -- The private singleton constraint also protects concurrent assignments.
end;
$$;

commit;

select id, raw_app_meta_data ->> 'app_role' as app_role
from auth.users
where raw_app_meta_data ->> 'app_role' = 'administrador';

create schema if not exists integration;

revoke all on schema integration from public;
revoke all on schema integration from anon;
revoke all on schema integration from authenticated;
revoke all on schema integration from service_role;


create table integration.auth_outbox (
    id uuid primary key default gen_random_uuid(),

    agregado_id uuid not null,

    tipo text not null,

    version_agregado integer not null default 1,

    datos jsonb not null,

    ocurrido_en timestamptz not null default now(),

    publicado_en timestamptz,

    intentos integer not null default 0,

    proximo_intento_en timestamptz,

    constraint auth_outbox_tipo_not_blank
        check (btrim(tipo) <> ''),

    constraint auth_outbox_version_agregado_positive
        check (version_agregado > 0),

    constraint auth_outbox_intentos_nonnegative
        check (intentos >= 0),

    constraint auth_outbox_datos_object
        check (jsonb_typeof(datos) = 'object')
);


create unique index auth_outbox_user_registered_once_idx
    on integration.auth_outbox (
        agregado_id,
        version_agregado
    )
    where tipo = 'identity.user.registered.v1';


create index auth_outbox_pending_idx
    on integration.auth_outbox (ocurrido_en)
    where publicado_en is null;


revoke all on table integration.auth_outbox from public;
revoke all on table integration.auth_outbox from anon;
revoke all on table integration.auth_outbox from authenticated;
revoke all on table integration.auth_outbox from service_role;
revoke all on table integration.auth_outbox from supabase_auth_admin;


create function integration.enqueue_auth_user_registered()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
    insert into integration.auth_outbox (
        agregado_id,
        tipo,
        version_agregado,
        datos,
        ocurrido_en
    )
    values (
        new.id,
        'identity.user.registered.v1',
        1,
        jsonb_build_object(
            'userId',
            new.id,
            'initialContactEmail',
            new.email
        ),
        coalesce(new.created_at, now())
    );

    return new;
end;
$$;


revoke all
    on function integration.enqueue_auth_user_registered()
    from public;

revoke all
    on function integration.enqueue_auth_user_registered()
    from anon;

revoke all
    on function integration.enqueue_auth_user_registered()
    from authenticated;

revoke all
    on function integration.enqueue_auth_user_registered()
    from service_role;


grant usage
    on schema integration
    to supabase_auth_admin;

grant execute
    on function integration.enqueue_auth_user_registered()
    to supabase_auth_admin;


create trigger auth_users_enqueue_registration_outbox
after insert on auth.users
for each row
when (new.email is not null)
execute function integration.enqueue_auth_user_registered();

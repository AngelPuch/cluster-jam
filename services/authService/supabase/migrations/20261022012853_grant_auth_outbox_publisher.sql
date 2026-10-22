do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'auth_outbox_publisher') then
        create role auth_outbox_publisher nologin;
    end if;
end;
$$;

revoke all on schema integration from auth_outbox_publisher;
revoke all on table integration.auth_outbox from auth_outbox_publisher;
grant usage on schema integration to auth_outbox_publisher;
grant select on table integration.auth_outbox to auth_outbox_publisher;
grant update (publicado_en, intentos, proximo_intento_en)
    on integration.auth_outbox to auth_outbox_publisher;

create index auth_outbox_due_registration_idx
    on integration.auth_outbox (
        coalesce(proximo_intento_en, ocurrido_en), ocurrido_en, id
    )
    where publicado_en is null and tipo = 'identity.user.registered.v1';

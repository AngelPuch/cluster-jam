begin;

alter table integration.auth_outbox
    add column bloqueado_en timestamptz,
    add column ultimo_error_codigo text,
    add constraint auth_outbox_blocked_state_valid check (
        bloqueado_en is null
        or (
            publicado_en is null
            and coalesce(ultimo_error_codigo, '') = 'REGISTRATION_EVENT_INVALID'
        )
    );

grant update (bloqueado_en, ultimo_error_codigo)
    on integration.auth_outbox to auth_outbox_publisher;

drop index integration.auth_outbox_due_registration_idx;

create index auth_outbox_due_registration_idx
    on integration.auth_outbox (
        coalesce(proximo_intento_en, ocurrido_en), ocurrido_en, id
    )
    where publicado_en is null
      and bloqueado_en is null
      and tipo = 'identity.user.registered.v1';

commit;


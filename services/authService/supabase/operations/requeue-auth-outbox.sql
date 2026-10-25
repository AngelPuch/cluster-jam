begin;

do $$
declare
    -- Set the blocked event UUID only after correcting its underlying cause.
    target_event_id uuid := null;
begin
    if target_event_id is null then
        raise exception 'Set target_event_id to the blocked event UUID before running this operation';
    end if;

    update integration.auth_outbox
    set bloqueado_en = null,
        ultimo_error_codigo = null,
        proximo_intento_en = clock_timestamp()
    where id = target_event_id
      and publicado_en is null
      and bloqueado_en is not null;

    if not found then
        raise exception 'The event does not exist or is not blocked and unpublished';
    end if;

    raise notice 'Registration outbox event % queued for retry', target_event_id;
end;
$$;

commit;

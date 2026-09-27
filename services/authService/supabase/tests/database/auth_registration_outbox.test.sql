begin;

create extension if not exists pgtap with schema extensions;

set local search_path = extensions, public;

select plan(32);


select has_schema(
    'integration',
    'integration schema should exist'
);


select has_table(
    'integration',
    'auth_outbox',
    'auth_outbox table should exist'
);


select col_is_pk(
    'integration',
    'auth_outbox',
    'id',
    'id should be the primary key'
);


select has_column(
    'integration',
    'auth_outbox',
    'agregado_id',
    'auth_outbox should have agregado_id'
);


select has_column(
    'integration',
    'auth_outbox',
    'tipo',
    'auth_outbox should have tipo'
);


select has_column(
    'integration',
    'auth_outbox',
    'version_agregado',
    'auth_outbox should have version_agregado'
);


select has_column(
    'integration',
    'auth_outbox',
    'datos',
    'auth_outbox should have datos'
);


select has_column(
    'integration',
    'auth_outbox',
    'ocurrido_en',
    'auth_outbox should have ocurrido_en'
);


select has_column(
    'integration',
    'auth_outbox',
    'publicado_en',
    'auth_outbox should have publicado_en'
);


select has_column(
    'integration',
    'auth_outbox',
    'intentos',
    'auth_outbox should have intentos'
);


select has_column(
    'integration',
    'auth_outbox',
    'proximo_intento_en',
    'auth_outbox should have proximo_intento_en'
);


select has_index(
    'integration',
    'auth_outbox',
    'auth_outbox_user_registered_once_idx',
    'registration events should have a uniqueness index'
);


select has_index(
    'integration',
    'auth_outbox',
    'auth_outbox_pending_idx',
    'pending events should have an index'
);


select has_function(
    'integration',
    'enqueue_auth_user_registered',
    array[]::name[],
    'registration outbox trigger function should exist'
);


select is_definer(
    'integration',
    'enqueue_auth_user_registered',
    array[]::name[],
    'registration trigger function should be security definer'
);


select has_trigger(
    'auth',
    'users',
    'auth_users_enqueue_registration_outbox',
    'auth.users should have the registration outbox trigger'
);


select trigger_is(
    'auth',
    'users',
    'auth_users_enqueue_registration_outbox',
    'integration',
    'enqueue_auth_user_registered',
    'auth.users trigger should call the outbox function'
);


create temporary table test_auth_users (
    id uuid primary key,
    email text,
    created_at timestamptz not null
);


create trigger test_auth_users_outbox
after insert on test_auth_users
for each row
when (new.email is not null)
execute function integration.enqueue_auth_user_registered();


insert into test_auth_users (
    id,
    email,
    created_at
)
values (
    '11111111-1111-4111-8111-111111111111',
    'usuario@example.com',
    '2026-09-26T20:00:00Z'
);


select results_eq(
    $$
        select tipo
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values ('identity.user.registered.v1'::text)
    $$,
    'trigger should create the registered event type'
);


select results_eq(
    $$
        select version_agregado
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values (1::integer)
    $$,
    'registered event should use aggregate version 1'
);


select results_eq(
    $$
        select datos ->> 'userId'
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values ('11111111-1111-4111-8111-111111111111'::text)
    $$,
    'payload should contain userId'
);


select results_eq(
    $$
        select datos ->> 'initialContactEmail'
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values ('usuario@example.com'::text)
    $$,
    'payload should contain initialContactEmail'
);


select results_eq(
    $$
        select intentos
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values (0::integer)
    $$,
    'new events should start with zero attempts'
);


select results_eq(
    $$
        select publicado_en is null
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values (true)
    $$,
    'new events should start unpublished'
);


select results_eq(
    $$
        select ocurrido_en
        from integration.auth_outbox
        where agregado_id =
            '11111111-1111-4111-8111-111111111111'::uuid
    $$,
    $$
        values ('2026-09-26T20:00:00Z'::timestamptz)
    $$,
    'event occurrence time should match user creation time'
);


select results_eq(
    $$
        select count(*)::integer
        from jsonb_object_keys((
            select datos
            from integration.auth_outbox
            where agregado_id = 
                '11111111-1111-4111-8111-111111111111'::uuid
        ));
    $$,
    $$
        values (2::integer)
    $$,
    'registration payload should contain only two fields'
);


insert into test_auth_users (
    id,
    email,
    created_at
)
values (
    '22222222-2222-4222-8222-222222222222',
    null,
    '2026-09-26T20:01:00Z'
);


select is(
    (
        select count(*)
        from integration.auth_outbox
        where agregado_id =
            '22222222-2222-4222-8222-222222222222'::uuid
    ),
    0::bigint,
    'users without email should not create a registration event'
);


savepoint atomicity_test;


insert into test_auth_users (
    id,
    email,
    created_at
)
values (
    '33333333-3333-4333-8333-333333333333',
    'rollback@example.com',
    '2026-09-26T20:02:00Z'
);


rollback to savepoint atomicity_test;


select is(
    (
        select count(*)
        from integration.auth_outbox
        where agregado_id =
            '33333333-3333-4333-8333-333333333333'::uuid
    ),
    0::bigint,
    'outbox insert should roll back with the source transaction'
);


select ok(
    not has_schema_privilege(
        'anon',
        'integration',
        'USAGE'
    ),
    'anon should not access integration schema'
);


select ok(
    not has_schema_privilege(
        'authenticated',
        'integration',
        'USAGE'
    ),
    'authenticated should not access integration schema'
);


select ok(
    not has_schema_privilege(
        'service_role',
        'integration',
        'USAGE'
    ),
    'service_role should not access integration schema directly'
);


select ok(
    has_schema_privilege(
        'supabase_auth_admin',
        'integration',
        'USAGE'
    ),
    'supabase_auth_admin should be able to resolve the trigger function'
);


select ok(
    has_function_privilege(
        'supabase_auth_admin',
        'integration.enqueue_auth_user_registered()',
        'EXECUTE'
    ),
    'supabase_auth_admin should be able to execute the trigger function'
);


select * from finish();

rollback;

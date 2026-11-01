begin;
set local request.jwt.claims='{}';
set local request.jwt.claim.sub='';
set local role anon;
do $$ begin
  if has_table_privilege(current_user,'public.to_pallets','SELECT')
     or has_function_privilege(current_user,'public.transport_operator(uuid,text,jsonb)','EXECUTE') then
    raise exception 'Unexpected anonymous access';
  end if;
  begin
    perform public.transport_driver(repeat('0',64),'get','{}');
    raise exception 'Invalid driver token was accepted';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
set local role authenticated;
do $$ begin
  if exists(select 1 from public.to_workspaces) then
    raise exception 'Workspace visible without membership';
  end if;
  begin
    perform public.transport_operator('00000000-0000-0000-0000-000000000000','create_manifest','{}');
    raise exception 'Unauthorised operator call accepted';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
select 'Access checks passed' as verification,
  (select count(*) from public.to_destinations) as destination_presets,
  (select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname in ('public','transport_private') and c.relkind='r'
      and (c.relname like 'to_%' or c.relname='driver_links') and c.relrowsecurity) as protected_tables;
rollback;

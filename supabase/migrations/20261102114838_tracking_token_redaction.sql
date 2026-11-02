create or replace function public.transport_tracking(p_workspace uuid,p_query text default '') returns jsonb
language sql stable security invoker set search_path='' as $$
 select coalesce(jsonb_agg(r),'[]') from (
  select a.kind,a.reference_id as id,a.revision,a.created_at,a.snapshot-'online'||case when a.snapshot->'online' is not null then jsonb_build_object('online',jsonb_build_object('id',a.snapshot->'online'->>'id')) else '{}'::jsonb end as snapshot,
   m.status as shipment_status,m.collected_at,m.delivered_at,m.id as manifest_id,
   m.driver_name,m.vehicle,
   (select coalesce(jsonb_agg(jsonb_build_object('action',e.action,'at',e.at)),'[]') from public.to_events e where e.workspace_id=a.workspace_id and e.reference_id=coalesce(m.id,a.reference_id)) as events
  from (
   select workspace_id,kind,reference_id,revision,snapshot,created_at from public.to_archive_documents
   union all
   select d.workspace_id,case when d.kind='manifest' then 'load' else d.kind end,d.reference_id,d.revision,d.snapshot,d.created_at from public.to_documents d
   where not exists(select 1 from public.to_archive_documents a where a.workspace_id=d.workspace_id and a.reference_id=d.reference_id and a.revision=d.revision)
  ) a
  left join public.to_manifests m on m.workspace_id=a.workspace_id and m.id=coalesce(a.snapshot->'online'->>'id',case when a.kind='load' then a.reference_id end,
   (select i.manifest_id from public.to_manifest_pallets i join public.to_manifests z on z.workspace_id=i.workspace_id and z.id=i.manifest_id where i.workspace_id=a.workspace_id and i.pallet_id=case when a.kind='pallet' then a.reference_id else a.snapshot->>'palletId' end order by z.created_at desc limit 1))
  where a.workspace_id=p_workspace and (btrim(p_query)='' or strpos(lower(a.reference_id||' '||a.snapshot::text),lower(btrim(p_query)))>0)
  order by a.created_at desc,a.reference_id limit 200
 ) r
$$;
revoke all on function public.transport_tracking(uuid,text) from public,anon;
grant execute on function public.transport_tracking(uuid,text) to authenticated;

create policy deny_direct_access on transport_private.publisher_devices to anon,authenticated using(false) with check(false);

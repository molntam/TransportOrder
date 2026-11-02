create table transport_private.publisher_devices (
 id uuid primary key default gen_random_uuid(), workspace_id uuid not null references public.to_workspaces(id),
 owner_id uuid not null references auth.users(id), label text not null check(length(label) between 1 and 120),
 token_hash text not null unique, created_at timestamptz not null default now(),
 expires_at timestamptz not null default now()+interval '1 year', revoked_at timestamptz
);
alter table transport_private.publisher_devices enable row level security;
revoke all on transport_private.publisher_devices from public,anon,authenticated;
create index to_devices_workspace on transport_private.publisher_devices(workspace_id,owner_id);
create table public.to_archive_documents (
 workspace_id uuid not null references public.to_workspaces(id), kind text not null check(kind in ('form','pallet','load')),
 reference_id text not null, revision integer not null check(revision>0), snapshot jsonb not null,
 created_at timestamptz not null default now(), primary key(workspace_id,kind,reference_id,revision)
);
alter table public.to_archive_documents enable row level security;
grant select on public.to_archive_documents to authenticated;
create policy member_read on public.to_archive_documents for select to authenticated
 using (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

create function transport_private.pair_device(w uuid,label text, revoke_id uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare token text; device uuid;
begin
 if auth.uid() is null or not transport_private.has_role(w,array['admin','operator']) then raise exception 'Operator access required' using errcode='42501'; end if;
 if revoke_id is not null then
  update transport_private.publisher_devices set revoked_at=now() where id=revoke_id and workspace_id=w and owner_id=auth.uid();
  return jsonb_build_object('revoked',found);
 end if;
 if btrim(label)='' then
  return (select coalesce(jsonb_agg(jsonb_build_object('id',id,'label',publisher_devices.label,'expiresAt',expires_at,'revokedAt',revoked_at)),'[]') from transport_private.publisher_devices where workspace_id=w and owner_id=auth.uid());
 end if;
 token:=encode(extensions.gen_random_bytes(32),'hex');
 insert into transport_private.publisher_devices(workspace_id,owner_id,label,token_hash)
 values(w,auth.uid(),left(btrim(label),120),encode(extensions.digest(token,'sha256'),'hex')) returning id into device;
 return jsonb_build_object('id',device,'token',token,'expiresInDays',365);
end $$;
create function public.transport_pair_device(p_workspace uuid,p_label text,p_revoke_id uuid default null) returns jsonb
language sql security invoker set search_path='' as $$select transport_private.pair_device(p_workspace,p_label,p_revoke_id)$$;
revoke all on function transport_private.pair_device(uuid,text,uuid),public.transport_pair_device(uuid,text,uuid) from public,anon;
grant execute on function transport_private.pair_device(uuid,text,uuid),public.transport_pair_device(uuid,text,uuid) to authenticated;

create function transport_private.device_api(token text,action text,payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d transport_private.publisher_devices; result jsonb; previous_sub text; tbl text; snap jsonb; existing jsonb;
begin
 if token is null or token !~ '^[a-f0-9]{64}$' then raise exception 'Invalid workstation pairing' using errcode='42501'; end if;
 select * into d from transport_private.publisher_devices where token_hash=encode(extensions.digest(token,'sha256'),'hex') and revoked_at is null and expires_at>now();
 if d.id is null then raise exception 'Workstation pairing expired or revoked' using errcode='42501'; end if;
 previous_sub:=current_setting('request.jwt.claim.sub',true);
 perform set_config('request.jwt.claim.sub',d.owner_id::text,true);
 if not transport_private.has_role(d.workspace_id,array['admin','operator']) then raise exception 'Device owner no longer has operator access' using errcode='42501'; end if;
 if octet_length(payload::text)>20000000 then raise exception 'Oversized payload'; end if;
 if action='read_records' then
  tbl:=payload->>'table';
  if tbl not in ('to_pallets','to_documents','to_manifests','to_manifest_pallets') then raise exception 'Device read is not allowed'; end if;
  execute format('select coalesce(jsonb_agg(r),''[]'') from (select * from public.%I where workspace_id=$1 and to_jsonb(%I) @> $2 order by to_jsonb(%I)::text limit 1000 offset $3) r',tbl,tbl,tbl)
   into result using d.workspace_id,coalesce(payload->'filters','{}'),greatest(0,coalesce((payload->>'offset')::integer,0));
 elsif action='archive_document' then
  snap:=payload->'snapshot';
  if jsonb_typeof(snap)<>'object' then raise exception 'Document snapshot required'; end if;
  select snapshot into existing from public.to_archive_documents where workspace_id=d.workspace_id and kind=payload->>'kind' and reference_id=payload->>'id' and revision=(payload->>'revision')::integer;
  if existing is not null and existing-'online' is distinct from snap-'online' then raise exception 'Archived document revision is immutable'; end if;
  insert into public.to_archive_documents(workspace_id,kind,reference_id,revision,snapshot)
   values(d.workspace_id,payload->>'kind',payload->>'id',(payload->>'revision')::integer,snap) on conflict (workspace_id,kind,reference_id,revision) do update set snapshot=case when to_archive_documents.snapshot->'online' is null then excluded.snapshot else to_archive_documents.snapshot end;
  result:='{"archived":true}';
 elsif action in ('save_pallet','create_manifest','rotate_driver_link') then
  result:=transport_private.operator_api(d.workspace_id,action,payload);
 else raise exception 'Device action is not allowed'; end if;
 perform set_config('request.jwt.claim.sub',coalesce(previous_sub,''),true);
 return result;
end $$;
create function public.transport_device(p_token text,p_action text,p_payload jsonb default '{}') returns jsonb
language sql security invoker set search_path='' as $$select transport_private.device_api(p_token,p_action,p_payload)$$;
revoke all on function transport_private.device_api(text,text,jsonb),public.transport_device(text,text,jsonb) from public;
grant execute on function transport_private.device_api(text,text,jsonb),public.transport_device(text,text,jsonb) to anon,authenticated;

create function public.transport_tracking(p_workspace uuid,p_query text default '') returns jsonb
language sql stable security invoker set search_path='' as $$
 select coalesce(jsonb_agg(r),'[]') from (
  select a.kind,a.reference_id as id,a.revision,a.created_at,a.snapshot,
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

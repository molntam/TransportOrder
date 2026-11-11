alter table public.to_manifests add column receiver_name text not null default '';
update public.to_manifests m set receiver_name=coalesce((select e.detail->>'receiver' from public.to_events e where e.workspace_id=m.workspace_id and e.reference_id=m.id and e.action='Delivery confirmed' order by e.at desc limit 1),'') where m.delivered_at is not null;

create function transport_private.safe_snapshot(value jsonb) returns jsonb
language plpgsql immutable security invoker set search_path='' as $$
declare result jsonb; item record;
begin
 if jsonb_typeof(value)='object' then
  result:='{}';
  for item in select key,val from jsonb_each(value) as x(key,val) loop
   if item.key not in ('handoffToken','handoffPublished','driverToken','url','versions') then
    result:=result||jsonb_build_object(item.key,transport_private.safe_snapshot(item.val));
   end if;
  end loop;
  return result;
 elsif jsonb_typeof(value)='array' then
  return (select coalesce(jsonb_agg(transport_private.safe_snapshot(x)),'[]') from jsonb_array_elements(value) x);
 end if;
 return value;
end $$;
revoke all on function transport_private.safe_snapshot(jsonb) from public,anon;
grant execute on function transport_private.safe_snapshot(jsonb) to authenticated;

create table public.to_department_orders (
 workspace_id uuid not null references public.to_workspaces(id), id text not null check(id ~ '^TO-[A-Z0-9-]{1,64}$'),
 department_name text not null check(length(btrim(department_name)) between 1 and 200),
 department_location text not null check(length(btrim(department_location)) between 1 and 200),
 snapshot jsonb not null check(jsonb_typeof(snapshot)='object'),
 created_at timestamptz not null default now(), received_at timestamptz, received_by uuid references auth.users(id),
 pallet_id text, receive_request text, primary key(workspace_id,id),
 foreign key(workspace_id,pallet_id) references public.to_pallets(workspace_id,id)
);
alter table public.to_department_orders enable row level security;
revoke all on public.to_department_orders from public,anon,authenticated;
grant select on public.to_department_orders to authenticated;
create policy member_read on public.to_department_orders for select to authenticated using(transport_private.has_role(workspace_id,array['admin','operator','viewer']));
create index to_department_orders_recent on public.to_department_orders(workspace_id,created_at desc);
create index to_department_orders_receiver on public.to_department_orders(received_by) where received_by is not null;
create index to_department_orders_pallet on public.to_department_orders(workspace_id,pallet_id) where pallet_id is not null;

create table transport_private.handoff_links (
 token_hash text primary key check(token_hash ~ '^[a-f0-9]{64}$'), workspace_id uuid not null, form_id text not null,
 created_at timestamptz not null default now(),
 foreign key(workspace_id,form_id) references public.to_department_orders(workspace_id,id), unique(workspace_id,form_id)
);
alter table transport_private.handoff_links enable row level security;
revoke all on transport_private.handoff_links from public,anon,authenticated;
create policy deny_direct_access on transport_private.handoff_links to anon,authenticated using(false) with check(false);

create or replace function transport_private.driver_api(p_token text,p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare link transport_private.driver_links; m public.to_manifests; p public.to_pallets;
 i public.to_manifest_pallets; code text; parts text[]; total integer; loaded integer; n integer;
 v_reason text:=btrim(coalesce(p_payload->>'reason','')); duplicate boolean:=false;
begin
 if jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>20000 then raise exception 'Invalid or oversized driver payload'; end if;
 -- Driver calls use a scoped bearer capability instead of requiring a driver account.
 if p_token is null or p_token !~ '^[0-9a-f]{64}$' then raise exception 'Invalid or expired driver link' using errcode='42501'; end if;
 select * into link from transport_private.driver_links where token_hash=encode(extensions.digest(p_token,'sha256'),'hex') and revoked_at is null and expires_at>now();
 if link.token_hash is null then raise exception 'Invalid or expired driver link' using errcode='42501'; end if;
 perform 1 from public.to_workspaces where id=link.workspace_id for update;
 -- Recheck after the workspace lock so rotation/cancellation wins over stale requests.
 if not exists(select 1 from transport_private.driver_links where token_hash=link.token_hash and revoked_at is null and expires_at>now()) then
  raise exception 'Invalid or expired driver link' using errcode='42501';
 end if;
 select * into m from public.to_manifests where workspace_id=link.workspace_id and id=link.manifest_id;
 if m.revision<>link.manifest_revision or m.status='cancelled' then raise exception 'Superseded manifest'; end if;
 if p_action in ('confirm_pickup','confirm_delivery','unscan') and p_payload ? 'expectedRowVersion' and m.row_version is distinct from (p_payload->>'expectedRowVersion')::bigint then raise exception 'Manifest changed; refresh first' using errcode='40001'; end if;
 if p_action='scan' then
  if m.status<>'ready' then raise exception 'Pickup is already closed'; end if;
  code:=coalesce(p_payload->>'code',''); parts:=regexp_match(code,'^TO:PALLET:(P-[A-Z0-9-]{1,64}):([0-9]{1,9})$');
  if parts is null then raise exception 'Scan a TransportOrder pallet QR code'; end if;
  select * into p from public.to_pallets where workspace_id=m.workspace_id and id=parts[1];
  if p.id is not null and transport_private.building_key(p.destination->>'building')<>transport_private.building_key(m.building) then
   raise exception 'Wrong destination: pallet is for %, not %',p.destination->>'building',m.building;
  end if;
  select * into i from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id and pallet_id=parts[1];
  if i.pallet_id is null then raise exception 'Pallet is not on this manifest'; end if;
  if p.status<>'finalised' or p.revision<>parts[2]::integer or i.pallet_revision<>p.revision or p.collected_at is not null then raise exception 'Superseded or already collected pallet'; end if;
  duplicate:=i.scanned_at is not null;
  if not duplicate then
   update public.to_manifest_pallets set scanned_at=now() where workspace_id=m.workspace_id and manifest_id=m.id and pallet_id=p.id;
   perform transport_private.record_event(m.workspace_id,'Pallet scanned',m.id,'driver',jsonb_build_object('palletId',p.id));
  end if;
 elsif p_action='unscan' then
  if m.status<>'ready' or v_reason='' then raise exception 'Only open loading scans can be removed, with a reason'; end if;
  update public.to_manifest_pallets set scanned_at=null where workspace_id=m.workspace_id and manifest_id=m.id and pallet_id=p_payload->>'palletId' and scanned_at is not null;
  get diagnostics n=row_count;
  if n<>1 then raise exception 'Choose a scanned pallet from this manifest'; end if;
  perform transport_private.record_event(m.workspace_id,'Pallet unloaded',m.id,'driver',jsonb_build_object('palletId',p_payload->>'palletId','reason',v_reason));
 elsif p_action='confirm_pickup' then
  if m.status<>'ready' then raise exception 'Pickup is already closed'; end if;
  select count(*),count(scanned_at) into total,loaded from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id;
  if loaded=0 or (loaded<total and v_reason='') then raise exception 'Scan at least one pallet and explain any partial pickup'; end if;
  if length(btrim(coalesce(p_payload->>'driver',''))) not between 1 and 200 or length(btrim(coalesce(p_payload->>'vehicle',''))) not between 1 and 200 then raise exception 'Driver name and vehicle registration are required'; end if;
  if exists(select 1 from public.to_manifest_pallets x join public.to_pallets y on y.workspace_id=x.workspace_id and y.id=x.pallet_id
    where x.workspace_id=m.workspace_id and x.manifest_id=m.id and x.scanned_at is not null
    and (y.status<>'finalised' or y.revision<>x.pallet_revision or y.collected_at is not null)) then raise exception 'A scanned pallet has changed'; end if;
  update public.to_pallets x set collected_at=now(),row_version=row_version+1,updated_at=now() where x.workspace_id=m.workspace_id
   and exists(select 1 from public.to_manifest_pallets y where y.workspace_id=x.workspace_id and y.pallet_id=x.id and y.manifest_id=m.id and y.scanned_at is not null);
  update public.to_manifest_pallets set collected_at=case when scanned_at is not null then now() end,released_at=now() where workspace_id=m.workspace_id and manifest_id=m.id;
  update public.to_manifests set status=case when loaded=total then 'collected' else 'partial' end,driver_name=btrim(p_payload->>'driver'),vehicle=btrim(p_payload->>'vehicle'),reason=left(v_reason,1000),collected_at=now() where workspace_id=m.workspace_id and id=m.id;
  perform transport_private.record_event(m.workspace_id,'Pickup confirmed',m.id,'driver',jsonb_build_object('loaded',loaded,'planned',total,'driver',p_payload->>'driver','vehicle',p_payload->>'vehicle','reason',left(v_reason,1000)));
 elsif p_action='confirm_delivery' then
  if m.status not in ('collected','partial') then raise exception 'Confirm pickup before delivery'; end if;
  if transport_private.building_key(p_payload->>'building') is distinct from transport_private.building_key(m.building)
   or length(btrim(coalesce(p_payload->>'receiver',''))) not between 1 and 200 then raise exception 'Confirm the matching destination building and receiver name'; end if;
  update public.to_pallets x set delivered_at=now(),row_version=row_version+1,updated_at=now() where x.workspace_id=m.workspace_id
   and exists(select 1 from public.to_manifest_pallets y where y.workspace_id=x.workspace_id and y.pallet_id=x.id and y.manifest_id=m.id and y.collected_at is not null);
  update public.to_manifest_pallets set delivered_at=now() where workspace_id=m.workspace_id and manifest_id=m.id and collected_at is not null;
  update public.to_manifests set status='delivered',receiver_name=btrim(p_payload->>'receiver'),delivered_at=now() where workspace_id=m.workspace_id and id=m.id;
  perform transport_private.record_event(m.workspace_id,'Delivery confirmed',m.id,'driver',jsonb_build_object('building',m.building,'receiver',p_payload->>'receiver'));
 elsif p_action<>'get' then raise exception 'Unknown driver action';
 end if;
 if p_action<>'get' and not duplicate then
  update public.to_manifests set row_version=row_version+1,updated_at=now() where workspace_id=m.workspace_id and id=m.id;
 end if;
 return (select jsonb_build_object('id',x.id,'revision',x.revision,'rowVersion',x.row_version,'building',x.building,'status',x.status,
   'driver',x.driver_name,'vehicle',x.vehicle,'reason',x.reason,'receiver',x.receiver_name,
   'leftBehindCount',(select count(*) from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id and released_at is not null and collected_at is null),
   'releasedPallets',(select coalesce(jsonb_agg(jsonb_build_object('id',pallet_id,'releasedAt',released_at,'reason',x.reason)),'[]') from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id and released_at is not null and collected_at is null),
   'createdAt',x.created_at,'collectedAt',x.collected_at,'deliveredAt',x.delivered_at,'duplicate',duplicate,
   'plannedCount',(select count(*) from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id),
   'scannedCount',(select count(*) from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id and scanned_at is not null),
   'pallets',(select coalesce(jsonb_agg(jsonb_build_object('id',j.pallet_id,'revision',j.pallet_revision,'scannedAt',j.scanned_at,'collectedAt',j.collected_at,'deliveredAt',j.delivered_at,
     'destination',j.snapshot->'destination','forms',(select jsonb_agg(jsonb_build_object('id',f->>'id','lines',(select jsonb_agg(jsonb_build_object('dn',l->>'dn','hu',l->>'hu','qty',l->>'qty')) from jsonb_array_elements(f->'lines') l))) from jsonb_array_elements(j.snapshot->'forms') f)) order by j.pallet_id),'[]')
     from public.to_manifest_pallets j where j.workspace_id=m.workspace_id and j.manifest_id=m.id and (x.status='ready' or j.collected_at is not null))) from public.to_manifests x where x.workspace_id=m.workspace_id and x.id=m.id);
end $$;

create function transport_private.department_api(w uuid, action text, payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.to_department_orders; h transport_private.handoff_links; snap jsonb; f jsonb; line jsonb; p jsonb; result jsonb;
 token text:=payload->>'token'; pid text; request_id text; mode text; qty numeric; n integer;
begin
 if auth.uid() is null or not transport_private.has_role(w,array['admin','operator']) then raise exception 'Workspace operator access required' using errcode='42501'; end if;
 if jsonb_typeof(payload) is distinct from 'object' or octet_length(payload::text)>20000000 then raise exception 'Invalid or oversized handover payload'; end if;
 if token is null or token !~ '^[a-f0-9]{64}$' then raise exception 'Invalid handover QR' using errcode='42501'; end if;
 perform 1 from public.to_workspaces where id=w for update;
 if action='publish_department_order' then
  snap:=transport_private.safe_snapshot(payload->'form');
  if jsonb_typeof(snap) is distinct from 'object' or snap->>'id' !~ '^TO-[A-Z0-9-]{1,64}$'
   or snap->>'status' is distinct from 'complete' or (snap->>'revision')::integer is distinct from 1
   or not transport_private.valid_location(snap->'destination') or not transport_private.valid_location(snap->'origin')
   or jsonb_typeof(snap->'lines') is distinct from 'array' or jsonb_array_length(snap->'lines') not between 1 and 500
   or coalesce(snap->'sourceDepartment'->>'name','')='' or coalesce(snap->'sourceDepartment'->>'location','')='' then
   raise exception 'A completed department form, destination, origin and material rows are required';
  end if;
  select * into d from public.to_department_orders where workspace_id=w and id=snap->>'id';
  if d.id is not null then
   if d.snapshot is distinct from snap or not exists(select 1 from transport_private.handoff_links where workspace_id=w and form_id=d.id and token_hash=encode(extensions.digest(token,'sha256'),'hex')) then raise exception 'Department document revision is immutable'; end if;
   return jsonb_build_object('id',d.id,'published',true,'receivedAt',d.received_at);
  end if;
  if exists(select 1 from public.to_documents where workspace_id=w and kind='form' and reference_id=snap->>'id') then raise exception 'Form ID already exists'; end if;
  n:=0;
  for line in select value from jsonb_array_elements(snap->'lines') loop
   qty:=nullif(line->>'qty','')::numeric;
   if qty is null or qty<=0 or qty::text in ('NaN','Infinity','-Infinity') or coalesce(nullif(line->>'hu',''),nullif(line->>'dn',''),nullif(line->>'part',''),nullif(line->>'description','')) is null then raise exception 'Material rows need a positive quantity and material reference'; end if;
   n:=n+1;
  end loop;
  if exists(select 1 from jsonb_array_elements(snap->'lines') x where coalesce(x->>'hu','')<>'' group by x->>'hu' having count(*)>1) then raise exception 'Duplicate HU in department form'; end if;
  if exists(select 1 from jsonb_array_elements(snap->'lines') x join public.to_material_lines l on l.workspace_id=w and l.hu=x->>'hu' and l.hu<>'' and l.active) then raise exception 'HU is already assigned to a pallet'; end if;
  if exists(select 1 from public.to_department_orders o cross join lateral jsonb_array_elements(o.snapshot->'lines') a cross join lateral jsonb_array_elements(snap->'lines') b where o.workspace_id=w and o.received_at is null and coalesce(a->>'hu','')<>'' and a->>'hu'=b->>'hu') then raise exception 'HU is already on an outstanding department order'; end if;
  insert into public.to_department_orders(workspace_id,id,department_name,department_location,snapshot) values(w,snap->>'id',snap->'sourceDepartment'->>'name',snap->'sourceDepartment'->>'location',snap);
  insert into transport_private.handoff_links(token_hash,workspace_id,form_id) values(encode(extensions.digest(token,'sha256'),'hex'),w,snap->>'id');
  insert into public.to_documents(workspace_id,kind,reference_id,revision,snapshot) values(w,'form',snap->>'id',1,snap);
  perform transport_private.record_event(w,'Department transport order created',snap->>'id','operator',jsonb_build_object('department',snap->'sourceDepartment'->>'name','location',snap->'sourceDepartment'->>'location'));
  return jsonb_build_object('id',snap->>'id','published',true);
 end if;
 select * into h from transport_private.handoff_links where workspace_id=w and token_hash=encode(extensions.digest(token,'sha256'),'hex');
 if h.form_id is null then raise exception 'Handover QR not found in this workspace' using errcode='42501'; end if;
 select * into d from public.to_department_orders where workspace_id=w and id=h.form_id;
 if action='receive_department_order' then
  request_id:=payload->>'requestId'; pid:=payload->>'palletId'; mode:=payload->>'mode';
  if coalesce(request_id,'') !~ '^[a-f0-9-]{32,64}$' or coalesce(pid,'') !~ '^P-[A-Z0-9-]{1,64}$' or mode is null or mode not in ('open','finalised') then raise exception 'Choose Open Pallet or Finalised Pallet'; end if;
  if d.received_at is not null and (d.receive_request is distinct from request_id or d.pallet_id is distinct from pid) then raise exception 'This transport order has already been received on pallet %',d.pallet_id; end if;
  if d.received_at is null then
   if not transport_private.valid_location(payload->'origin') then raise exception 'Delivery Operations origin is required'; end if;
   f:=d.snapshot||jsonb_build_object('revision',2,'origin',payload->'origin','sourceOrigin',d.snapshot->'origin','palletId',pid,'receivedAt',now(),'updatedAt',now(),'handoffSourceId',d.id);
   p:=jsonb_build_object('id',pid,'status',mode,'revision',case when mode='finalised' then 1 else 0 end,'destination',f->'destination');
   result:=transport_private.operator_api(w,'save_pallet',jsonb_build_object('pallet',p,'forms',jsonb_build_array(f),'expectedRowVersion',0));
   update public.to_department_orders set received_at=now(),received_by=auth.uid(),pallet_id=pid,receive_request=request_id where workspace_id=w and id=d.id;
   perform transport_private.record_event(w,'Department handover received',d.id,'operator',jsonb_build_object('palletId',pid,'status',mode,'fromDepartment',d.department_name));
  end if;
 elsif action<>'get_department_order' then raise exception 'Unknown handover action'; end if;
 return (select jsonb_build_object('form',x.snapshot,'receivedAt',x.received_at,'palletId',x.pallet_id,
  'pallet',(select to_jsonb(y) from public.to_pallets y where y.workspace_id=w and y.id=x.pallet_id),
  'receivedForm',(select data from public.to_forms where workspace_id=w and id=x.id)) from public.to_department_orders x where x.workspace_id=w and x.id=d.id);
end $$;
revoke all on function transport_private.department_api(uuid,text,jsonb) from public,anon,authenticated;

create or replace function transport_private.device_api(token text,action text,payload jsonb) returns jsonb
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
  snap:=transport_private.safe_snapshot(payload->'snapshot');
  if jsonb_typeof(snap)<>'object' then raise exception 'Document snapshot required'; end if;
  select snapshot into existing from public.to_archive_documents where workspace_id=d.workspace_id and kind=payload->>'kind' and reference_id=payload->>'id' and revision=(payload->>'revision')::integer;
  if existing is not null and transport_private.safe_snapshot(existing)-'online' is distinct from snap-'online' then raise exception 'Archived document revision is immutable'; end if;
  insert into public.to_archive_documents(workspace_id,kind,reference_id,revision,snapshot)
   values(d.workspace_id,payload->>'kind',payload->>'id',(payload->>'revision')::integer,snap) on conflict (workspace_id,kind,reference_id,revision) do update set snapshot=case when to_archive_documents.snapshot->'online' is null then excluded.snapshot else transport_private.safe_snapshot(to_archive_documents.snapshot) end;
  result:='{"archived":true}';
 elsif action in ('publish_department_order','get_department_order','receive_department_order') then
  result:=transport_private.department_api(d.workspace_id,action,payload);
 elsif action in ('save_pallet','create_manifest','rotate_driver_link') then
  result:=transport_private.operator_api(d.workspace_id,action,payload);
 else raise exception 'Device action is not allowed'; end if;
 perform set_config('request.jwt.claim.sub',coalesce(previous_sub,''),true);
 return result;
end $$;

create function transport_private.tracking_building(value text) returns text
language sql immutable security invoker set search_path='' as $$
 select case
  when regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') like '%weert1a%' then 'weert1a'
  when regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') like '%weert1b%' then 'weert1b'
  when regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') like '%weert2%' then 'weert2'
  when regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') like '%dc8%' then 'dc8'
  when regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') like '%hqpack%' then 'hqpack'
  else regexp_replace(lower(coalesce(value,'')),'[^a-z0-9]','','g') end
$$;
revoke all on function transport_private.tracking_building(text) from public,anon;
grant execute on function transport_private.tracking_building(text) to authenticated;

create function transport_private.tracking_catalog(w uuid) returns setof jsonb
language sql stable security invoker set search_path='' as $$
 with manifest_rows as (
  select m.*,coalesce((select jsonb_agg(jsonb_build_object('id',i.pallet_id,'revision',i.pallet_revision,'snapshot',i.snapshot,'scannedAt',i.scanned_at,'collectedAt',i.collected_at,'deliveredAt',i.delivered_at) order by i.pallet_id)
   from public.to_manifest_pallets i where i.workspace_id=m.workspace_id and i.manifest_id=m.id and ((m.status='ready' and i.released_at is null) or i.collected_at is not null)),'[]') as contents,
   (select count(*) from public.to_manifest_pallets i where i.workspace_id=m.workspace_id and i.manifest_id=m.id and i.released_at is not null and i.collected_at is null) as left_behind
  from public.to_manifests m where m.workspace_id=w and m.status<>'cancelled'
 ), live_manifests as (
  select jsonb_build_object('kind','load','id',m.id,'revision',m.revision,'created_at',m.created_at,
   'building',m.building,'building_key',transport_private.tracking_building(m.building),
   'shipment_status',m.status,'stage',case when m.delivered_at is not null then 'delivered' when m.collected_at is not null then 'collected' else 'ready' end,
   'manifest_id',m.id,'collected_at',m.collected_at,'delivered_at',m.delivered_at,'driver_name',m.driver_name,'vehicle',m.vehicle,'receiver_name',m.receiver_name,
   'reason',m.reason,'left_behind',m.left_behind,'snapshot',jsonb_build_object('id',m.id,'building',m.building,'origin',m.origin,'pallets',m.contents),
   'events',(select coalesce(jsonb_agg(jsonb_build_object('action',e.action,'at',e.at,'detail',e.detail) order by e.at),'[]') from public.to_events e where e.workspace_id=w and e.reference_id=m.id)) as r
  from manifest_rows m where jsonb_array_length(m.contents)>0
 ), live_pallets as (
  select jsonb_build_object('kind','pallet','id',p.id,'revision',p.revision,'created_at',p.created_at,
   'building',p.destination->>'building','building_key',transport_private.tracking_building(p.destination->>'building'),
   'stage','in_process','shipment_status',p.status,'snapshot',jsonb_build_object('id',p.id,'revision',p.revision,'destination',p.destination,'origin',p.origin,
    'forms',coalesce((select jsonb_agg(f.data order by f.id) from public.to_forms f where f.workspace_id=w and f.pallet_id=p.id and f.removed_at is null),'[]')),
   'reason',(select m.reason from public.to_manifest_pallets i join public.to_manifests m on m.workspace_id=i.workspace_id and m.id=i.manifest_id where i.workspace_id=w and i.pallet_id=p.id and i.released_at is not null and i.collected_at is null order by i.released_at desc limit 1),
   'events',(select coalesce(jsonb_agg(jsonb_build_object('action',e.action,'at',e.at,'detail',e.detail) order by e.at),'[]') from public.to_events e where e.workspace_id=w and (e.reference_id=p.id or exists(select 1 from public.to_department_orders o where o.workspace_id=w and o.pallet_id=p.id and o.id=e.reference_id)))) as r
  from public.to_pallets p where p.workspace_id=w
 ), department_forms as (
  select jsonb_build_object('kind','form','id',d.id,'revision',1,'created_at',d.created_at,
   'building',d.snapshot->'destination'->>'building','building_key',transport_private.tracking_building(d.snapshot->'destination'->>'building'),
   'stage','in_process','shipment_status','At '||d.department_name,'source_department',d.department_name,'snapshot',d.snapshot,
   'events',(select coalesce(jsonb_agg(jsonb_build_object('action',e.action,'at',e.at,'detail',e.detail) order by e.at),'[]') from public.to_events e where e.workspace_id=w and e.reference_id=d.id)) as r
  from public.to_department_orders d where d.workspace_id=w and d.received_at is null
 ), archived as (
  select distinct on(kind,reference_id) kind,reference_id,revision,snapshot,created_at from (
   select a.kind,a.reference_id,a.revision,a.snapshot,a.created_at,1 as priority from public.to_archive_documents a where a.workspace_id=w
   union all select case when d.kind='manifest' then 'load' else d.kind end,d.reference_id,d.revision,d.snapshot,d.created_at,2 from public.to_documents d where d.workspace_id=w
  ) all_versions order by kind,reference_id,revision desc,priority desc
 ), archive_rows as (
  select jsonb_build_object('kind',a.kind,'id',a.reference_id,'revision',a.revision,'created_at',a.created_at,
   'building',coalesce(a.snapshot->'destination'->>'building',a.snapshot->>'building'),
   'building_key',transport_private.tracking_building(coalesce(a.snapshot->'destination'->>'building',a.snapshot->>'building')),
   'stage',case when a.kind='load' then 'ready' else 'in_process' end,'shipment_status',case when a.kind='load' then 'ready' else 'Prepared' end,'snapshot',a.snapshot,'events','[]'::jsonb) as r
  from archived a where
   not exists(select 1 from public.to_department_orders d where d.workspace_id=w and d.id=a.reference_id)
   and not exists(select 1 from public.to_forms f where f.workspace_id=w and f.id=a.reference_id)
   and not exists(select 1 from public.to_pallets p where p.workspace_id=w and p.id=a.reference_id)
   and (a.kind<>'load' or not exists(select 1 from public.to_manifests m where m.workspace_id=w and m.id=coalesce(a.snapshot->'online'->>'id',a.reference_id)))
   and (a.kind<>'load' or not exists(select 1 from jsonb_array_elements(coalesce(a.snapshot->'pallets','[]')) x join public.to_manifest_pallets i on i.workspace_id=w and i.pallet_id=x->>'id'))
 ), all_records as (
  select r from live_manifests union all select r from live_pallets union all select r from department_forms union all select r from archive_rows
 ), covered_pallets as (
  select x->>'id' as id from all_records a cross join lateral jsonb_array_elements(coalesce(a.r->'snapshot'->'pallets','[]')) x where a.r->>'kind'='load'
 ), covered_forms as (
  select f->>'id' as id from all_records a cross join lateral jsonb_array_elements(coalesce(a.r->'snapshot'->'forms','[]')) f where a.r->>'kind'='pallet'
  union select f->>'id' from all_records a cross join lateral jsonb_array_elements(coalesce(a.r->'snapshot'->'pallets','[]')) p cross join lateral jsonb_array_elements(coalesce(p->'snapshot'->'forms',p->'forms','[]')) f where a.r->>'kind'='load'
 )
 select transport_private.safe_snapshot(r) from all_records a where
  (a.r->>'kind'<>'pallet' or not exists(select 1 from covered_pallets p where p.id=a.r->>'id'))
  and (a.r->>'kind'<>'form' or (not exists(select 1 from covered_forms f where f.id=a.r->>'id') and not exists(select 1 from covered_pallets p where p.id=a.r->'snapshot'->>'palletId')))
$$;
revoke all on function transport_private.tracking_catalog(uuid) from public,anon;
grant execute on function transport_private.tracking_catalog(uuid) to authenticated;

create or replace function public.transport_tracking(p_workspace uuid,p_query text default '') returns jsonb
language sql stable security invoker set search_path='' as $$
 select coalesce(jsonb_agg(r order by r->>'created_at' desc,r->>'id'),'[]') from (
  select r from transport_private.tracking_catalog(p_workspace) r
  where btrim(p_query)='' or strpos(lower((r->>'id')||' '||(r->'snapshot')::text),lower(btrim(p_query)))>0
  order by r->>'created_at' desc,r->>'id' limit 200
 ) matches
$$;

create function public.transport_tracking_page(p_workspace uuid,p_query text default '',p_building text default '',p_stage text default '',p_offset integer default 0) returns jsonb
language sql stable security invoker set search_path='' as $$
 with candidates as materialized (
  select r from transport_private.tracking_catalog(p_workspace) r where
   (btrim(p_query)='' or strpos(lower((r->>'id')||' '||(r->'snapshot')::text),lower(btrim(p_query)))>0)
   and (p_building='' or r->>'building_key'=p_building)
 ), filtered as (select r from candidates where p_stage='' or r->>'stage'=p_stage), page as (
  select r from filtered order by r->>'created_at' desc,r->>'id' limit 50 offset least(100000,greatest(0,p_offset))
 )
 select jsonb_build_object('authorized',transport_private.has_role(p_workspace,array['admin','operator','viewer']),'records',(select coalesce(jsonb_agg(r),'[]') from page),'total',(select count(*) from filtered),
  'counts',(select coalesce(jsonb_object_agg(stage,n),'{}') from (select r->>'stage' as stage,count(*) as n from candidates group by r->>'stage') groups),
  'hasMore',(select count(*) from filtered)>greatest(0,p_offset)+50)
$$;
revoke all on function public.transport_tracking_page(uuid,text,text,text,integer) from public,anon;
grant execute on function public.transport_tracking_page(uuid,text,text,text,integer) to authenticated;

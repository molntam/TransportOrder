create schema if not exists transport_private;
revoke all on schema transport_private from public;
grant usage on schema transport_private to authenticated, anon;

create function transport_private.building_key(value text) returns text
language sql immutable strict set search_path = ''
as $$ select lower(regexp_replace(btrim(value), '\s+', ' ', 'g')) $$;

create function transport_private.valid_location(value jsonb) returns boolean
language sql immutable set search_path = ''
as $$ select coalesce(jsonb_typeof(value) = 'object' and
  length(btrim(value->>'building')) between 1 and 300 and
  length(btrim(value->>'department')) between 1 and 300 and
  length(btrim(value->>'shipTo')) between 1 and 300, false) $$;

create table public.to_workspaces (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  timezone text not null default 'Europe/Amsterdam',
  created_at timestamptz not null default now()
);
create table public.to_members (
  workspace_id uuid not null references public.to_workspaces(id),
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('admin','operator','viewer')),
  created_at timestamptz not null default now(),
  primary key (workspace_id,user_id)
);
create index to_members_user on public.to_members(user_id,workspace_id);

create function transport_private.has_role(w uuid, roles text[]) returns boolean
language sql stable security definer set search_path = ''
as $$ select auth.uid() is not null and exists (
 select 1 from public.to_members m where m.workspace_id=w and m.user_id=(select auth.uid()) and m.role=any(roles)
) $$;

create table public.to_destinations (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.to_workspaces(id),
  building text not null check (length(btrim(building)) between 1 and 300),
  department text not null check (length(btrim(department)) between 1 and 300),
  ship_to text not null check (length(btrim(ship_to)) between 1 and 300),
  enabled boolean not null default true,
  data jsonb not null default '{}',
  unique (workspace_id,building,department,ship_to)
);
create table public.to_dock_slots (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.to_workspaces(id),
  building text not null check (length(btrim(building)) between 1 and 300),
  weekdays smallint[] not null check (cardinality(weekdays)>0 and weekdays <@ array[0,1,2,3,4]::smallint[] and array_position(weekdays,null) is null),
  start_time time not null,
  end_time time not null check (end_time>start_time),
  enabled boolean not null default true
);
create index to_dock_slots_workspace on public.to_dock_slots(workspace_id);
create table public.to_imports (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.to_workspaces(id),
  kind text not null check (kind in ('shipto','quantities')),
  filename text not null default '',
  data jsonb not null check (jsonb_typeof(data)='object'),
  imported_at timestamptz not null default now()
);
create index to_imports_latest on public.to_imports(workspace_id,kind,imported_at desc);
create table public.to_pallets (
  workspace_id uuid not null references public.to_workspaces(id),
  id text not null check (id ~ '^P-[A-Z0-9-]{1,64}$'),
  status text not null check (status in ('open','finalised')),
  revision integer not null default 0 check (revision>=0),
  row_version bigint not null default 1 check (row_version>0),
  destination jsonb not null check (transport_private.valid_location(destination)),
  origin jsonb not null check (transport_private.valid_location(origin)),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finalised_at timestamptz,
  collected_at timestamptz,
  delivered_at timestamptz,
  primary key (workspace_id,id),
  check (status<>'finalised' or (revision>0 and finalised_at is not null)),
  check (delivered_at is null or collected_at is not null)
);
create index to_pallets_ready on public.to_pallets(workspace_id,status,transport_private.building_key(destination->>'building')) where collected_at is null;
create table public.to_forms (
  workspace_id uuid not null,
  id text not null check (id ~ '^TO-[A-Z0-9-]{1,64}$'),
  pallet_id text not null,
  status text not null check (status in ('draft','complete')),
  revision integer not null check (revision>=0),
  data jsonb not null check (jsonb_typeof(data)='object'),
  removed_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (workspace_id,id),
  foreign key (workspace_id,pallet_id) references public.to_pallets(workspace_id,id)
);
create index to_forms_pallet on public.to_forms(workspace_id,pallet_id);
create table public.to_material_lines (
  workspace_id uuid not null,
  form_id text not null,
  line_no integer not null check (line_no>0),
  hu text not null default '',
  dn text not null default '',
  part text not null default '',
  description text not null default '',
  quantity numeric check (quantity>0 and quantity<>'NaN'::numeric and quantity<>'Infinity'::numeric),
  active boolean not null default false,
  primary key (workspace_id,form_id,line_no),
  foreign key (workspace_id,form_id) references public.to_forms(workspace_id,id),
  check (not active or quantity is not null)
);
create unique index to_lines_unique_hu on public.to_material_lines(workspace_id,hu) where active and hu<>'';
create index to_lines_dn on public.to_material_lines(workspace_id,dn) where dn<>'';
create table public.to_documents (
  workspace_id uuid not null references public.to_workspaces(id),
  kind text not null check (kind in ('form','pallet','manifest')),
  reference_id text not null,
  revision integer not null check (revision>0),
  snapshot jsonb not null check (jsonb_typeof(snapshot)='object'),
  created_at timestamptz not null default now(),
  primary key (workspace_id,kind,reference_id,revision)
);
create table public.to_manifests (
  workspace_id uuid not null references public.to_workspaces(id),
  id text not null,
  revision integer not null default 1 check (revision>0),
  row_version bigint not null default 1,
  building text not null check (length(btrim(building)) between 1 and 300),
  origin jsonb not null check (transport_private.valid_location(origin)),
  status text not null default 'ready' check (status in ('ready','collected','partial','cancelled','delivered')),
  driver_name text not null default '',
  vehicle text not null default '',
  reason text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  collected_at timestamptz,
  delivered_at timestamptz,
  primary key (workspace_id,id)
);
create index to_manifests_recent on public.to_manifests(workspace_id,created_at desc);
create table public.to_manifest_pallets (
  workspace_id uuid not null,
  manifest_id text not null,
  pallet_id text not null,
  pallet_revision integer not null check (pallet_revision>0),
  snapshot jsonb not null,
  scanned_at timestamptz,
  collected_at timestamptz,
  delivered_at timestamptz,
  released_at timestamptz,
  primary key (workspace_id,manifest_id,pallet_id),
  foreign key (workspace_id,manifest_id) references public.to_manifests(workspace_id,id),
  foreign key (workspace_id,pallet_id) references public.to_pallets(workspace_id,id)
);
create unique index to_one_active_manifest on public.to_manifest_pallets(workspace_id,pallet_id) where released_at is null;
create index to_manifest_pallet_lookup on public.to_manifest_pallets(workspace_id,pallet_id,manifest_id);
create table public.to_events (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.to_workspaces(id),
  action text not null,
  reference_id text not null,
  actor_user_id uuid,
  actor_kind text not null check (actor_kind in ('operator','driver','system')),
  detail jsonb not null default '{}',
  at timestamptz not null default now()
);
create index to_events_record on public.to_events(workspace_id,reference_id,at desc);
create table transport_private.driver_links (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  workspace_id uuid not null,
  manifest_id text not null,
  manifest_revision integer not null,
  expires_at timestamptz not null,
  revoked_at timestamptz,
  foreign key (workspace_id,manifest_id) references public.to_manifests(workspace_id,id)
);
create index to_links_manifest on transport_private.driver_links(workspace_id,manifest_id);
alter table transport_private.driver_links enable row level security;
create policy service_only on transport_private.driver_links to service_role using (true) with check (true);
revoke all on transport_private.driver_links from public,anon,authenticated;

create function transport_private.record_event(w uuid, a text, r text, k text, d jsonb default '{}') returns void
language sql set search_path = ''
as $$ insert into public.to_events(workspace_id,action,reference_id,actor_user_id,actor_kind,detail)
 values(w,a,r,auth.uid(),k,d) $$;

create function transport_private.issue_link(w uuid, m text) returns text
language plpgsql set search_path = ''
as $$
declare token text := encode(extensions.gen_random_bytes(32),'hex');
begin
 update transport_private.driver_links set revoked_at=now() where workspace_id=w and manifest_id=m and revoked_at is null;
 insert into transport_private.driver_links(token_hash,workspace_id,manifest_id,manifest_revision,expires_at)
 select encode(extensions.digest(token,'sha256'),'hex'),w,m,revision,now()+interval '7 days'
 from public.to_manifests where workspace_id=w and id=m;
 return token;
end $$;

create function transport_private.operator_api(p_workspace uuid,p_action text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
 p public.to_pallets; m public.to_manifests; item record;
 doc jsonb; f jsonb; l jsonb; forms jsonb; dest jsonb; orig jsonb; snap jsonb;
 pid text; fid text; mid text; token text; v_reason text := btrim(coalesce(p_payload->>'reason',''));
 ver integer; num integer; total integer; st text; expected bigint; qty numeric;
begin
 if auth.uid() is null or not transport_private.has_role(p_workspace,array['admin','operator']) then
  raise exception 'Workspace operator access required' using errcode='42501';
 end if;
 if jsonb_typeof(p_payload)<>'object' or octet_length(p_payload::text)>20000000 then raise exception 'Invalid or oversized payload'; end if;
 perform 1 from public.to_workspaces where id=p_workspace for update;
 if p_action='save_pallet' then
  doc:=p_payload->'pallet'; forms:=p_payload->'forms'; pid:=doc->>'id'; st:=doc->>'status';
  if doc is null or forms is null or jsonb_typeof(forms)<>'array' or jsonb_array_length(forms) not between 1 and 500 or st not in ('open','finalised') then
   raise exception 'Provide an open/finalised pallet and 1–500 forms';
  end if;
  select * into p from public.to_pallets where workspace_id=p_workspace and id=pid;
  expected:=coalesce((p_payload->>'expectedRowVersion')::bigint,0);
  if coalesce(p.row_version,0)<>expected then raise exception 'Pallet changed; refresh before saving' using errcode='40001'; end if;
  if p.id is not null and (p.status<>'open' or p.collected_at is not null or exists(select 1 from public.to_manifest_pallets where workspace_id=p_workspace and pallet_id=pid and released_at is null)) then
   raise exception 'Reopen an unreserved, uncollected pallet before editing';
  end if;
  dest:=doc->'destination'; orig:=forms->0->'origin'; ver:=coalesce((doc->>'revision')::integer,0);
  if ver<>coalesce(p.revision,0)+(case when st='finalised' then 1 else 0 end) then raise exception 'Incorrect pallet document revision'; end if;
  insert into public.to_pallets(workspace_id,id,status,revision,destination,origin,finalised_at)
  values(p_workspace,pid,st,ver,dest,orig,case when st='finalised' then now() end)
  on conflict (workspace_id,id) do update set status=excluded.status,revision=excluded.revision,destination=excluded.destination,
   origin=excluded.origin,updated_at=now(),row_version=to_pallets.row_version+1,finalised_at=excluded.finalised_at;
  update public.to_material_lines set active=false where workspace_id=p_workspace and form_id in
   (select id from public.to_forms where workspace_id=p_workspace and pallet_id=pid);
  update public.to_forms set removed_at=now() where workspace_id=p_workspace and pallet_id=pid;
  for f in select value from jsonb_array_elements(forms) loop
   fid:=f->>'id';
   if f->>'status' not in ('draft','complete') or (st='finalised' and f->>'status'<>'complete')
    or f->'destination' is distinct from dest or f->'origin' is distinct from orig
    or jsonb_typeof(f->'lines') is distinct from 'array' or jsonb_array_length(f->'lines')>500 then
    raise exception 'Forms must share the pallet route/origin; finalised pallets require completed forms';
   end if;
   if exists(select 1 from public.to_forms where workspace_id=p_workspace and id=fid and pallet_id<>pid) then raise exception 'Form belongs to another pallet'; end if;
   if exists(select 1 from public.to_forms where workspace_id=p_workspace and id=fid and removed_at is null) then raise exception 'Duplicate form ID'; end if;
   insert into public.to_forms(workspace_id,id,pallet_id,status,revision,data)
   values(p_workspace,fid,pid,f->>'status',coalesce((f->>'revision')::integer,0),f-'versions')
   on conflict (workspace_id,id) do update set status=excluded.status,revision=excluded.revision,data=excluded.data,removed_at=null,updated_at=now();
   delete from public.to_material_lines where workspace_id=p_workspace and form_id=fid;
   num:=0;
   for l in select value from jsonb_array_elements(f->'lines') loop
    num:=num+1; qty:=nullif(l->>'qty','')::numeric;
    if f->>'status'='complete' and (qty is null or not (qty>0) or
      coalesce(nullif(l->>'hu',''),nullif(l->>'dn',''),nullif(l->>'part',''),nullif(l->>'description','')) is null) then
     raise exception 'Completed rows need positive quantity and a HU, DN, part or description';
    end if;
    insert into public.to_material_lines(workspace_id,form_id,line_no,hu,dn,part,description,quantity,active)
    values(p_workspace,fid,num,coalesce(l->>'hu',''),coalesce(l->>'dn',''),coalesce(l->>'part',''),coalesce(l->>'description',''),qty,f->>'status'='complete');
   end loop;
   if f->>'status'='complete' then
    if num=0 then raise exception 'Completed forms need material rows'; end if;
    snap:=f-'versions';
    if exists(select 1 from public.to_documents where workspace_id=p_workspace and kind='form' and reference_id=fid and revision=(f->>'revision')::integer and snapshot is distinct from snap) then
     raise exception 'A completed form revision is immutable';
    end if;
    insert into public.to_documents(workspace_id,kind,reference_id,revision,snapshot)
     values(p_workspace,'form',fid,(f->>'revision')::integer,snap) on conflict do nothing;
   end if;
  end loop;
  if (select count(distinct upper(src_line->>'sourceShipTo')) from jsonb_array_elements(forms) src_form cross join lateral jsonb_array_elements(src_form->'lines') src_line where coalesce(src_line->>'sourceShipTo','')<>'')>1 then
   raise exception 'Mixed SAP ship-to codes must stay on separate pallets';
  end if;
  if st='finalised' then
   snap:=jsonb_build_object('id',pid,'revision',ver,'destination',dest,'forms',forms,'at',now());
   insert into public.to_documents(workspace_id,kind,reference_id,revision,snapshot) values(p_workspace,'pallet',pid,ver,snap);
  end if;
  perform transport_private.record_event(p_workspace,'Pallet saved',pid,'operator',jsonb_build_object('status',st,'revision',ver));
  return (select to_jsonb(x) from public.to_pallets x where workspace_id=p_workspace and id=pid);
 elsif p_action='reopen_pallet' then
  pid:=p_payload->>'id';
  select * into p from public.to_pallets where workspace_id=p_workspace and id=pid;
  if p.id is null or p.status<>'finalised' or p.collected_at is not null or v_reason=''
   or p.row_version is distinct from (p_payload->>'expectedRowVersion')::bigint
   or exists(select 1 from public.to_manifest_pallets where workspace_id=p_workspace and pallet_id=pid and released_at is null) then
   raise exception 'Choose a current uncollected, unreserved finalised pallet and give a reason';
  end if;
  update public.to_pallets set status='open',row_version=row_version+1,updated_at=now() where workspace_id=p_workspace and id=pid;
  perform transport_private.record_event(p_workspace,'Pallet reopened',pid,'operator',jsonb_build_object('reason',v_reason));
  return jsonb_build_object('id',pid,'status','open','rowVersion',p.row_version+1);
 elsif p_action='create_manifest' then
  mid:='LOAD-'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,12));
  select * into p from public.to_pallets x where workspace_id=p_workspace and status='finalised' and collected_at is null
   and transport_private.building_key(destination->>'building')=transport_private.building_key(p_payload->>'building')
   and not exists(select 1 from public.to_manifest_pallets i where i.workspace_id=x.workspace_id and i.pallet_id=x.id and i.released_at is null)
   order by created_at limit 1;
  if p.id is null then raise exception 'No unassigned finalised pallets for this building'; end if;
  insert into public.to_manifests(workspace_id,id,building,origin) values(p_workspace,mid,p.destination->>'building',p.origin);
  insert into public.to_manifest_pallets(workspace_id,manifest_id,pallet_id,pallet_revision,snapshot)
   select p_workspace,mid,x.id,x.revision,d.snapshot from public.to_pallets x join public.to_documents d
    on d.workspace_id=x.workspace_id and d.kind='pallet' and d.reference_id=x.id and d.revision=x.revision
   where x.workspace_id=p_workspace and x.status='finalised' and x.collected_at is null
    and transport_private.building_key(x.destination->>'building')=transport_private.building_key(p.destination->>'building')
    and not exists(select 1 from public.to_manifest_pallets i where i.workspace_id=x.workspace_id and i.pallet_id=x.id and i.released_at is null);
  if exists(select 1 from public.to_manifest_pallets i join public.to_pallets x on x.workspace_id=i.workspace_id and x.id=i.pallet_id
   where i.workspace_id=p_workspace and i.manifest_id=mid and x.origin is distinct from p.origin) then raise exception 'Separate loads are required for different origins'; end if;
  select count(*) into total from public.to_manifest_pallets where workspace_id=p_workspace and manifest_id=mid;
  snap:=jsonb_build_object('id',mid,'revision',1,'building',p.destination->>'building','pallets',
   (select jsonb_agg(jsonb_build_object('id',pallet_id,'revision',pallet_revision,'snapshot',snapshot) order by pallet_id) from public.to_manifest_pallets where workspace_id=p_workspace and manifest_id=mid));
  insert into public.to_documents(workspace_id,kind,reference_id,revision,snapshot) values(p_workspace,'manifest',mid,1,snap);
  token:=transport_private.issue_link(p_workspace,mid);
  perform transport_private.record_event(p_workspace,'Manifest created',mid,'operator',jsonb_build_object('pallets',total));
  return jsonb_build_object('id',mid,'revision',1,'palletCount',total,'driverToken',token,'expiresInDays',7);
 elsif p_action in ('cancel_manifest','rotate_driver_link') then
  mid:=p_payload->>'id';
  select * into m from public.to_manifests where workspace_id=p_workspace and id=mid;
  if m.id is null or m.row_version is distinct from (p_payload->>'expectedRowVersion')::bigint then raise exception 'Manifest changed; refresh first'; end if;
  if p_action='cancel_manifest' then
   if m.status<>'ready' or v_reason='' then raise exception 'Only an uncollected manifest can be cancelled, with a reason'; end if;
   update public.to_manifests set status='cancelled',reason=v_reason,row_version=row_version+1,updated_at=now() where workspace_id=p_workspace and id=mid;
   update public.to_manifest_pallets set released_at=now() where workspace_id=p_workspace and manifest_id=mid;
   update transport_private.driver_links set revoked_at=now() where workspace_id=p_workspace and manifest_id=mid and revoked_at is null;
   perform transport_private.record_event(p_workspace,'Manifest cancelled',mid,'operator',jsonb_build_object('reason',v_reason));
   return jsonb_build_object('id',mid,'status','cancelled');
  end if;
  if m.status not in ('ready','collected','partial') then raise exception 'This manifest cannot receive a new driver link'; end if;
  token:=transport_private.issue_link(p_workspace,mid);
  update public.to_manifests set row_version=row_version+1,updated_at=now() where workspace_id=p_workspace and id=mid;
  perform transport_private.record_event(p_workspace,'Driver link rotated',mid,'operator');
  return jsonb_build_object('id',mid,'driverToken',token,'expiresInDays',7);
 elsif p_action='set_dock_slots' then
  if jsonb_typeof(p_payload->'slots') is distinct from 'array' or jsonb_array_length(p_payload->'slots')>200 then raise exception 'Provide up to 200 dock slots'; end if;
  delete from public.to_dock_slots where workspace_id=p_workspace;
  for doc in select value from jsonb_array_elements(p_payload->'slots') loop
   insert into public.to_dock_slots(workspace_id,building,weekdays,start_time,end_time)
   values(p_workspace,doc->>'building',array(select jsonb_array_elements_text(doc->'days')::smallint),(doc->>'start')::time,(doc->>'end')::time);
  end loop;
  perform transport_private.record_event(p_workspace,'Dock slots updated','settings','operator'); return jsonb_build_object('ok',true);
 elsif p_action='import_source' then
  if jsonb_typeof(p_payload->'data') is distinct from 'object' or jsonb_typeof(p_payload->'data'->'rows') is distinct from 'array'
   or jsonb_array_length(p_payload->'data'->'rows')>50000 then raise exception 'Provide parsed SAP data with up to 50000 rows'; end if;
  insert into public.to_imports(workspace_id,kind,filename,data) values(p_workspace,p_payload->>'kind',left(coalesce(p_payload->>'filename',''),200),p_payload->'data');
  perform transport_private.record_event(p_workspace,'SAP source imported',p_payload->>'kind','operator'); return jsonb_build_object('ok',true);
 elsif p_action='set_member' then
  if not transport_private.has_role(p_workspace,array['admin']) then raise exception 'Administrator access required' using errcode='42501'; end if;
  if (p_payload->>'userId')::uuid=auth.uid() then raise exception 'Ask another administrator to change your membership'; end if;
  if p_payload->>'role'='remove' then delete from public.to_members where workspace_id=p_workspace and user_id=(p_payload->>'userId')::uuid;
  else insert into public.to_members(workspace_id,user_id,role) values(p_workspace,(p_payload->>'userId')::uuid,p_payload->>'role')
   on conflict (workspace_id,user_id) do update set role=excluded.role;
  end if;
  perform transport_private.record_event(p_workspace,'Workspace membership changed',p_payload->>'userId','operator',jsonb_build_object('role',p_payload->>'role'));
  return jsonb_build_object('ok',true);
 end if;
 raise exception 'Unknown operator action';
end $$;

create function transport_private.driver_api(p_token text,p_action text,p_payload jsonb) returns jsonb
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
  update public.to_manifests set status='delivered',delivered_at=now() where workspace_id=m.workspace_id and id=m.id;
  perform transport_private.record_event(m.workspace_id,'Delivery confirmed',m.id,'driver',jsonb_build_object('building',m.building,'receiver',p_payload->>'receiver'));
 elsif p_action<>'get' then raise exception 'Unknown driver action';
 end if;
 if p_action<>'get' and not duplicate then
  update public.to_manifests set row_version=row_version+1,updated_at=now() where workspace_id=m.workspace_id and id=m.id;
 end if;
 return (select jsonb_build_object('id',x.id,'revision',x.revision,'rowVersion',x.row_version,'building',x.building,'status',x.status,
   'createdAt',x.created_at,'collectedAt',x.collected_at,'deliveredAt',x.delivered_at,'duplicate',duplicate,
   'plannedCount',(select count(*) from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id),
   'scannedCount',(select count(*) from public.to_manifest_pallets where workspace_id=m.workspace_id and manifest_id=m.id and scanned_at is not null),
   'pallets',(select coalesce(jsonb_agg(jsonb_build_object('id',j.pallet_id,'revision',j.pallet_revision,'scannedAt',j.scanned_at,'collectedAt',j.collected_at,'deliveredAt',j.delivered_at,
     'destination',j.snapshot->'destination','forms',(select jsonb_agg(jsonb_build_object('id',f->>'id','lines',(select jsonb_agg(jsonb_build_object('dn',l->>'dn','hu',l->>'hu','qty',l->>'qty')) from jsonb_array_elements(f->'lines') l))) from jsonb_array_elements(j.snapshot->'forms') f)) order by j.pallet_id),'[]')
     from public.to_manifest_pallets j where j.workspace_id=m.workspace_id and j.manifest_id=m.id)) from public.to_manifests x where x.workspace_id=m.workspace_id and x.id=m.id);
end $$;

create function public.transport_operator(p_workspace uuid,p_action text,p_payload jsonb default '{}') returns jsonb
language sql security invoker set search_path = ''
as $$ select transport_private.operator_api(p_workspace,p_action,p_payload) $$;
create function public.transport_driver(p_token text,p_action text default 'get',p_payload jsonb default '{}') returns jsonb
language sql security invoker set search_path = ''
as $$ select transport_private.driver_api(p_token,p_action,p_payload) $$;

revoke all on all functions in schema transport_private from public,anon,authenticated;
grant execute on function transport_private.has_role(uuid,text[]) to authenticated;
grant execute on function transport_private.operator_api(uuid,text,jsonb) to authenticated;
grant execute on function transport_private.driver_api(text,text,jsonb) to anon,authenticated;
revoke all on function public.transport_operator(uuid,text,jsonb) from public,anon,authenticated;
revoke all on function public.transport_driver(text,text,jsonb) from public,anon,authenticated;
grant execute on function public.transport_operator(uuid,text,jsonb) to authenticated;
grant execute on function public.transport_driver(text,text,jsonb) to anon,authenticated;

alter table public.to_workspaces enable row level security;
revoke all on public.to_workspaces from public,anon,authenticated;
grant select on public.to_workspaces to authenticated;
create policy workspace_read on public.to_workspaces for select to authenticated using
 (transport_private.has_role(id,array['admin','operator','viewer']));

alter table public.to_members enable row level security;
revoke all on public.to_members from public,anon,authenticated;
grant select on public.to_members to authenticated;
create policy workspace_read on public.to_members for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_destinations enable row level security;
revoke all on public.to_destinations from public,anon,authenticated;
grant select on public.to_destinations to authenticated;
create policy workspace_read on public.to_destinations for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_dock_slots enable row level security;
revoke all on public.to_dock_slots from public,anon,authenticated;
grant select on public.to_dock_slots to authenticated;
create policy workspace_read on public.to_dock_slots for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_imports enable row level security;
revoke all on public.to_imports from public,anon,authenticated;
grant select on public.to_imports to authenticated;
create policy workspace_read on public.to_imports for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_pallets enable row level security;
revoke all on public.to_pallets from public,anon,authenticated;
grant select on public.to_pallets to authenticated;
create policy workspace_read on public.to_pallets for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_forms enable row level security;
revoke all on public.to_forms from public,anon,authenticated;
grant select on public.to_forms to authenticated;
create policy workspace_read on public.to_forms for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_material_lines enable row level security;
revoke all on public.to_material_lines from public,anon,authenticated;
grant select on public.to_material_lines to authenticated;
create policy workspace_read on public.to_material_lines for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_documents enable row level security;
revoke all on public.to_documents from public,anon,authenticated;
grant select on public.to_documents to authenticated;
create policy workspace_read on public.to_documents for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_manifests enable row level security;
revoke all on public.to_manifests from public,anon,authenticated;
grant select on public.to_manifests to authenticated;
create policy workspace_read on public.to_manifests for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_manifest_pallets enable row level security;
revoke all on public.to_manifest_pallets from public,anon,authenticated;
grant select on public.to_manifest_pallets to authenticated;
create policy workspace_read on public.to_manifest_pallets for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

alter table public.to_events enable row level security;
revoke all on public.to_events from public,anon,authenticated;
grant select on public.to_events to authenticated;
create policy workspace_read on public.to_events for select to authenticated using
 (transport_private.has_role(workspace_id,array['admin','operator','viewer']));

insert into public.to_workspaces(slug,name) values ('delivery-ops-5l','Delivery Operations 5L');
notify pgrst,'reload schema';

insert into public.to_destinations(workspace_id,building,department,ship_to,data)
select w.id,r->>'building',r->>'department',r->>'shipTo',r
from public.to_workspaces w cross join jsonb_array_elements('[{"building": "Building 17", "department": "Motion", "shipTo": "B17-MOTION"}, {"building": "Building 21", "department": "Motion", "shipTo": "B21-MOASSY"}, {"building": "Building 21", "department": "Bld21 Inbound", "shipTo": "WH-BLD21C"}, {"building": "Building 21", "department": "Consumables", "shipTo": "B21-PACKBC"}, {"building": "Building 21", "department": "Factory supply", "shipTo": "CLE21-CABN"}, {"building": "Building 21", "department": "Field Service Hub", "shipTo": "NL15C"}, {"building": "Building 21", "department": "Mature Products & Services", "shipTo": "CLE21-MPSC"}, {"building": "Building 21", "department": "Toolcabin", "shipTo": "CLE21-T21A"}, {"building": "Building 30", "department": "Motion", "shipTo": "B30-MOASSY"}, {"building": "Building 30", "department": "Motion", "shipTo": "B30-MO-LSM"}, {"building": "Building 58", "department": "Scrap", "shipTo": "BLD58-SCRP"}, {"building": "Building 58", "department": "Supply/Consumables", "shipTo": "BLD58C"}, {"building": "Building 9", "department": "D&E/Chemicals/Other", "shipTo": "DESK9C"}, {"building": "HQ Pack", "department": "Return to Manufacturer (RTM)", "shipTo": "B5L-RTMC"}, {"building": "Weert 1", "department": "Reverse Logistics / Re-use parts", "shipTo": "WH-WEERTC"}, {"building": "Weert 2", "department": "Service Warehouse", "shipTo": "NL10C"}, {"building": "Weert 1A", "department": "Reverse Logistics / Re-use parts", "shipTo": "WH-WEERT1A"}, {"building": "Weert 1A", "department": "SCRAP", "shipTo": "WEERT1A SCRAP"}, {"building": "Weert 1B", "department": "Replenishment Hub", "shipTo": "WH-WEERT1B"}, {"building": "WH-DC8", "department": "DC8", "shipTo": "DC8 - ASML"}, {"building": "WH-DC8", "department": "DEFA TOOLS", "shipTo": "DC8 DEFA TOOLS"}, {"building": "B23-DEC", "department": "Cleanroom", "shipTo": "BIC1 - BLD23"}, {"building": "Building 21", "department": "Silver Forum", "shipTo": "Bld. 21 MPS", "sourceCode": "WH21-MPSC"}, {"building": "Building 30", "department": "Motion", "shipTo": "B30-MOTION"}, {"building": "Weert 2", "department": "Key sight", "shipTo": "KEYSIGHT", "label": "Weert 2 — Key sight"}, {"building": "Weert 2", "department": "FOR PWO", "shipTo": "Tools Department", "sourceCode": "DHL.TOOLSC"}, {"building": "Weert 2", "department": "ASML Service Operations", "shipTo": "NL05C", "label": "NL05 Weert"}, {"building": "B23 - BIC1", "department": "ASML Trading BV parts", "shipTo": "NL05C", "label": "NL05 Eindhoven / BIC"}]'::jsonb) r
where w.slug='delivery-ops-5l' on conflict do nothing;

do $$ begin
 if to_regprocedure('public.rls_auto_enable()') is not null then
  revoke execute on function public.rls_auto_enable() from public,anon,authenticated;
 end if;
end $$;

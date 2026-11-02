create or replace function transport_private.operator_api(p_workspace uuid,p_action text,p_payload jsonb) returns jsonb
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
  if p_payload ? 'palletIds' and (jsonb_typeof(p_payload->'palletIds')<>'array' or jsonb_array_length(p_payload->'palletIds') not between 1 and 500) then raise exception 'Select 1–500 pallet IDs'; end if;
  mid:='LOAD-'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,12));
  select * into p from public.to_pallets x where workspace_id=p_workspace and status='finalised' and collected_at is null
   and transport_private.building_key(destination->>'building')=transport_private.building_key(p_payload->>'building')
   and (not p_payload ? 'palletIds' or p_payload->'palletIds' ? x.id)
   and not exists(select 1 from public.to_manifest_pallets i where i.workspace_id=x.workspace_id and i.pallet_id=x.id and i.released_at is null)
   order by created_at limit 1;
  if p.id is null then raise exception 'No unassigned finalised pallets for this building'; end if;
  insert into public.to_manifests(workspace_id,id,building,origin) values(p_workspace,mid,p.destination->>'building',p.origin);
  insert into public.to_manifest_pallets(workspace_id,manifest_id,pallet_id,pallet_revision,snapshot)
   select p_workspace,mid,x.id,x.revision,d.snapshot from public.to_pallets x join public.to_documents d
    on d.workspace_id=x.workspace_id and d.kind='pallet' and d.reference_id=x.id and d.revision=x.revision
   where x.workspace_id=p_workspace and x.status='finalised' and x.collected_at is null
    and transport_private.building_key(x.destination->>'building')=transport_private.building_key(p.destination->>'building')
    and (not p_payload ? 'palletIds' or p_payload->'palletIds' ? x.id)
    and not exists(select 1 from public.to_manifest_pallets i where i.workspace_id=x.workspace_id and i.pallet_id=x.id and i.released_at is null);
  if exists(select 1 from public.to_manifest_pallets i join public.to_pallets x on x.workspace_id=i.workspace_id and x.id=i.pallet_id
   where i.workspace_id=p_workspace and i.manifest_id=mid and x.origin is distinct from p.origin) then raise exception 'Separate loads are required for different origins'; end if;
  select count(*) into total from public.to_manifest_pallets where workspace_id=p_workspace and manifest_id=mid;
  if p_payload ? 'palletIds' and total<>jsonb_array_length(p_payload->'palletIds') then raise exception 'Selected pallets are unavailable or have different destinations'; end if;
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


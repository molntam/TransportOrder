do $$
declare
  operator_email text := 'REPLACE_WITH_YOUR_EMAIL';
  operator_id uuid;
  v_workspace_id uuid;
begin
  if operator_email = 'REPLACE_WITH_YOUR_EMAIL' then
    raise exception 'Replace REPLACE_WITH_YOUR_EMAIL with your confirmed Supabase Auth account email';
  end if;
  select id into strict operator_id from auth.users
    where lower(email)=lower(operator_email) and email_confirmed_at is not null;
  select id into strict v_workspace_id from public.to_workspaces where slug='delivery-ops-5l';
  insert into public.to_members(workspace_id,user_id,role)
    values(v_workspace_id,operator_id,'admin')
    on conflict (workspace_id,user_id) do update set role='admin';
  insert into public.to_events(workspace_id,action,reference_id,actor_kind,detail)
    values(v_workspace_id,'Administrator provisioned',operator_id::text,'system','{"method":"manual SQL bootstrap"}');
end $$;

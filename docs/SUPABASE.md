# Shared shipment backend

This backend is the next layer for TransportOrder. The desktop app in v0.5 still saves locally. Creating these tables does not upload local workspaces, change printing or activate phone scanning. No SAP transaction rows are seeded.

## Apply the setup

The project is `shipment-tracking-prototype`, ref `cwwpuapvgwoelhpwserm`, in Ireland (`eu-west-1`). Its API URL and workspace slug are recorded in `supabase/project.json`; they are not secrets.

Run the generated SQL file in `supabase/migrations/` once in the Supabase SQL Editor. Run it as one transaction if your SQL client does not already provide transactional execution. The setup creates the Delivery Operations 5L workspace and the 28 current destination presets. Actual dock schedules remain empty until entered. It also restricts external execution of the standard `rls_auto_enable()` event-trigger function when present; it does not remove the event trigger.

Create an operator in **Authentication → Users → Add user → Create user**, with your chosen email/password. Confirm the account. Creating a user is separate from workspace access: nobody becomes an administrator automatically.

To provision the first administrator, replace the email placeholder in `supabase/bootstrap_operator.sql`, then run that file in the SQL Editor. It looks up the existing confirmed Auth account; it never creates an account, chooses an email or sends an invitation. Keep populated bootstrap copies and credentials out of the repository. Later membership changes use the administrator-only `set_member` action.

The desktop integration will use a publishable API key plus each operator's Supabase Auth access token. No secret/service-role key belongs in the desktop app, driver page or public repository. Disable public sign-up for an invitation-only operator rollout; workspace policies already deny accounts without explicit membership. Auth email delivery, sign-in redirects and the final driver website domain are configured during client integration.

## Data model

| Table | Purpose |
|---|---|
| `to_workspaces`, `to_members` | Warehouse workspace and explicit admin/operator/viewer membership |
| `to_destinations`, `to_dock_slots` | Destination directory and weekday Netherlands arrival windows |
| `to_imports` | Immutable batches of parsed SAP data and import metadata |
| `to_pallets`, `to_forms`, `to_material_lines` | Current pallet/form state, exact text DN/HU/12NC and decimal quantities |
| `to_documents` | Immutable completed form, pallet and manifest snapshots |
| `to_manifests`, `to_manifest_pallets` | Planned truck contents, reservations and actual scan/pickup/delivery timestamps |
| `to_events` | Append-only operator/driver/system activity through controlled actions |
| `transport_private.driver_links` | Hashed, expiring and revocable manifest capabilities; never exposed as a table |

All application tables have RLS. Explicit workspace members can read their workspace's public tables. Anonymous clients cannot list or directly write tables. Even operators cannot directly overwrite history or change statuses through table writes: writes use the controlled APIs below. Membership administration requires an administrator. An anonymous Auth account does not gain access merely by having the authenticated role.

IDs from the desktop are retained (`P-…`, `TO-…`, text DNs/HUs with leading zeros). The database generates manifest IDs. Each resource is scoped by workspace. Current material lines are indexed by HU/DN and completed active HUs are unique across pallets. Omitted forms are retained as removed records; their prior documents remain available. Unassigned draft forms currently remain in the local desktop workspace until assigned to a pallet.

## Operator API

POST `/rest/v1/rpc/transport_operator`, with the publishable key in `apikey` and the signed-in user's JWT in `Authorization: Bearer ...`:

```json
{
  "p_workspace": "workspace-uuid",
  "p_action": "create_manifest",
  "p_payload": {"building": "Building 21"}
}
```

| Action | Payload |
|---|---|
| `save_pallet` | `pallet`, `forms`, `expectedRowVersion` (0 for a new pallet) |
| `reopen_pallet` | `id`, `expectedRowVersion`, `reason` |
| `create_manifest` | `building`; includes all unassigned finalised pallets for that building |
| `cancel_manifest` | `id`, `expectedRowVersion`, `reason` |
| `rotate_driver_link` | `id`, `expectedRowVersion`; revokes the previous link immediately |
| `set_dock_slots` | `slots`: array of `{building, days, start, end}`; days 0–4 mean Monday–Friday |
| `import_source` | `kind`, `filename`, `data`: parsed import object with `rows` |
| `set_member` | Administrator only: `userId`, `role` (`admin`, `operator`, `viewer`, or `remove`) |

`save_pallet` accepts the current desktop pallet and active form objects. Complete forms require a positive finite quantity and meaningful row identification. Forms must match the pallet's destination/origin and cannot mix SAP ship-to codes. Finalised pallets require all forms complete. The current desktop SAP parser/resolver remains responsible for SAP-specific routing, quantity aggregation and override review before publishing; the database does not invent missing SAP fields or silently reinterpret imports.

`revision` is the immutable print revision; `row_version` is a separate concurrency counter. A new open pallet starts at print revision 0, and each finalisation increments it. Editing/reopening requires the current row version. Finalised pallets cannot be overwritten, and reserved/collected pallets cannot be reopened. A completed form revision cannot be replaced with different content. Requests serialize on the workspace row so creating manifests, scanning and editing cannot race into inconsistent reservations. Independent workspaces do not share that lock.

Creating or rotating a manifest returns a 64-character `driverToken` once. Store it only where needed to produce/reprint its QR; it cannot be recovered from the hash. Rotating after losing the token invalidates previously printed manifest links. Driver links expire after seven days.

## Driver API

POST `/rest/v1/rpc/transport_driver` with the publishable `apikey`. A driver account/JWT is not required; the manifest's unpredictable bearer token is the credential:

```json
{
  "p_token": "token-from-the-manifest-link",
  "p_action": "scan",
  "p_payload": {"code": "TO:PALLET:P-EXAMPLE:1"}
}
```

| Action | Payload / behavior |
|---|---|
| `get` | Scoped manifest, pallet IDs/revisions, DN/HU/quantity and loading progress |
| `scan` | `code`; rejects wrong building, wrong manifest, old QR and collected pallets; duplicates do not add progress |
| `unscan` | `palletId`, `reason`; correct an accidental scan before pickup |
| `confirm_pickup` | `driver`, `vehicle`, and `reason` for a partial pickup |
| `confirm_delivery` | Matching destination `building` and a `receiver` name; only collected pallets are delivered |

The response excludes operator remarks, import tables, other manifests and private token records. QR tokens should go in the hosted driver's URL fragment, not query strings or logs. The driver page must read the fragment and send the token in the RPC body. Pallet QRs contain only pallet ID/revision; possession of a pallet ID alone does not open a driver session.

Manifest membership remains immutable. Pickup marks only scanned pallets collected and releases all reservations. Unscanned pallets remain ready for another truck. Cancelling requires a reason, releases reservations and revokes links. Original manifests retain planned contents; actual pickup/delivery is recorded separately. Driver names and receiver names are self-reported, not verified identity or a digital signature. The same bearer link authorises collection and delivery for its manifest during its lifetime.

The public RPCs are security invoker wrappers. Narrow privileged implementations live in the unexposed `transport_private` schema with a fixed empty search path, explicit function grants and either a current membership check or a hashed capability check. Private helper functions are not generally executable. Do not add `transport_private` to the Data API exposed schema list.

## Tests and rollout

Developer checks:

```bash
npm ci
npm run test:database
python -m unittest discover -s tests -q
node tests/ui-smoke.cjs
```

The database test uses real PostgreSQL 17 through PGlite, including pgcrypto, the exact migration, SQL functions and roles. It stubs only Supabase's Auth schema/helper locally. It tests access boundaries, quantities, routes, duplicate HUs, reservations, immutable revisions, partial/full pickup, cancellation, token rotation, stale QRs, delivery and atomic rollback after errors. It is not a live Supabase Auth/PostgREST, multi-connection concurrency or phone-camera test. After cloud application, run Supabase security/performance advisors and verify REST calls with an operator JWT and an anonymous capability before enabling clients.

Next client work: operator sign-in, publishing/migrating local records, conflict-aware shared reads, hosted HTTPS driver UI and QR link configuration. Local files must not be bulk uploaded until explicitly selected by the operator. Existing local QRs are identifiers/loopback links and need reprinting with the hosted manifest link after integration.

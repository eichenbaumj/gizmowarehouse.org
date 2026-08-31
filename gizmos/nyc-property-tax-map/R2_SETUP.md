# Cloudflare R2 setup for the NYC Property Tax map

> **Looking for the canonical pattern for any new gizmo?** Read
> `tools/HOSTING_DATA.md` first — that doc is the source of truth for how
> the warehouse hosts big data files. This file is the historical replay of
> the 2026-04 first-time setup, kept for reference.

Cloudflare account: `joe@group17a.com` (account ID in `.env.local`
at the repo root, gitignored).

This deploys the citywide PMTiles + NTA aggregates + medians JSON to R2 so
the gizmo-warehouse map can fetch them via HTTP range requests. R2 is free
up to 10 GB and free egress, vs Lovable's ~25 MB asset cap that won't fit
our 103 MB tile file.

## What got created

- **Bucket:** `gizmo-warehouse-data` (its own bucket, separate from other projects)
- **Public URL:** `https://data.gizmowarehouse.org` — a custom domain on
  `group17a.com`, attached to the bucket via Cloudflare → R2 → Custom
  Domains. We do **not** use the bucket's `pub-*.r2.dev` URL because
  individual `*.r2.dev` hostnames get classification-blocked by OpenDNS /
  Cisco Umbrella / Quad9 / corporate DNS filters. See
  `tools/HOSTING_DATA.md` § "Why a custom domain" for the full story.
- **API token:** scoped to that bucket only, Object Read & Write
  (name + credentials in `.env.local`)
- **CORS:** GET/HEAD with Range from any origin, ETag exposed
- **Files uploaded** (all under prefix `nyc-property-tax/`):
  - `parcels.pmtiles` (~103 MB)
  - `nta-aggregates.geojson` (~5 MB)
  - `stats.json` (citywide medians for legend)
  - `class-medians.json` (per-class ETR medians)

## Step 1 — Create the bucket ✅

1. Cloudflare dashboard sidebar → **R2 Object Storage** → **Overview**.
2. Click blue **+ Create bucket** (top right).
3. Name: `gizmo-warehouse-data`. Location: `Automatic`. Storage class: `Standard`.
4. Click **Create bucket**.

## Step 2 — Attach a custom domain ✅

This is the load-bearing step. The bucket's auto-generated `pub-*.r2.dev`
URL is not safe for public traffic (see `tools/HOSTING_DATA.md`).

1. Inside the bucket → **Settings** tab → scroll to **Public Access** →
   **Custom Domains** → **Connect Domain**.
2. Enter `data.gizmowarehouse.org`. Click **Continue**.
3. Cloudflare auto-creates the CNAME record on the `group17a.com` zone
   (because the zone is on the same account).
4. Wait ~30 seconds for the TLS cert to provision. The status badge flips
   from "Pending" to "Connected" and the cert turns green.
5. Verify: `curl -I https://data.gizmowarehouse.org/nyc-property-tax/stats.json`
   should return `HTTP/2 200`.

> The Public Development URL (`pub-XXXXXX.r2.dev`) is left enabled but the
> warehouse never references it. Treat it as legacy.

## Step 3 — Configure CORS ✅

1. Same Settings tab → scroll to **CORS Policy** → click **+ Add**.
2. The editor opens with an example. Replace its full contents with:

   ```json
   [{"AllowedOrigins":["*"],"AllowedMethods":["GET","HEAD"],"AllowedHeaders":["*","Range"],"ExposeHeaders":["Content-Range","Content-Length","ETag"],"MaxAgeSeconds":86400}]
   ```

   The Cloudflare editor has a Monaco-style auto-bracket that breaks
   character-by-character typing — paste the JSON in one shot.
3. Click **Save**.

CORS is bucket-level, so any future gizmo's prefix in the same bucket gets
this rule for free.

## Step 4 — Mint an API token ✅

1. Sidebar → **R2 Object Storage** → top-right **Manage API Tokens** (or
   navigate directly to `/r2/api-tokens`).
2. Click **Create Account API token** (the recommended/production choice;
   not the User token).
3. Name the token after the bucket it grants (record it in `.env.local`).
4. Permissions: **Object Read & Write**.
5. Specify bucket(s): **Apply to specific buckets only** → select
   `gizmo-warehouse-data`.
6. TTL: `Forever`. (Can revoke from the same page later.)
7. Click **Create Account API Token**.
8. **Copy the three values** Cloudflare shows on the success page — they
   are not displayed again:
   - **Access Key ID**
   - **Secret Access Key**
   - **S3 endpoint URL** (`https://<account>.r2.cloudflarestorage.com`)

   These get pasted into `.env.local` (gitignored) at the repo root.

## Step 5 — `.env.local` ✅

The repo's `.gitignore` already covers `.env.local`. Format:

```
R2_ACCOUNT_ID=<from the Cloudflare dashboard>
R2_BUCKET=gizmo-warehouse-data
R2_PUBLIC_URL=https://data.gizmowarehouse.org
R2_S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
```

If credentials ever leak, revoke at:
`https://dash.cloudflare.com/<account-id>/r2/api-tokens`

## Step 6 — Upload data ✅

```
python3 gizmos/nyc-property-tax-map/pipeline/06_upload_r2.py
```

Reads `.env.local`, uses boto3 (auto-installs if missing), uploads the four
files. Re-running is idempotent (overwrites). Cache headers set to
one-year-immutable since we'll change filenames if data changes.

## Step 7 — Point the frontend at R2 ✅

In `src/config/nycPropertyTaxMap.ts`, the URLs are:

```ts
ntaGeoJsonUrl: "https://data.gizmowarehouse.org/nyc-property-tax/nta-aggregates.geojson",
parcelsPmtilesUrl: "https://data.gizmowarehouse.org/nyc-property-tax/parcels.pmtiles?v=3",
statsUrl: "https://data.gizmowarehouse.org/nyc-property-tax/stats.json",
classMediansUrl: "https://data.gizmowarehouse.org/nyc-property-tax/class-medians.json",
```

Then `npm run dev` and verify tiles load (network tab shows range requests
to `data.gizmowarehouse.org`).

## Future updates

When the pipeline regenerates data:
1. Run stages 03 → 04 → 05 (build new tiles).
2. Run `06_upload_r2.py` to push.
3. If filenames stayed the same and you've set `Cache-Control: immutable`,
   force a refresh by appending `?v=<timestamp>` to URLs — or change the
   filename. Easier path: just change the filename in stage 05 (e.g.
   `parcels-FY26.pmtiles`) and update the config URL.

## History — why we migrated off `pub-*.r2.dev`

Original setup (2026-04-29) used `https://pub-<hash>.r2.dev`,
the auto-generated R2 public-development URL. That worked for about three
days, then OpenDNS / Cisco Umbrella began returning their malware-block IP
(`146.112.61.110`) in response to DNS queries for that hostname,
serving a self-signed cert. Browsers refused the cert with
`net::ERR_CERT_AUTHORITY_INVALID` and the map went dark for everyone behind
a filtered resolver — including Joe's home network (Spectrum, which
forwards to OpenDNS by default).

This is a known abuse-mitigation pattern: R2 public-development URLs are
flagged individually based on content classification. The fix is to attach
a custom domain on a zone we control (here, `data.gizmowarehouse.org` on the
`group17a.com` Cloudflare zone). Per-bucket abuse classification doesn't
apply to user-owned domains, and the cert chains to a trusted CA, so the
map loads everywhere.

The migration was a five-minute dashboard change (Step 2 above) plus a
one-line edit to four URLs in the frontend config. The bucket contents
didn't move; only the hostname users hit changed.

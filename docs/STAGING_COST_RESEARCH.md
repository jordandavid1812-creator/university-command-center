# Milestone 5A — private staging cost and provider research

Researched **11 November 2026 (Africa/Lagos)** using the linked official sources.
USD list prices before tax, FX/card fees, support and engineering time. No accounts
were created, services bought, emails sent or infrastructure provisioned. Provider
prices/limits can change; re-quote the chosen region and complete bundle before any
purchase. Published prices are not proof of compatibility with this project's roles.

## Evidence labels

- **Published:** a value visible in the official source when reviewed; not a signed quote.
- **Calculated:** arithmetic from published rates and explicit assumed usage.
- **Estimate/unverified:** planning allowance or historical example; not a current quote.
- No free-tier credit, educational discount or annual contract is assumed eligible.

## Current candidate prices

| Item | Observed price / limit | Evidence and decision impact |
| --- | --- | --- |
| DigitalOcean Basic VM, 1 vCPU / 2 GiB / 50 GiB SSD | **$12/month published** | [Official Droplet table](https://www.digitalocean.com/pricing/droplets). Entry synthetic staging candidate, not a demonstrated capacity guarantee. A 512 MiB $4 VM exists but is not recommended for Django plus PG17/hash work. |
| DigitalOcean Basic VM, 2 vCPU / 4 GiB / 80 GiB SSD | **$24/month published** | Same table. More headroom if profiling shows 2 GiB insufficient; still a single failure domain and operator-managed. |
| Droplet daily image backups | **30% of VM price published**; weekly 20% | [Official backup pricing](https://docs.digitalocean.com/products/backups/details/pricing/). Daily: calculated $3.60 on $12 or $7.20 on $24. VM images are not the sole database backup/restore strategy. |
| DigitalOcean managed PostgreSQL Standard, 1 GiB / 1 vCPU | **$15.15/month published** at minimum table configuration | [Official managed DB table](https://www.digitalocean.com/pricing/managed-databases). Disk is metered/listed with a 10 GiB minimum; confirm checkout's included storage and avoid double-counting. PG17 is advertised by [the product page](https://www.digitalocean.com/products/managed-databases-postgresql). |
| Render always-on Django service + small Postgres | **~$13/month historical vendor example, not a verified current bundle quote** | [Render's cost article](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses) explicitly dates this example July 2026, excludes storage/bandwidth. Do not label it today's guaranteed total. |
| Render current plan names / PG17 | Web `0.5c-512mb` (legacy Starter); DB `0.1c-256mb` (legacy Basic-256mb) | [Current compute-plan docs](https://render.com/docs/compute-plans); [creation docs](https://render.com/docs/postgresql-creating-connecting) list major versions 13–18. Obtain live plan rates. Paid PG includes recovery features; exact retention/tier must be checked. |
| Neon Launch PostgreSQL | **$0.106/CU-hour + $0.35/GB-month published**, usage-based | [Official pricing](https://neon.com/pricing). For 0.25 CU active 8 h/day ×30 days and 1 GB: **$6.71 calculated**. Always-on 0.25 CU ×730 h plus 1 GB: **$19.70 calculated**. History/branches/egress may add charges. Sleeping saves money but affects latency. |
| Neon Free | **$0**, 100 CU-hours/project/month and 1 GB published | Same pricing source. Useful only for an authorized synthetic compatibility exercise; not an assumed reliability/backup plan. [PG17 support announcement](https://neon.com/blog/postgres-17). Do not replace Django authentication with vendor auth. |
| Resend Free transactional | **$0**, 3,000/month and 100/day UTC, sent + received count | [Official quota docs](https://resend.com/docs/knowledge-base/account-quotas-and-limits). Suitable for bounded controlled-mailbox tests after approval; a daily hard limit can break a recovery escape hatch. Paid quote not relied on here. |
| Postmark Basic at 10,000-email slider position | **$15/month published**, extra $1.80/1,000 | [Official pricing](https://postmarkapp.com/pricing). Pro shows $16.50 at this selection; Basic lists 45-day retention. Confirm monthly volume, recipient/content retention, account approval and token-URL privacy before selection. Free testing is only 100/month. |
| Backblaze B2 off-site encrypted objects | **$6.95/TB/month published**, byte-hour billing | [Official pricing](https://www.backblaze.com/cloud-storage/pricing). 20 GB at $0.00695/GB-month is **~$0.14 calculated storage only**; retained versions and restore traffic change usage. Budget $1–3/month as an **estimate**, not a minimum bill or a free-egress promise. |
| Tailscale private reviewer access | Personal **$0 up to 6 users**; Standard **$8/user/month published** | [Official pricing](https://tailscale.com/pricing). Confirm organizational/education eligibility; do not assume a personal plan covers this project. Three Standard users add **$24/month calculated**. VPN access does not replace Django authentication. |
| Sentry error reporting (optional) | Developer **$0, one user**; Team **$29/month monthly or $26/month annual equivalent** published | [Official pricing](https://sentry.io/pricing/). Included volume/overages apply. Do not buy an annual commitment by treating $26 as month-to-month. External payload/retention review required; disable replay and sensitive request capture. |
| Domain/DNS and independent security work | **Unverified estimates**: domain $10–25/year; external tester requires quote | No registrar/TLD/tester selected. DNS may be included with an existing domain. Pentest labor and operator time are **not included** in the hosting totals below. |

The Render free database expires and its free web service sleeps; its article's
free-tier details make it inappropriate as the assumed durable recovery/staging
acceptance environment. No vendor price here promises uptime or regional capacity.

## Architecture choices and compatibility gates

### A. One private VM: provisional recommendation for a tiny synthetic staging lab

Run Django's reviewed production WSGI server, reverse proxy and PostgreSQL **17** on
one VM, private ingress only, off-site encrypted DB backups. Lowest component count
and full control of the unusual security role/extension setup. The owner must assign
someone to patch OS/Postgres, monitor disk/memory, manage certificates and restore.
A cheaper VM is not cheaper overall if nobody can operate it safely.

**Gate:** an approved future staging settings/WSGI/static-assets implementation,
VM sizing test, private access and backup drills. No HA claim; a host failure causes
outage until restoration. No real student data during 5A's proposed lab stage.

### B. VM Django + managed PG17: lower DB operations, higher cost

A $12 VM plus the $15.15 DB table minimum is **$27.15 calculated base compute**, before
backup/storage/transport/network fees. Avoid a public DB: DigitalOcean's
[management docs](https://docs.digitalocean.com/products/databases/postgresql/how-to/manage-users-and-databases/)
say clusters are publicly accessible by default until trusted sources are configured.
Require private networking/source restrictions and TLS certificate verification.

**Gate:** provider admin role must be able to create the exact restricted app logins
and offline owner/migrator, provision pgcrypto in the private schema and preserve
forced RLS. A provider-generated admin connection is never an app credential.

### C. Managed Django (Render) + managed DB (Render/Neon): investigate, do not assume

Less VM maintenance, but app services may expose public origins, each email worker
adds billable compute, and cheapest tiers may not provide private networking or
suitable access control. An access gateway is insufficient if the origin remains
reachable around it. Render service+DB must be quoted together; Neon bills separately.

[Neon's role documentation](https://neon.com/docs/manage/roles) says Console/API
roles receive neon_superuser membership, whereas SQL-created roles use ordinary
Postgres grants. That distinction matters: this project's runtime/auth roles reject
role memberships/ownership/elevated flags. SQL provisioning **may** satisfy the
contract; this is not a tested compatibility assertion. Use no vendor auth/RLS
replacement. Prefer direct or reviewed transaction pooling, never statement pooling.

### Shared provider proof required before selection

In a separately authorized disposable PG17 instance, prove:

1. Actual server version 17; pgcrypto available and provisionable in `ucc_crypto`
   without a conflicting pre-installed extension. Existing migrations deliberately
   refuse takeover of a conflicting extension. No patch weakening that check.
2. Offline DBA/provisioning ability; non-owner NOINHERIT, no-membership runtime/auth
   LOGINs; non-superuser owner/migrator; required schema/function ownership and grants.
3. Existing role-boundary checks, plus approved PR #26 corrections, pass on actual
   provider connections. Include PG17 MAINTAIN in drift tests, not PG16-only evidence.
4. FORCE RLS and signed transaction/backend context survive direct SQL attempts and
   connection reuse. No default privileged URL, superuser role or vendor-auth shortcut.
5. TLS verify-full, connection/idle/time limits, pooling behavior, private ingress,
   backup export/restore, region and deletion/retention requirements meet acceptance.

If a provider cannot satisfy these, reject that configuration or obtain a separately
reviewed architecture decision. Do not disable the project's checks to fit a cheap SKU.

## Small staging budget examples — estimates, not purchase authorization

Assumptions: one environment, 1–3 reviewers, low synthetic traffic, owned domain if
available, no extra worker VM initially, off-site objects ~20 GB, basic sanitized
monitoring on the VM. Delivery transport/worker implementation still needs review.

| Scenario | Monthly planning total | Composition and exclusions |
| --- | --- | --- |
| Lean private lab, eligible free access + controlled free mail | **$17–22 estimated** | $12 VM + $3.60 daily image backup + $1–3 off-site allowance + $0–3 monitoring/DNS allowance. Free mail/access eligibility and capacity not guaranteed. Human ops excluded. |
| Same lab with Postmark Basic | **$32–37 estimated** | Above + $15 published email rate. Privacy/delivery approval still required. |
| Above with 3 paid Standard VPN users | **$56–61 estimated** | Add $24; no assumption of a free organization plan. |
| VM + managed PG17 + paid mail, eligible free access | **$47–55 estimated** | $12 VM + $15.15 DB minimum + $3.60 VM image backups + $15 email + $1–3 off-site, plus rounding/storage/DNS headroom. Confirm managed storage bill. |
| 4 GiB VM version of paid-mail lab | **$48–53 estimated** | $24 VM + $7.20 images + $15 mail + $1–3 off-site + modest monitoring/DNS allowance. |

Optional Sentry Team adds $29/month month-to-month, plus any paid access seats/usage;
external penetration testing adds an **unquoted separate** cost. Any dedicated queue/
worker, managed cache, extra staging clone or restore VM increases the budget. Use
short-lived restore test VMs only after spend approval; do not silently add a second
always-on environment. Spend alerts are not a hard cap: require manual resizing and
a documented shutdown plan; confirm the provider's actual cap/overage behavior.

## Owner decisions before procurement

Choose budget cap and payer; region/data-residency and terms; VM operator vs managed
service; VPN/access plan and reviewer roster; domain and DNS control; mail provider/
message retention and secondary recovery procedure; backup RPO/RTO and storage;
monitoring privacy/retention; security-testing scope/budget. Revalidate all prices
and compatibility evidence at that decision. This document authorizes none of them.

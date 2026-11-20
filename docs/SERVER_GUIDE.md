# Server guide: putting the website online

This guide is for the owner. It sets up one small cloud server that runs the database, the
website and Caddy (which handles HTTPS). Claude will give you the exact commands with your own
domain filled in when you are ready. This page is the reference.

The website refuses to start until the email lines in step G are added.

## What it costs

| Item | Cost |
| --- | --- |
| Domain name (e.g. from Namecheap or Cloudflare) | about $10–15 a year |
| DigitalOcean server: Ubuntu 24.04, Basic, 2 GB memory | about $12 a month ($6 for 1 GB works for a small trial) |
| DigitalOcean weekly server backups (optional extra copy) | about 20% of the server price |

## A. Buy the domain

Buy one name, for example `ucc-student.com`. Use it only for this website (the website tells
browsers to always use HTTPS on it and all its subdomains).

## B. Create the server

1. On your Windows computer, make an SSH key (press Enter at every question):

   ```powershell
   ssh-keygen -t ed25519
   ```

2. Show the public half, and copy what it prints:

   ```powershell
   Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
   ```

3. On DigitalOcean: **Create → Droplets**. Choose region **London** or **Frankfurt**,
   image **Ubuntu 24.04 (LTS)**, size **Basic → Regular → 2 GB**, and under
   **Authentication** choose **SSH Key** and paste the key. Create it and copy its **IPv4 address**.

## C. Point the domain at the server

In your domain provider's **DNS** settings, add an **A record**: host `@`, value = the
server's IPv4 address. It can take a few minutes to an hour to work.

## D. Connect and protect the server

```powershell
ssh root@SERVER-IP-ADDRESS
```

Then, on the server:

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
```

Ubuntu installs security updates automatically.

## E. Install Docker and Git

```bash
apt-get update && apt-get install -y docker.io docker-compose-v2 git
```

## F. Get the code (read-only)

The server gets a key that can only **read** this one repository:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/ucc_deploy && cat ~/.ssh/ucc_deploy.pub
```

On GitHub: the repository → **Settings → Deploy keys → Add deploy key**, paste it, and leave
**Allow write access** unticked. Then:

```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/ucc_deploy" git clone git@github.com:jordandavid1812-creator/university-command-center.git
cd university-command-center
```

## G. Create the private settings (once)

```bash
python3 deploy/make_secrets.py --host YOUR-DOMAIN --email YOUR-EMAIL
```

This makes `deploy/secrets/` with new random passwords and keys, readable only by the server's
administrator. It never prints them and refuses to overwrite them. Copy that folder somewhere
private (not GitHub, not chat) — without it you cannot reach the database.

Then add the website's email account (a new Gmail account with a Google app password; see
VERCEL_GUIDE.md "Email account") to `deploy/secrets/web.env` with `nano deploy/secrets/web.env`,
adding these two lines with your values:

```
UCC_EMAIL_ADDRESS=your.site.address@gmail.com
UCC_EMAIL_APP_PASSWORD=the16letterpassword
```

## H. Start everything

```bash
docker compose -f deploy/compose.yml build
docker compose -f deploy/compose.yml up -d --wait db
docker compose -f deploy/compose.yml run --rm migrate
docker compose -f deploy/compose.yml up -d
```

Open `https://YOUR-DOMAIN`. The first visit can take a minute while Caddy gets the certificate.

## I. Tell classmates

Anyone with an email address can sign up. The site emails them a 6-digit code that works for
5 minutes; they type it in, and their account is ready. Share your site address.

## Everyday commands (run in `university-command-center` on the server)

| Task | Command |
| --- | --- |
| See if it is running | `docker compose -f deploy/compose.yml ps` |
| Recent website messages | `docker compose -f deploy/compose.yml logs --tail 50 web` |
| Update to the newest merged code | `git pull` then the four commands in step H |
| Stop the website | `docker compose -f deploy/compose.yml down` |

**Never add `-v` to `down`.** `down -v` deletes the database and every student's data.

## How it is protected

- Only Caddy is reachable from the internet (ports 80 and 443). It answers only for your
  domain, gets and renews the HTTPS certificate, redirects `http://` to `https://`, refuses
  requests over 11 MB, and replaces any visitor-supplied `X-Forwarded-For`.
- The website has no open port. It trusts forwarded headers only from Caddy's fixed internal
  address (`172.30.0.10`), runs as an unprivileged user on a read-only file system with no
  Linux capabilities, and checks every setting before it starts.
- The database is on an internal network with no internet and no way in from outside.
  The website logs in only as the restricted runtime and auth roles. Database updates run as
  a separate one-off `migrate` container with the migrator login, which the website never has.
- Secrets live only in `deploy/secrets/` on the server (ignored by Git, never in the image).

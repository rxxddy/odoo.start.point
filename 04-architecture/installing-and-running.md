---
description: From-source install, odoo.conf, odoo-bin, and a clean dev setup.
---

# Installing and running

A from-source checkout gives you a debugger, a git history you can bisect, and the freedom to run several versions side by side. This chapter sets up a development environment you can throw away and rebuild in ten minutes, and explains the three things that make a first run fail: Python version, PostgreSQL access, and the addons path.

## What you need

| Component | Odoo 16 | Odoo 17 | Odoo 18 |
|---|---|---|---|
| Python | 3.7 to 3.10 (3.10 recommended) | 3.10+ | 3.10+ |
| PostgreSQL | 12+ | 12+ | 12+ |
| wkhtmltopdf | 0.12.6 with patched Qt | same | same |
| Node (rtlcss, for right-to-left languages only) | optional | optional | optional |

Check the exact floor in `requirements.txt` and `setup/` of the branch you checked out; the supported range moves with each release and distribution packages lag. Treat the table as a starting point, not a contract.

wkhtmltopdf matters only for PDF reports. A missing or unpatched build does not stop the server; it produces PDFs without headers and footers, which is a confusing symptom to meet for the first time on someone else's machine.

## Layout on disk

Keep Odoo itself, your own addons, and the virtualenv in separate directories. Never put your modules inside the Odoo checkout: upgrading the checkout (`git pull`, branch switch) must not touch your code.

```
~/odoo/
  16.0/            # git clone --branch 16.0 --depth 1 https://github.com/odoo/odoo
  18.0/
  venv-16/
  venv-18/
  custom/          # your addons repositories
  conf/
    dev-18.conf
```

## Install

```bash
git clone --branch 18.0 --depth 1 https://github.com/odoo/odoo ~/odoo/18.0
python3 -m venv ~/odoo/venv-18
. ~/odoo/venv-18/bin/activate
pip install -U pip wheel
pip install -r ~/odoo/18.0/requirements.txt
```

On Debian-family systems, install the build dependencies first (`libpq-dev`, `libldap2-dev`, `libsasl2-dev`, `libxml2-dev`, `libxslt1-dev`, `libjpeg-dev`, `zlib1g-dev`), otherwise `psycopg2`, `python-ldap`, or `lxml` fail to compile. The failure surfaces halfway through `pip install`, and the error text points at a missing header, not at the package you need to install.

A shallow clone (`--depth 1`) is fast and fine for running. If you need `git blame` or `git log -S` on the framework, which you will, drop the flag or run `git fetch --unshallow` later.

## PostgreSQL role

Odoo refuses to run as the `postgres` superuser. Create a dedicated role that may create databases:

```bash
sudo -u postgres createuser --createdb --pwprompt odoo_dev
```

Without `--createdb` the database manager and `-d newdb -i base` fail with a permission error. Do not make the role a superuser. If a module needs an extension such as `unaccent` or `pg_trgm`, creating it once as `postgres` in `template1` is cleaner than widening the role. (Whether a given module needs one depends on the version and your configuration; check the log of the first install.)

## The configuration file

Every command line switch can live in a config file. Generate one from the current switches with `--save` (short `-s`), then edit it:

```bash
~/odoo/18.0/odoo-bin -c ~/odoo/conf/dev-18.conf -s \
  --addons-path=$HOME/odoo/18.0/addons,$HOME/odoo/custom/library \
  --db_host=localhost --db_user=odoo_dev --db_password=secret \
  --stop-after-init
```

A minimal `dev-18.conf`:

```ini
[options]
addons_path = /home/dev/odoo/18.0/odoo/addons,/home/dev/odoo/18.0/addons,/home/dev/odoo/custom/library
db_host = localhost
db_user = odoo_dev
db_password = secret
http_port = 8069
log_level = info
dbfilter = ^dev_.*$
list_db = True
```

Note the two core directories. `odoo/addons` holds `base` and a few framework modules; `addons` holds the rest. Leaving out `odoo/addons` makes the first run fail because `base` cannot be found. Copying `addons_path` from a generated config is the safest approach.

{% hint style="info" %}
Config keys use underscores (`db_host`). On the command line, most options accept both hyphens and underscores (`--db_host`, `--db-host`); the hyphenated form is the one the help output shows for newer options. When in doubt, run `odoo-bin --help`.
{% endhint %}

## First run

```bash
~/odoo/18.0/odoo-bin -c ~/odoo/conf/dev-18.conf -d dev_library -i base --without-demo=all --stop-after-init
~/odoo/18.0/odoo-bin -c ~/odoo/conf/dev-18.conf -d dev_library --dev=xml,reload
```

The first command creates the database, loads `base`, and exits. The second starts the server on `http://localhost:8069`. `--stop-after-init` is how you run installation and upgrade as a batch step; it is also the only sane way to run them in CI or a deploy script.

`--without-demo=all` skips demo data. Demo data is useful when you learn the standard apps and harmful when you want to see how your module behaves on a realistic database, because demo records hide missing-data bugs. Decide per database at creation time: the demo flag is recorded when modules are first installed, and flipping it later means recreating the database.

The login after `-i base` is `admin` / `admin`. Change it before the database is reachable from anywhere but your laptop.

## Multiple versions side by side

One virtualenv, one config file, and one database name prefix per version. A database created by 16 cannot be opened by 18 without a migration: the server sees modules with older versions and tries to upgrade them or fails. A `dbfilter` prefix (`dev16_`, `dev18_`) keeps the wrong server from listing the wrong databases.

## Pitfalls

{% hint style="warning" %}
Run the server as an unprivileged account, never as `root`. A stray `odoo-bin shell` as root writes filestore files that the service account cannot read afterwards.
{% endhint %}

- **Port already in use.** A forgotten server on 8069 makes the new one fail at bind time. `ss -ltnp | grep 8069` first.
- **`-u` without `-d`.** With no database selected, the update has nothing to act on; the server starts and waits. Always pass `-d` in scripts.
- **Wrong virtualenv.** The framework is run from the checkout, not installed. `pip list | grep -i odoo` should show nothing; an old `odoo` package in the venv can shadow the checkout.
- **Filestore location.** Attachments live outside the database, in `data_dir` (default under your user's local share directory). Copying only a database dump gives a copy with missing images and attachments. Set `--data-dir` explicitly for every instance.
- **Two instances, one database.** Two servers on the same database both run the crons. Never start a second dev server against a shared database without disabling crons (see [Workers, cron, and longpolling](workers-cron-and-longpolling.md)).

## Try it

```bash
# read-only: what does this build think its options are?
~/odoo/18.0/odoo-bin --help | head -40
# does the role connect, and what databases exist?
psql -U odoo_dev -h localhost -l
# after the first run, which modules are installed?
psql -U odoo_dev -d dev_library -c "select name, state, latest_version from ir_module_module where state='installed' order by name limit 10;"
```

# PythonAnywhere Deploy Notes

This project already supports two modes in `repairshop/settings.py`:

- Local development: SQLite is used when the PythonAnywhere MySQL variables are blank or missing.
- Production: MySQL is used when `PA_DB_HOST`, `PA_DB_USER`, `PA_DB_PASSWORD`, and `PA_DEFAULT_DB_NAME` are all present.

## Local development on this machine

Use the local `.env` file in the project root. It is already configured for SQLite.

Typical startup flow:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

That will use:

- `db.sqlite3` for the shared/default database.
- Additional SQLite files like `shop1_db.sqlite3` only if code accesses those tenant aliases.

## Production on PythonAnywhere

Do not store real production secrets in the repository.

Use one of these two approaches.

### Recommended: set real values in the PythonAnywhere WSGI file

Because `repairshop/settings.py` only loads `.env` values for keys that are not already in `os.environ`, values set in the WSGI file take precedence over any `.env` file.

In PythonAnywhere, open the WSGI configuration file for your web app and add your environment variables before `get_wsgi_application()` runs.

For your app, that file is:

```text
repairshopcloud_eu_wsgi.py
```

Example:

```python
import os
import sys

project_home = '/home/yourusername/RepairShop'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'repairshop.settings'
os.environ['DJANGO_SECRET_KEY'] = 'replace-with-real-secret'
os.environ['DJANGO_DEBUG'] = 'False'

os.environ['PA_DB_HOST'] = 'yourusername.mysql.pythonanywhere-services.com'
os.environ['PA_DB_PORT'] = '3306'
os.environ['PA_DB_USER'] = 'yourusername'
os.environ['PA_DB_PASSWORD'] = 'replace-with-real-db-password'
os.environ['PA_DEFAULT_DB_NAME'] = 'yourusername$repairshop_default'
os.environ['PA_SHOP1_DB_NAME'] = 'yourusername$shop1_db'
os.environ['PA_SHOP2_DB_NAME'] = 'yourusername$shop2_db'

os.environ['TENANT_DB_ALIASES'] = ''

os.environ['MOTORAPI_AUTH_TOKEN'] = 'replace-with-real-token'
os.environ['MOTORAPI_BASE_URL'] = 'https://v1.motorapi.dk'
os.environ['MOTORAPI_VERIFY_SSL'] = 'True'

os.environ['EMAIL_BACKEND'] = 'django.core.mail.backends.smtp.EmailBackend'
os.environ['EMAIL_HOST'] = 'smtp.yourprovider.com'
os.environ['EMAIL_PORT'] = '587'
os.environ['EMAIL_HOST_USER'] = 'replace-with-real-user'
os.environ['EMAIL_HOST_PASSWORD'] = 'replace-with-real-password'
os.environ['EMAIL_USE_TLS'] = 'True'
os.environ['EMAIL_USE_SSL'] = 'False'
os.environ['DEFAULT_FROM_EMAIL'] = 'invoice@yourdomain.com'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

If PythonAnywhere is already configured with the correct virtualenv in the Web tab, do not add manual `activate_this.py` logic. The Web tab virtualenv setting is the cleaner and more reliable approach.

Why this is safe:

- `git pull` updates tracked files only.
- Secrets in the PythonAnywhere WSGI file are outside your git repo.
- Even if a `.env` file exists in the project folder, the WSGI values win.

### Acceptable fallback: keep a production `.env` file on the server, but do not commit it

If you prefer, you can create `/home/yourusername/RepairShop/.env` directly on the server and fill it with real production values based on `.env.production.example`.

This usually survives `git pull` because:

- `.env` is ignored by `.gitignore`.
- An ignored, untracked file is not overwritten by a normal `git pull`.

Still, this is weaker than the WSGI approach because the file lives inside the app directory. It is better than committing secrets, but not as strong as keeping secrets outside the repo.

## Strongest pattern: load secrets from a file outside the repo

If you want production secrets in a file instead of directly in WSGI, place them outside the project directory, for example:

```text
/home/yourusername/.secrets/repairshop.env
```

Then read them in the WSGI file before Django starts:

```python
import os
import sys
from pathlib import Path

project_home = '/home/yourusername/RepairShop'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

secret_file = Path('/home/yourusername/.secrets/repairshop.env')
if secret_file.exists():
    for raw_line in secret_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'repairshop.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

That gives you these benefits:

- Secrets are not in git.
- Secrets are not in the project directory.
- Re-deploying code does not touch the secrets file.

## Deployment steps

After your code is on PythonAnywhere:

1. Create the MySQL databases in PythonAnywhere.
2. Add the production env values using the WSGI method or the external secrets-file method.
3. Create or update the virtualenv and install requirements.
4. Run migrations for the default database.
5. Reload the web app from the PythonAnywhere dashboard.

Typical commands in a PythonAnywhere Bash console:

```bash
cd ~/RepairShop
source /home/yourusername/.virtualenvs/repairshop-venv/bin/activate
pip install -r requirements.txt
# Important: Bash console does NOT automatically inherit env vars from the WSGI file.
# Export production DB vars here (or source a secrets file) before migrate.

# Verify you are targeting MySQL (not sqlite fallback) before running migrations:
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'], settings.DATABASES['default']['NAME'])"

# Apply shared-app migrations (including shops) on default:
python manage.py migrate --database=default

# Optional: confirm shops migrations are applied (0015 adds shop_profile.enabled_features):
python manage.py showmigrations shops --database=default

python manage.py collectstatic --noinput
```

### One-command deploy helper (recommended)

This repo now includes a guarded deploy script:

```bash
./deploy_pythonanywhere.sh
```

What it does:

- Loads secrets from `/home/yourusername/.secrets/repairshop.env` (or a path you pass in).
- Verifies Django is using MySQL (fails if it is still on sqlite fallback).
- Runs `migrate --database=default`.
- Shows `shops` migration status.
- Runs `collectstatic --noinput`.

Custom secrets path example:

```bash
./deploy_pythonanywhere.sh /home/yourusername/.secrets/repairshop.env
```

## Static files on PythonAnywhere

If the Django admin looks plain or unstyled in production, the usual cause is that static files are not mapped in the PythonAnywhere Web tab.

This project uses:

```text
STATIC_URL=/static/
STATIC_ROOT=/home/henrikhansen/RepairShop/staticfiles
MEDIA_URL=/media/
MEDIA_ROOT=/home/henrikhansen/RepairShop/media
```

After you run `python manage.py collectstatic --noinput`, add these mappings in the PythonAnywhere Web tab:

```text
URL: /static/
Directory: /home/henrikhansen/RepairShop/staticfiles
```

```text
URL: /media/
Directory: /home/henrikhansen/RepairShop/media
```

Then reload the web app.

Quick check:

- Open `/static/admin/css/base.css` in your browser on the live site.
- If it loads, admin CSS is being served.
- If it returns 404, the Web tab static mapping is missing or points to the wrong directory.

## Important note about tenant databases

This codebase currently marks `shops` as a shared app, so shared data migrates on `default` only.

If you later add true tenant-only apps, initialize those tenant databases separately using the existing command:

```bash
python manage.py init_tenant_db shop3_db
```

## What not to do

- Do not commit a real `.env` file.
- Do not copy production secrets into `.env.example` or `.env.production.example`.
- Do not rely on `DJANGO_DEBUG=True` in production.
- Do not assume a fresh clone on the server still has your old `.env`; keep production secrets outside git or recreate them explicitly.

## Instance-specific template for this project

Based on the current deployment details you shared, this is the right shape for `repairshopcloud_eu_wsgi.py` with secrets redacted:

```python
import os
import sys

project_path = os.path.expanduser('~/RepairShop')
if project_path not in sys.path:
    sys.path.insert(0, project_path)

os.environ['DJANGO_SETTINGS_MODULE'] = 'repairshop.settings'
os.environ['DJANGO_SECRET_KEY'] = 'replace-with-real-django-secret'
os.environ['DJANGO_DEBUG'] = 'False'

os.environ['PA_DB_HOST'] = 'henrikhansen.mysql.eu.pythonanywhere-services.com'
os.environ['PA_DB_PORT'] = '3306'
os.environ['PA_DB_USER'] = 'henrikhansen'
os.environ['PA_DB_PASSWORD'] = 'replace-with-real-db-password'
os.environ['PA_DEFAULT_DB_NAME'] = 'henrikhansen$repairshop_default'
os.environ['PA_SHOP1_DB_NAME'] = 'henrikhansen$shop1_db'
os.environ['PA_SHOP2_DB_NAME'] = 'henrikhansen$shop2_db'

os.environ['TENANT_DB_ALIASES'] = ''

os.environ['MOTORAPI_AUTH_TOKEN'] = 'replace-with-real-motorapi-token'
os.environ['MOTORAPI_BASE_URL'] = 'https://v1.motorapi.dk'
os.environ['MOTORAPI_VERIFY_SSL'] = 'True'

os.environ['EMAIL_BACKEND'] = 'django.core.mail.backends.smtp.EmailBackend'
os.environ['EMAIL_HOST'] = 'smtp.gmail.com'
os.environ['EMAIL_PORT'] = '587'
os.environ['EMAIL_HOST_USER'] = 'hehan.me@gmail.com'
os.environ['EMAIL_HOST_PASSWORD'] = 'replace-with-real-gmail-app-password'
os.environ['EMAIL_USE_TLS'] = 'True'
os.environ['EMAIL_USE_SSL'] = 'False'
os.environ['DEFAULT_FROM_EMAIL'] = 'invoice@repairshopcloud.eu'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

Use the PythonAnywhere Web tab to point the web app at the correct virtualenv instead of trying to activate `.venv` manually inside WSGI.
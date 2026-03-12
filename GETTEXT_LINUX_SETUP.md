# GNU Gettext Setup on Linux

This project uses Django translation catalogs in:

- `locale/da/LC_MESSAGES/django.po`
- `locale/de/LC_MESSAGES/django.po`

On Windows, `manage.py makemessages` currently fails because GNU gettext tools are not installed.
The `.po` files were updated manually and the `.mo` files were compiled with `polib` as a temporary workaround.

When working on Linux, use the normal Django gettext workflow below.

## 1. Install GNU gettext

Ubuntu or Debian:

```bash
sudo apt update
sudo apt install gettext
```

Fedora:

```bash
sudo dnf install gettext
```

Arch:

```bash
sudo pacman -S gettext
```

## 2. Verify the tools are available

```bash
which msguniq
which msgfmt
msguniq --version
msgfmt --version
```

Expected result: both commands resolve and print a version.

## 3. Activate the project environment

From the project root:

```bash
cd /path/to/RepairShop
source .venv/bin/activate
```

If the virtual environment does not exist on Linux yet:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Extract updated translation strings

Run this from the project root:

```bash
python manage.py makemessages -l da -l de
```

This updates:

- `locale/da/LC_MESSAGES/django.po`
- `locale/de/LC_MESSAGES/django.po`

## 5. Review and translate new entries

Open the `.po` files and fill in any new `msgstr` values.

Files:

- `locale/da/LC_MESSAGES/django.po`
- `locale/de/LC_MESSAGES/django.po`

## 6. Compile translations

```bash
python manage.py compilemessages
```

This generates the binary catalogs used by Django:

- `locale/da/LC_MESSAGES/django.mo`
- `locale/de/LC_MESSAGES/django.mo`

## 7. Restart the Django server

```bash
python manage.py runserver
```

If the server is already running, restart it after compiling translations.

## 8. Useful checks

Check for untranslated entries:

```bash
grep -R '^msgstr ""$' locale/*/LC_MESSAGES/django.po
```

If only the header matches, that is normal.

Run Django validation:

```bash
python manage.py check
```

## Notes

- Recent UI/layout refactors added many new strings in shared templates like `base_shop.html`, `shop_dashboard.html`, `invoice_detail.html`, `invoice_print.html`, and repair-order templates.
- The current `.po` files already contain manual additions and quality fixes for Danish and German.
- Once GNU gettext works on Linux, `makemessages` should be the source of truth again instead of manual catalog maintenance.
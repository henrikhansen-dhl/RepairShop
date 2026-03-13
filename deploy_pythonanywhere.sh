#!/usr/bin/env bash
set -euo pipefail

# One-command production deploy helper for PythonAnywhere.
# Usage:
#   ./deploy_pythonanywhere.sh
#   ./deploy_pythonanywhere.sh /home/henrikhansen/.secrets/repairshop.env
#
# Optional env vars:
#   SECRETS_FILE=/home/henrikhansen/.secrets/repairshop.env ./deploy_pythonanywhere.sh
#   VENV_ACTIVATE=/home/henrikhansen/RepairShop/.venv/bin/activate ./deploy_pythonanywhere.sh

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_FILE="${1:-${SECRETS_FILE:-$HOME/.secrets/repairshop.env}}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$PROJECT_ROOT/.venv/bin/activate}"

cd "$PROJECT_ROOT"

if [[ ! -f "$PROJECT_ROOT/manage.py" ]]; then
  echo "ERROR: manage.py not found in $PROJECT_ROOT"
  exit 1
fi

if [[ -f "$VENV_ACTIVATE" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
else
  echo "WARN: virtualenv activate script not found at: $VENV_ACTIVATE"
  echo "Continuing with current Python interpreter."
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: secrets file not found: $SECRETS_FILE"
  echo "Create it with PA_DB_* values or pass a valid path as the first argument."
  exit 1
fi

# Export all variables from secrets file for this shell.
set -a
# shellcheck disable=SC1090
source "$SECRETS_FILE"
set +a

echo "Checking active database engine..."
python manage.py shell -c "from django.conf import settings; import sys; e=settings.DATABASES['default']['ENGINE']; n=settings.DATABASES['default']['NAME']; print(e, n); sys.exit(0 if e=='django.db.backends.mysql' else 1)"

echo "Running shared-app migrations on default..."
python manage.py migrate --database=default

echo "Verifying shops migrations..."
python manage.py showmigrations shops --database=default

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Done. Next step: reload the web app in the PythonAnywhere Web tab."

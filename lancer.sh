#!/usr/bin/env bash
# Lance PyBuilder sous Linux (crée l'environnement virtuel au premier démarrage).
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "Première utilisation : création de l'environnement virtuel…"
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python pybuilder.py "$@"

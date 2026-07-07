#!/bin/bash
# Pull latest dataset (grown nightly by the 00:30 expansion job) and reload.
cd /opt/openplantdb || exit 1
before=$(git rev-parse HEAD)
git pull --ff-only origin main >/dev/null 2>&1
after=$(git rev-parse HEAD)
if [ "$before" != "$after" ]; then
  systemctl restart openplantdb-site
  logger -t openplantdb-refresh "dataset updated $before -> $after, service reloaded"
fi

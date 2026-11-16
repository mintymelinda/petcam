#!/bin/bash -e
set -euo pipefail
cd /opt/petcam
PETCAM_SKIP_DEPENDENCIES=1 PETCAM_SKIP_SERVICE_START=1 PETCAM_DEFER_TLS=1 bash deploy/install.sh

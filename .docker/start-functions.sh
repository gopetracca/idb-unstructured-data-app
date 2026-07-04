#!/bin/sh
set -eu

exec uv run --no-dev /opt/startup/start_nonappservice.sh

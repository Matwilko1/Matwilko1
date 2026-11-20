#!/usr/bin/with-contenv bashio
bashio::log.info "Starting Coffee Reminders"
cd /app
exec python3 -u -m coffee_reminders serve

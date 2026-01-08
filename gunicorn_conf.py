# Gunicorn Configuration
# TradeEdge Pro - Enterprise Production Config

import multiprocessing
import os

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 65  # Slightly higher than Nginx default

# Bind
bind = "0.0.0.0:8000"

# Logging
loglevel = "info"
accesslog = "-"  # Stdout
errorlog = "-"   # Stderr

# Timeouts
timeout = 120  # Allow for long scheduled tasks if any

# Process Naming
proc_name = "tradeedge_pro"

# Daemon
daemon = False

"""Configuration Gunicorn pour Render.com"""

# Bind to the port provided by Render
bind = "0.0.0.0:10000"

# Number of worker processes
workers = 4

# Worker class
worker_class = "sync"

# Maximum number of requests a worker will process before restarting
max_requests = 1000
max_requests_jitter = 50

# Timeout for requests
timeout = 120

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "colourful_hdjt"

# Preload app
preload_app = True

import re

config_path = "/etc/nginx/sites-enabled/trade.star7gaurav.in"
with open(config_path, "r") as f:
    config = f.read()

new_blocks = """
    # Conscious Brain Dashboard UI
    location /new-dashboard {
        alias /home/ubuntu/var/www/html/trade/dashboard-ui/dist;
        try_files $uri $uri/ /new-dashboard/index.html;
    }

    # Python WebSocket Streamer
    location /ws/ {
        proxy_pass http://127.0.0.1:8501/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
"""

if "location /new-dashboard" not in config:
    config = config.replace("    listen 443 ssl;", new_blocks + "\n    listen 443 ssl;")
    with open("new_config.conf", "w") as f:
        f.write(config)

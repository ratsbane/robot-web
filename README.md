### Control a LeRobot arm via web ###

```cd /var/www/robot
source venv/bin/activate
pkill gunicorn  # Ensure no old instances
/var/www/robot/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --preload app:app```


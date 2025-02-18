### Control a LeRobot arm via web ###

```cd /var/www/robot
source venv/bin/activate
pkill gunicorn  # Ensure no old instances
/var/www/robot/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 --preload app:app```


### Service Control ###

Add the following lines to `/etc/systemd/system/robot_arm_control.service`:

```
[Unit]
Description=Robot Arm Control Service
After=network.target

[Service]
User=pi
Group=www-data
WorkingDirectory=/var/www/robot
ExecStart=/var/www/robot/venv/bin/python /var/www/robot/robot_control_service.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

And add these lines to `/etc/systemd/system/robot_arm_web.service`

```[Unit]
Description=Robot Arm Web Server (FastAPI)
After=network.target robot_arm_control.service
Requires=robot_arm_control.service

[Service]
User=pi
Group=www-data
WorkingDirectory=/var/www/robot
ExecStart=/var/www/robot/venv/bin/uvicorn app:app --host 0.0.0.0 --port 5000
Restart=on-failure

[Install]
WantedBy=multi-user.target```

#### Enable services ####

```
sudo systemctl enable robot_arm_control.service
sudo systemctl enable robot_arm_web.service
```
#### Start the services ####

```
sudo systemctl start robot_arm_control.service
sudo systemctl start robot_arm_web.service
```

#### Check status ####
```
sudo systemctl status robot_arm_control.service
sudo systemctl status robot_arm_web.service
```

#### Stop and restart ####

```
sudo systemctl stop robot_arm_control.service
sudo systemctl restart robot_arm_control.service
sudo systemctl stop robot_arm_web.service
sudo systemctl restart robot_arm_web.service
```

#### View Logs ####

```
sudo journalctl -u robot_arm_web.service -f
sudo journalctl -u robot_arm_control.service -f
```





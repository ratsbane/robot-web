## Setup ##

Copy the four .service files in this directory /etc/systemd/system

```
sudo cp robot_arm_control.service /etc/systemd/system
sudo cp robot_websocket.service /etc/systemd/system
sudo cp video-stream.service /etc/systemd/system
sudo cp web_server.service /etc/systemd/system
```

Enable these services

```
sudo systemctl activate robot_arm_control.service
sudo systemctl activate robot_websocket.service
sudo systemctl activate video-stream.service
sudo systemctl activate web_server.service
```

Replace "activate" with "status", "start", "stop", or "restart" for those functions.



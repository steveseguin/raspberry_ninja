[Unit]
Description=Record Vdo Ninja STT
After=network.target

[Service]
User=_USER_
Group=_USER_
WorkingDirectory=_MY_PATH_
ExecStart=/usr/bin/python3 _MY_PATH_/record.py --host 0.0.0.0 --port 18000
Restart=always

[Install]
WantedBy=multi-user.target

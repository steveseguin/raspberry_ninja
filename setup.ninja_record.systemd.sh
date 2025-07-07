#!/bin/bash
set -euo pipefail
[ $(id -u) -eq 0 ] && echo "LANCEMENT root INTERDIT (use sudo user). " && exit 1
cat templates/record.service.tpl | sed "s~_USER_~$USER~g" | sed "s~_MY_PATH_~$(pwd)~" > /tmp/ninja_record.service

cat /tmp/ninja_record.service
sudo cp /tmp/ninja_record.service /etc/systemd/system/ninja_record.service

sudo systemctl daemon-reload
sudo systemctl enable ninja_record
sudo systemctl restart ninja_record

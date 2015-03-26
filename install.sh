#!/bin/bash

# This script needs to run as root
if [[ $(id -u) != 0 ]]
then
  echo Please run the setup utility as root
  exit 1
fi

# makeitso user
if [[ ! $(id makeitso) ]]
then
  echo Creating user makeitso
  useradd -m -s /bin/bash -d /home/makeitso -u 2000 makeitso
fi

# Create ssh directory and keys
if [[ ! -d /home/makeitso/.ssh ]]
then
  mkdir /home/makeitso/.ssh
  chmod 700 /home/makeitso/.ssh
  chown makeitso: /home/makeitso/.ssh
  ssh-keygen -t id_dsa /home/makeitso/.ssh/id_dsa
  chown makeitso: /home/makeitso/.ssh/id_dsa
fi

# Set-up sudo
if [[ ! -f /etc/sudoers.d/makeitso ]]
then
  echo "%makeitso ALL=(ALL) NOPASSWD:/usr/sbin/makeitso-priv" > /etc/sudoers.d/makeitso
  echo "makeitso ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/makeitso
fi

# Config files - Copy our local directory
if [[ ! -f /etc/makeitso ]]
then
  mkdir -p /etc/makeitso/makeitso.d
fi
cp makeitso.d/*.yaml /etc/makeitso/makeitso.d/
chown -R makeitso:makeitso /etc/makeitso
chmod 700 /etc/makeitso /etc/makeitso/makeitso.d
chmod 600 /etc/makeitso/makeitso.d/*.yaml

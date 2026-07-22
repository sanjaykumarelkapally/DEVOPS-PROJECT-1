#!/bin/bash

echo "Setting permissions..."

chown -R ubuntu:ubuntu /home/ubuntu/app

chmod -R 755 /home/ubuntu/app

echo "Permissions updated."
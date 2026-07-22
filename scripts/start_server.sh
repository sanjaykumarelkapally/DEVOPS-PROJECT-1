#!/bin/bash

echo "Starting application..."

cd /home/ubuntu/app

docker compose pull || true

docker compose up -d --build

echo "Application started successfully."
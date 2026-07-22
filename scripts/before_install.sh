#!/bin/bash

echo "Preparing deployment..."

mkdir -p /home/ubuntu/app

echo "Cleaning previous files..."

find /home/ubuntu/app -mindepth 1 -delete

echo "Preparation completed."
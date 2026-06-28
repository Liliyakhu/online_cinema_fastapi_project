#!/bin/bash

set -e

handle_error() {
    echo "Error: $1"
    exit 1
}

cd /home/ubuntu/src/online_cinema_fastapi_project || handle_error "Failed to navigate to the application directory."

echo "Fetching the latest changes from the remote repository..."
git fetch origin main || handle_error "Failed to fetch updates from the 'origin' remote."

echo "Resetting the local repository to match 'origin/main'..."
git reset --hard origin/main || handle_error "Failed to reset the local repository to 'origin/main'."

echo "Fetching tags from the remote repository..."
git fetch origin --tags || handle_error "Failed to fetch tags from the 'origin' remote."

docker compose -f docker-compose-prod.yml up -d --build || handle_error "Failed to build and run Docker containers."

echo "Deployment completed successfully."

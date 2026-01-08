#!/bin/bash

# Exit the script immediately if any command exits with a non-zero status
set -e

# Function to handle errors with custom messages
handle_error() {
    echo "Error: $1"
    exit 1
}

APP_DIR="/home/ubuntu/online-cinema-fastapi"
COMPOSE_FILE="docker-compose-prod.yml"
PROJECT_NAME="online_cinema"

# Navigate to the application directory
cd "$APP_DIR" || handle_error "Failed to navigate to the application directory."

# Fetch the latest changes from the remote repository
echo "Fetching the latest changes from the remote repository..."
git fetch origin main || handle_error "Failed to fetch updates from the 'origin' remote."

# Reset the local repository to match the remote 'main' branch
echo "Resetting the local repository to match 'origin/main'..."
git reset --hard origin/main || handle_error "Failed to reset the local repository to 'origin/main'."

# (Optional) Pull any new tags from the remote repository
echo "Fetching tags from the remote repository..."
git fetch origin --tags || handle_error "Failed to fetch tags from the 'origin' remote."

echo "Stopping old containers..."
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down --remove-orphans || handle_error "Failed to stop old containers"

echo "Removing old containers to avoid name conflicts..."
docker rm -f \
  backend_movies \
  mailhog_movies \
  redis_movies \
  postgres_movies \
  minio-movies \
  celery_worker_movies \
  celery_beat_movies \
  flower_movies \
  alembic_migrator_movies \
  pgadmin_movies \
  minio_mc_movies \
  || true
  
echo "Building and starting containers..."
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --build || handle_error "Failed to build and run containers"

echo "Cleaning dangling images..."
docker image prune -f || handle_error "Failed to clean dangling images"

# Print a success message upon successful deployment
echo "Deployment completed successfully."

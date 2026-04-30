#!/bin/sh

set -eu

echo "Deploying Card Scoring..."

GIT_REMOTE="${GIT_REMOTE:-origin}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
SKIP_GIT_PULL="${SKIP_GIT_PULL:-0}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-card-scoring}"
export COMPOSE_PROJECT_NAME

compose() {
    docker compose "$@"
}

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required."
    echo "Install the Docker Compose plugin on the VPS, then rerun deploy.sh."
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "git not found on PATH"
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not found on PATH"
    exit 1
fi

if [ "${SKIP_GIT_PULL}" = "1" ]; then
    echo "Skipping git pull"
else
    git pull "${GIT_REMOTE}" "${DEPLOY_BRANCH}"
fi

if [ ! -f .env ]; then
    echo "Missing .env in $(pwd). Copy .env.example to .env and set production values."
    exit 1
fi

echo "Stopping existing Docker Compose services..."
compose down --remove-orphans || true

echo "Building and starting Docker Compose services..."
compose up --build -d --remove-orphans

echo "Current service status:"
compose ps

echo "Deployment complete."

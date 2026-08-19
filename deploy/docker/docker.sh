#!/bin/bash
# --------------------------------------------------------------------------
# docker.sh — Build and run PS-MCP from wheel files in a deployment package.
#
# Run this script from inside an extracted deployment package produced by
# `psmcp build`. The package must contain:
#   wheels/       — .whl files for ps-mcp and all routers
#   Dockerfile    — wheel-based container image definition
#   .env.sample   — environment template
#
# Usage:
#   ./docker.sh build              # build the Docker image
#   ./docker.sh start              # start the container
#   ./docker.sh deploy             # build + start + tail logs
#   ./docker.sh stop | restart | logs | status
#
# Environment variables:
#   IMAGE_NAME      — Docker image name   (default: ps-mcp)
#   CONTAINER_NAME  — container name       (default: ps-mcp-server)
#   PORT            — host port            (default: 8888)
#   ENV_FILE        — .env file to mount   (default: .env in this directory)
# --------------------------------------------------------------------------
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Configuration — override via environment variables
IMAGE_NAME="${IMAGE_NAME:-ps-mcp}"
CONTAINER_NAME="${CONTAINER_NAME:-ps-mcp-server}"
PORT="${PORT:-8888}"
ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/.env}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
}

check_wheels() {
    if [ ! -d "${SCRIPT_DIR}/wheels" ] || [ -z "$(find "${SCRIPT_DIR}/wheels" -maxdepth 1 -name '*.whl' -print -quit 2>/dev/null)" ]; then
        print_error "No wheel files found in ${SCRIPT_DIR}/wheels/"
        print_error "Run this script from inside an extracted deployment package."
        exit 1
    fi
}

build_image() {
    check_wheels
    print_info "Building Docker image: ${IMAGE_NAME}:latest from wheel files"
    docker build -t "${IMAGE_NAME}:latest" "${SCRIPT_DIR}"
    print_info "Build completed successfully"
}

stop_container() {
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        print_info "Stopping existing container: ${CONTAINER_NAME}"
        docker stop "${CONTAINER_NAME}" 2>/dev/null || true
        docker rm "${CONTAINER_NAME}" 2>/dev/null || true
    fi
}

run_container() {
    print_info "Starting container: ${CONTAINER_NAME}"

    local env_flag=""
    if [ -f "${ENV_FILE}" ]; then
        env_flag="--env-file ${ENV_FILE}"
        print_info "Using env file: ${ENV_FILE}"
    else
        print_warn "No .env file found at ${ENV_FILE} — container will use defaults only"
        print_warn "Copy .env.sample to .env and edit it, then re-run."
    fi

    docker run -d \
        --name "${CONTAINER_NAME}" \
        -p "${PORT}:8888" \
        ${env_flag} \
        --restart unless-stopped \
        "${IMAGE_NAME}:latest"

    print_info "Container started successfully"
    print_info "Server is running at http://localhost:${PORT}"
    print_info "Health check: http://localhost:${PORT}/health"
}

show_logs() {
    print_info "Showing container logs (Ctrl+C to exit)"
    docker logs -f "${CONTAINER_NAME}"
}

show_status() {
    print_info "Container status:"
    docker ps -a --filter "name=^${CONTAINER_NAME}$" || print_warn "Container not found"
}

main() {
    case "${1:-}" in
        build)
            check_docker
            build_image
            ;;
        start)
            check_docker
            stop_container
            run_container
            ;;
        stop)
            check_docker
            stop_container
            print_info "Container stopped"
            ;;
        restart)
            check_docker
            stop_container
            run_container
            ;;
        logs)
            check_docker
            show_logs
            ;;
        status)
            check_docker
            show_status
            ;;
        deploy)
            check_docker
            build_image
            stop_container
            run_container
            show_logs
            ;;
        *)
            echo "Usage: $0 {build|start|stop|restart|logs|status|deploy}"
            echo ""
            echo "Commands:"
            echo "  build   - Build the Docker image from wheel files"
            echo "  start   - Start the container"
            echo "  stop    - Stop the container"
            echo "  restart - Restart the container"
            echo "  logs    - Show container logs"
            echo "  status  - Show container status"
            echo "  deploy  - Build, start, and show logs (full deployment)"
            echo ""
            echo "Run from inside an extracted psmcp build deployment package."
            exit 1
            ;;
    esac
}

main "$@"

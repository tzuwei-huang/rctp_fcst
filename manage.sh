#!/bin/bash

IMAGE_NAME="rctp_fcst_tg_bot"
CONTAINER_NAME="rctp_fcst_tg_bot"

case "$1" in
    build)
        echo "Building Docker image..."
        docker build -t $IMAGE_NAME .
        ;;
    run)
        echo "Starting container..."
        docker run --name $CONTAINER_NAME \
            --network host \
            --env-file .env \
            -d $IMAGE_NAME
        ;;
    stop)
        echo "Stopping and removing container..."
        docker stop $CONTAINER_NAME 2>/dev/null
        docker rm $CONTAINER_NAME 2>/dev/null
        ;;
    restart)
        $0 stop
        $0 build
        $0 run
        ;;
    logs)
        docker logs -f $CONTAINER_NAME
        ;;
    *)
        echo "Usage: $0 {build|run|stop|restart|logs}"
        exit 1
        ;;
esac

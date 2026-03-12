git pull
docker-compose down --remove-orphans
docker-compose up -d --build
docker image prune -f 

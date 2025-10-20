# docker build -t dmeric/docs-to-ai .

docker image tag mcp/docs-to-ai dmeric/docs-to-ai:latest
docker push dmeric/docs-to-ai:latest

docker image tag mcp/docs-to-ai dmeric/docs-to-ai:v0.2
docker push dmeric/docs-to-ai:v0.2

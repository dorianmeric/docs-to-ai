#!/usr/bin/env bash

Write-Host "Building docs-to-ai Docker image..." -ForegroundColor Green

export MY_UID=$(id -u)
export MY_GID=$(id -g)

docker-compose build

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "`nStarting MCP server in detached mode..." -ForegroundColor Green
    docker-compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nContainer started successfully!" -ForegroundColor Green
        Write-Host "Container name: docs-to-ai-mcp" -ForegroundColor Cyan
        Write-Host "`nUseful commands:" -ForegroundColor Yellow
        Write-Host "  View logs:    docker-compose logs -f docs-to-ai" -ForegroundColor White
        Write-Host "  Stop server:  docker-compose down" -ForegroundColor White
        Write-Host "  Restart:      docker-compose restart docs-to-ai" -ForegroundColor White
    } else {
        Write-Host "`nFailed to start container!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
    exit 1
}

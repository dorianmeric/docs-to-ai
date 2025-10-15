# Build and start the docs-to-ai Docker container

Write-Host "Building docs-to-ai Docker image..." -ForegroundColor Green
docker-compose build

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "`nStarting MCP server in detached mode..." -ForegroundColor Green
    docker-compose up -d docs-to-ai
    
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

# Build and start the docs-to-ai Docker container

Write-Host "Building docs-to-ai Docker image..." -ForegroundColor Green
# Default UID/GID for Windows (since it doesn't use Unix IDs)
if (wsl -e id -u 2>$null) {
  $env:MY_UID = wsl -e id -u
  $env:MY_GID = wsl -e id -g
} else {
  $env:MY_UID = 1000
  $env:MY_GID = 1000
}





docker-compose build




if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green
    Write-Host "`nStarting MCP server in detached mode..." -ForegroundColor Green
    



   # docker-compose up -d
    docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d # for GPU support


    
    
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

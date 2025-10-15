# View logs from the running MCP server

Write-Host "Viewing logs from docs-to-ai container..." -ForegroundColor Green
Write-Host "Press Ctrl+C to exit" -ForegroundColor Yellow
Write-Host ""

docker-compose logs -f docs-to-ai

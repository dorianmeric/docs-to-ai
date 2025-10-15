# Stop the docs-to-ai Docker container

Write-Host "Stopping docs-to-ai container..." -ForegroundColor Yellow

docker-compose down

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nContainer stopped successfully!" -ForegroundColor Green
} else {
    Write-Host "`nFailed to stop container!" -ForegroundColor Red
    exit 1
}

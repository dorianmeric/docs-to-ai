# Build and start the docs-to-ai Docker container

Write-Host "Building docs-to-ai Docker image... BE PATIENT, THIS USUALLY TAKES 8minutes when rebuilding!" -ForegroundColor Green
docker compose down 
docker compose build

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nBuild successful!" -ForegroundColor Green

} else {
    Write-Host "`nBuild failed!" -ForegroundColor Red
    exit 1
}

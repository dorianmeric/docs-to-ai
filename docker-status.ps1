# Check Docker installation and container status

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "docs-to-ai Docker Status Check" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan

# Check Docker installation
Write-Host "`n[1/5] Checking Docker installation..." -ForegroundColor Yellow
try {
    $dockerVersion = docker --version
    Write-Host "  ✓ Docker found: $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker not found! Please install Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check Docker Compose
Write-Host "`n[2/5] Checking Docker Compose..." -ForegroundColor Yellow
try {
    $composeVersion = docker-compose --version
    Write-Host "  ✓ Docker Compose found: $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker Compose not found!" -ForegroundColor Red
    exit 1
}

# Check if Docker daemon is running
Write-Host "`n[3/5] Checking Docker daemon..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "  ✓ Docker daemon is running" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Docker daemon is not running! Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check for Docker image
Write-Host "`n[4/5] Checking for docs-to-ai image..." -ForegroundColor Yellow
$imageExists = docker images docs-to-ai:latest --format "{{.Repository}}" | Select-String "docs-to-ai"
if ($imageExists) {
    $imageInfo = docker images docs-to-ai:latest --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    Write-Host "  ✓ Image found:" -ForegroundColor Green
    Write-Host "    $imageInfo" -ForegroundColor Cyan
} else {
    Write-Host "  ⚠ Image not found. Run './docker-build-image.ps1' to build." -ForegroundColor Yellow
}

# Check container status
Write-Host "`n[5/5] Checking container status..." -ForegroundColor Yellow
$containerRunning = docker ps --filter "name=docs-to-ai-mcp" --format "{{.Names}}" | Select-String "docs-to-ai-mcp"
$containerExists = docker ps -a --filter "name=docs-to-ai-mcp" --format "{{.Names}}" | Select-String "docs-to-ai-mcp"

if ($containerRunning) {
    Write-Host "  ✓ Container is RUNNING" -ForegroundColor Green
    $containerInfo = docker ps --filter "name=docs-to-ai-mcp" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    Write-Host "    $containerInfo" -ForegroundColor Cyan
} elseif ($containerExists) {
    Write-Host "  ⚠ Container exists but is STOPPED" -ForegroundColor Yellow
    Write-Host "    Run 'docker-compose up -d docs-to-ai' to start" -ForegroundColor White
} else {
    Write-Host "  ℹ Container not created yet" -ForegroundColor Cyan
    Write-Host "    Run './docker-build-image.ps1' to build and start" -ForegroundColor White
}

# Check data directories
Write-Host "`n[6/5] Checking data directories..." -ForegroundColor Yellow
$dirs = @("chroma_db", "doc_cache", "docs")
foreach ($dir in $dirs) {
    if (Test-Path "./$dir") {
        $itemCount = (Get-ChildItem -Path "./$dir" -Recurse -File | Measure-Object).Count
        Write-Host "  ✓ $dir/ ($itemCount files)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $dir/ not found" -ForegroundColor Yellow
    }
}

# Summary
Write-Host "`n" + ("=" * 60) -ForegroundColor Cyan
Write-Host "Quick Start Commands:" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  Build (and it will be ready to be used by LLMs via MCP,,,):     ./rebuid-DocsToAI-container.ps1" -ForegroundColor White
# Write-Host "  Add Documents:  ./docker-addfiles.ps1" -ForegroundColor White

Write-Host "=" * 60 -ForegroundColor Cyan

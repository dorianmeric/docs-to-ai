# Ingest documents into the database using Docker

Write-Host "Checking if documents exist in ./docs directory..." -ForegroundColor Green

if (-not (Test-Path "./docs")) {
    Write-Host "`nERROR: ./docs directory not found!" -ForegroundColor Red
    Write-Host "Please create the ./docs directory and add your PDF/Word documents." -ForegroundColor Yellow
    exit 1
}

$docCount = (Get-ChildItem -Path "./docs" -Recurse -Include *.pdf,*.docx,*.doc | Measure-Object).Count

if ($docCount -eq 0) {
    Write-Host "`nWARNING: No PDF or Word documents found in ./docs" -ForegroundColor Yellow
    Write-Host "Please add documents to the ./docs directory before ingesting." -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne "y") {
        exit 0
    }
} else {
    Write-Host "Found $docCount document(s) in ./docs" -ForegroundColor Cyan
}

Write-Host "`nBuilding Docker image (if needed)..." -ForegroundColor Green
docker-compose build

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nBuild failed!" -ForegroundColor Red
    exit 1
}

Write-Host "`nRunning document ingestion..." -ForegroundColor Green
Write-Host "This may take several minutes depending on the number of documents." -ForegroundColor Yellow

docker-compose run --rm docs-addfiles

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nIngestion completed successfully!" -ForegroundColor Green
    Write-Host "Documents are now available for searching." -ForegroundColor Cyan
} else {
    Write-Host "`nIngestion failed!" -ForegroundColor Red
    Write-Host "Check the error messages above for details." -ForegroundColor Yellow
    exit 1
}

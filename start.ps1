# ============================================================
#  start.ps1 — Arranca el servidor de desarrollo
#  Uso: .\start.ps1
# ============================================================

# Cargar variables del .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $val = $matches[2].Trim()
        [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
    }
}

Write-Host "✅ Variables de entorno cargadas"
Write-Host "🚀 Iniciando servidor Django en http://127.0.0.1:8000"
Write-Host "   Panel admin: http://127.0.0.1:8000/$env:ADMIN_URL"
Write-Host "   Presiona Ctrl+C para detener"
Write-Host ""

.venv\Scripts\python.exe manage.py runserver

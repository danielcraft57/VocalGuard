$ErrorActionPreference = "Stop"

$base = "http://127.0.0.1:8000/api/v1"

function Invoke-Api {
    param(
        [string]$Name,
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        $Body = $null
    )

    try {
        $params = @{
            Method = $Method
            Uri = $Url
            Headers = $Headers
        }
        if ($null -ne $Body) {
            $params["ContentType"] = "application/json"
            $params["Body"] = ($Body | ConvertTo-Json -Depth 10)
        }
        $resp = Invoke-WebRequest @params
        $parsed = $null
        if ($resp.Content) {
            try { $parsed = ($resp.Content | ConvertFrom-Json) } catch { $parsed = $resp.Content }
        }
        return [pscustomobject]@{
            name = $Name
            ok = $true
            status = [int]$resp.StatusCode
            body = $parsed
            error = $null
        }
    }
    catch {
        $status = $null
        $errBody = $null
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $raw = $reader.ReadToEnd()
                $reader.Close()
                try { $errBody = $raw | ConvertFrom-Json } catch { $errBody = $raw }
            } catch {
                $errBody = $_.Exception.Message
            }
        } else {
            $errBody = $_.Exception.Message
        }
        return [pscustomobject]@{
            name = $Name
            ok = $false
            status = $status
            body = $null
            error = $errBody
        }
    }
}

$results = @()

# 1) Génération token
$createTokenPayload = @{
    app_url = "https://danielcraft.fr"
    name = "integration-tests-public-api"
    can_read_agenda = $true
    can_write_agenda = $true
    can_write_entreprises = $true
    can_manage_tokens = $false
    can_read_customers = $true
    can_write_customers = $true
    can_read_quotes = $true
    can_write_quotes = $true
    can_read_calls = $true
}

$tokenCreate = Invoke-Api -Name "POST /tokens" -Method "POST" -Url "$base/tokens" -Body $createTokenPayload
$results += $tokenCreate
if (-not $tokenCreate.ok -or -not $tokenCreate.body.token) {
    $results | ConvertTo-Json -Depth 12
    exit 1
}

$publicToken = [string]$tokenCreate.body.token
$authHeaders = @{
    Authorization = "Bearer $publicToken"
}

# 2) Read endpoints
$results += Invoke-Api -Name "GET /public/agenda" -Method "GET" -Url "$base/public/agenda" -Headers $authHeaders
$results += Invoke-Api -Name "GET /public/availability/work-days" -Method "GET" -Url "$base/public/availability/work-days" -Headers $authHeaders

$fromDate = (Get-Date).ToString("yyyy-MM-dd")
$toDate = (Get-Date).AddDays(7).ToString("yyyy-MM-dd")
$slotsResp = Invoke-Api -Name "GET /public/availability/slots" -Method "GET" -Url "$base/public/availability/slots?from_date=$fromDate&to_date=$toDate" -Headers $authHeaders
$results += $slotsResp
$results += Invoke-Api -Name "GET /public/calls" -Method "GET" -Url "$base/public/calls?skip=0&limit=5" -Headers $authHeaders

# 3) Entreprise create/update
$createEntreprise = Invoke-Api -Name "POST /public/entreprises" -Method "POST" -Url "$base/public/entreprises" -Headers $authHeaders -Body @{
    name = "Entreprise Test API Public"
    phone_number = "03 87 78 09 16"
    website = "https://example.test"
    city = "Metz"
    country = "France"
    emails = @("contact@example.test", "team@example.test")
}
$results += $createEntreprise

$entrepriseId = $null
if ($createEntreprise.ok -and $createEntreprise.body.id) {
    $entrepriseId = [int]$createEntreprise.body.id
    $results += Invoke-Api -Name "PATCH /public/entreprises/{id}" -Method "PATCH" -Url "$base/public/entreprises/$entrepriseId" -Headers $authHeaders -Body @{
        city = "Nancy"
        emails = @("contact@example.test")
    }
}

# 4) Clients
$createClientPayload = @{
    entreprise_id = $entrepriseId
    name = "Loic Daniel"
    email = "loic5488@gmail.com"
    phone_number = "03 87 78 09 16"
    notes = "Client test API publique"
}
$createClient = Invoke-Api -Name "POST /public/clients" -Method "POST" -Url "$base/public/clients" -Headers $authHeaders -Body $createClientPayload
$results += $createClient
$results += Invoke-Api -Name "GET /public/clients" -Method "GET" -Url "$base/public/clients" -Headers $authHeaders

$clientId = $null
if ($createClient.ok -and $createClient.body.id) {
    $clientId = [int]$createClient.body.id
}

# 5) Quotes
$results += Invoke-Api -Name "POST /public/quotes" -Method "POST" -Url "$base/public/quotes" -Headers $authHeaders -Body @{
    client_id = $clientId
    phone_number = "03 87 78 09 16"
    title = "Devis test API publique"
    lines = @(
        @{
            description = "Site vitrine"
            quantity = 1
            unit_price = 1500
        }
    )
    notes = "Création via test"
    status = "draft"
}
$results += Invoke-Api -Name "GET /public/quotes" -Method "GET" -Url "$base/public/quotes" -Headers $authHeaders

# 6) Booking agenda sur un vrai créneau libre
$bookingDate = $null
$bookingTime = $null
if ($slotsResp.ok -and $slotsResp.body -and $slotsResp.body.slots -and $slotsResp.body.slots.Count -gt 0) {
    $slot = $slotsResp.body.slots[0]
    $bookingDate = [string]$slot.date
    $start = [string]$slot.start_time
    if ($start.Length -ge 16) {
        $bookingTime = $start.Substring(11, 5)
    }
}
if (-not $bookingDate -or -not $bookingTime) {
    $bookingDate = (Get-Date).AddDays(1).ToString("yyyy-MM-dd")
    $bookingTime = "11:00"
}

$results += Invoke-Api -Name "POST /public/agenda/booking" -Method "POST" -Url "$base/public/agenda/booking" -Headers $authHeaders -Body @{
    preferred_date = $bookingDate
    preferred_time = $bookingTime
    service = "site_vitrine"
    budget = "1200"
    project_type = "web"
    name = "Loic Daniel"
    company_name = "Entreprise Test API Public"
    email = "loic5488@gmail.com"
    emails = @("loic5488@gmail.com", "contact@example.test")
    phone = "03 87 78 09 16"
    website = "https://example.test"
    city = "Nancy"
    country = "France"
    address_1 = "1 rue du Test"
    message = "Demande de test endpoint booking"
}

$results += Invoke-Api -Name "GET /public/agenda (post-booking)" -Method "GET" -Url "$base/public/agenda" -Headers $authHeaders

# 7) Cleanup token de test
if ($tokenCreate.ok -and $tokenCreate.body.id) {
    $tokenId = [int]$tokenCreate.body.id
    $results += Invoke-Api -Name "DELETE /tokens/{id} (cleanup)" -Method "DELETE" -Url "$base/tokens/$tokenId"
}

$results | ConvertTo-Json -Depth 12

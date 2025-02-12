import httpx
params = {
    'query': '023993013',
    'nos': '5',
}

response = httpx.get('https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0/autocomplete', params=params)
print(response.json()) 

def ricerca(testo):
    params = {
        'query': testo,
        'spellingCorrection': 'true',
        'page': '0',
    }

    response = httpx.get('https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0/formadosaggio/ricerca', params=params)
    print(response.json())

def ricerca_esatta(scelta):
    params = {
        'query': scelta,
        'exact': 'true',
        'page': '0',
    }
    response = httpx.get('https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0/formadosaggio/ricerca', params=params)
    print(response.json())

def download_riassunto(codiceSis, aic6):
    params = {
        'ts': 'RCP',
    }

    response = httpx.get(
        f'https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0/organizzazione/{codiceSis}/farmaci/{aic6}/stampati',
        params=params
    )
    print(response.headers.get('Content-Type', ''))
    file_path = "./riassunto.pdf"
    with open(file_path, 'wb') as f:
        f.write(response.content)

def download_foglietto(codiceSis, aic6):
    params = {
        'ts': 'FI',
    }

    response = httpx.get(
        f'https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0/organizzazione/{codiceSis}/farmaci/{aic6}/stampati',
        params=params
    )
    print(response.headers.get('Content-Type', ''))
    file_path = "./foglietto.pdf"
    with open(file_path, 'wb') as f:
        f.write(response.content)

import httpx
import os

async def download_tickers_data(url, filepath):
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    with open(filepath, 'wb') as f:
        f.write(response.content)

async def download_event():
    nyse_url = 'https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_full_tickers.json'
    nasdaq_url = 'https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nasdaq/nasdaq_full_tickers.json'
    
    nyse_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nyse_full_tickers.json')
    nasdaq_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nasdaq_full_tickers.json')
    
    async with httpx.AsyncClient() as client:
        nyse_response = await client.get(nyse_url)
        nasdaq_response = await client.get(nasdaq_url)
        
        with open(nyse_file_path, 'wb') as nyse_file:
            nyse_file.write(nyse_response.content)
        
        with open(nasdaq_file_path, 'wb') as nasdaq_file:
            nasdaq_file.write(nasdaq_response.content)
    
    print('Files downloaded successfully.')


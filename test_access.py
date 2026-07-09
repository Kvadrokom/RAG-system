import uuid
import time
import asyncio
import aiohttp

GIGACHAT_AUTH_URL = 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth'
CURRENT_TOKEN = ''
TOKEN_EXPIRES_AT = time.time()
SECRET_KEY = 'MDE5YjdlYWItM2YyYS03ZWVmLWI3YzAtZWYyMmIxNTg1YWEwOjRkMDE4OGFjLWEyOGQtNDhkZi05MjE3LWIyYjUxMTBkZGYzMA=='
GIGACHAT_API_URL = 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions'

async def get_access_token():
    global CURRENT_TOKEN, TOKEN_EXPIRES_AT
    current_time = time.time()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {SECRET_KEY}"
    }
    data = {
        "scope": "GIGACHAT_API_PERS"      # Оставляем только scope
    }
    connector = aiohttp.TCPConnector(ssl=False)  # Лучше включить проверку сертификатов
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(GIGACHAT_AUTH_URL, headers=headers, data=data) as resp:
            response = await resp.json()
            print(f'status_code = {resp.status}')
            if resp.status == 200:
                token_data = response
                CURRENT_TOKEN = token_data["access_token"]
                TOKEN_EXPIRES_AT = current_time + token_data.get('expires_in', 3600)
    return response


async def gigachat_ask():
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Rquid': str(uuid.uuid4()),
        "Authorization": f"Bearer {CURRENT_TOKEN}"
    }
    data = {
        "model": "GigaChat-2",
        "messages": [{"role": "user", "content": "Hello, how are you?"}]
    }
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.post(GIGACHAT_API_URL, headers=headers, json=data) as resp:
            response = await resp.json()
            print(f'status_code = {resp.status}')
            print(resp.text)
            print(response['choices'][0]['message']['content'])

    # payload = json.dumps({
    #     "model": "GigaChat-2",
    #     "messages": [{"role": "user", "content": "Hello, how are you?"}]
    # })
    # headers = {
    #     'Content-Type': 'application/json',
    #     'Accept': 'application/json',
    #     'Authorization': f'Bearer {CURRENT_TOKEN}'
    # }
    #
    # response = requests.request("POST", GIGACHAT_API_URL, headers=headers, data=payload, verify=False)
    # print(response.text)




if __name__ == '__main__':
    result = asyncio.run(get_access_token())
    print(result['access_token'])
    asyncio.run(gigachat_ask())  # Ждём выполнения асинхронной функции
    # gigachat_ask()
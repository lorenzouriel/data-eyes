import asyncio
from pathlib import Path
import httpx
from dotenv import dotenv_values
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

async def main():
    config=dotenv_values(Path('.env'))
    base='http://localhost:3000'
    with httpx.Client(base_url=base, timeout=15) as client:
        for path in ['/assistant/', '/assistant/_stcore/health', '/assistant/_stcore/stream']:
            r=client.get(path)
            assert r.status_code==401, (path,r.status_code)
        print('Unauthenticated assistant HTTP routes rejected')
        r=client.post('/login',json={'user':config.get('GF_SECURITY_ADMIN_USER','admin'),'password':config['GF_SECURITY_ADMIN_PASSWORD']})
        assert r.status_code==200, ('Grafana login status',r.status_code)
        for path in ['/api/dashboards/uid/ask-the-fleet','/assistant/','/assistant/_stcore/health']:
            r=client.get(path)
            assert r.status_code==200, (path,r.status_code)
        print('Grafana session permits dashboard, assistant HTML and health')
        cookies='; '.join(f'{c.name}={c.value}' for c in client.cookies.jar)
        async with connect('ws://localhost:3000/assistant/_stcore/stream',origin=base,subprotocols=['streamlit'],additional_headers={'Cookie':cookies}) as ws:
            print('Authenticated Streamlit WebSocket connected')
        try:
            async with connect('ws://localhost:3000/assistant/_stcore/stream',origin=base,subprotocols=['streamlit']):
                raise AssertionError('Unauthenticated WebSocket accepted')
        except InvalidStatus as exc:
            assert exc.response.status_code==401
            print('Unauthenticated Streamlit WebSocket rejected')
        client.get('/logout')

asyncio.run(main())

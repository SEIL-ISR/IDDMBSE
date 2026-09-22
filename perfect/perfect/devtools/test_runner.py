import asyncio
import json
from pprint import pprint

import websockets

uri = "ws://localhost:8001"

EMPTY_INFO = dict(design={}, environment={})

async def send_op_async(op, info=EMPTY_INFO):
    info = info or {}
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(dict(op=op, info=info)))
        try:
            async for resp in ws:
                pprint(json.loads(resp))
        except websockets.ConnectionClosedError as e:
            print(f"Oops, did something happen to the server? Got {e}")

def send_op(op, info=EMPTY_INFO):
    asyncio.run(send_op_async(op, info))

import asyncio
import websockets
import os

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5555))

# словарь: websocket → ник
clients = {}

async def broadcast_system_message(message):
    system_msg = f"СИСТЕМА: {message}"
    await asyncio.gather(*[
        ws.send(system_msg)
        for ws in clients
    ])

async def handle_client(websocket):
    try:
        # первое сообщение — ник
        nick = await websocket.recv()
        clients[websocket] = nick
        print(f"[+] Подключился {nick}")
        await broadcast_system_message(f"{nick} присоединился к чату")

        # основной цикл чата
        async for msg in websocket:
            msg_str = f"{clients[websocket]}: {msg}"
            print(msg_str + "   ---- выведено в консоль")
            await asyncio.gather(*[
                ws.send(msg_str)
                for ws in clients
            ])

    except Exception as e:
        print(f"[!] Ошибка: {e}")

    finally:
        if websocket in clients:
            nick = clients[websocket]
            del clients[websocket]
            await broadcast_system_message(f"{nick} покинул чат")
            print(f"[-] Отключился {nick}")

async def main():
    async with websockets.serve(handle_client, HOST, PORT):
        print(f"[*] WebSocket сервер запущен на ws://{HOST}:{PORT}")
        await asyncio.Future()  # держим сервер вечным

if __name__ == "__main__":
    asyncio.run(main())
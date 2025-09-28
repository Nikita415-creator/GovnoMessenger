import asyncio
import websockets
import json
import os

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5555))

# Структуры данных
clients = {}  # websocket → {nickname, ...}
active_chats = {}  # user_nick → [list of active private chats]

async def broadcast_system_message(message):
    system_msg = json.dumps({"type": "system", "content": message})
    await asyncio.gather(*[
        ws.send(system_msg)
        for ws in clients
    ], return_exceptions=True)

async def send_user_list(websocket):
    """Отправляет текущий список пользователей"""
    user_list = [{"nickname": data["nickname"], "online": True} 
                for ws, data in clients.items() if ws != websocket]
    message = json.dumps({"type": "users", "users": user_list})
    await websocket.send(message)

async def handle_private_message(sender_ws, target_nick, content):
    """Обработка личных сообщений"""
    sender_nick = clients[sender_ws]["nickname"]
    
    # Ищем получателя
    recipient_ws = None
    for ws, data in clients.items():
        if data["nickname"] == target_nick:
            recipient_ws = ws
            break
    
    if recipient_ws:
        # Отправляем получателю
        private_msg = json.dumps({
            "type": "private",
            "from": sender_nick,
            "to": target_nick,
            "content": content,
            "timestamp": asyncio.get_event_loop().time()
        })
        await recipient_ws.send(private_msg)
        
        # Также отправляем обратно отправителю для отображения
        await sender_ws.send(private_msg)
        
        print(f"[PM] {sender_nick} → {target_nick}: {content}")
    else:
        # Пользователь не найден
        error_msg = json.dumps({
            "type": "error",
            "content": f"Пользователь {target_nick} не в сети"
        })
        await sender_ws.send(error_msg)

async def handle_client(websocket):
    try:
        # Первое сообщение — ник
        nick = await websocket.recv()
        clients[websocket] = {"nickname": nick, "joined_at": asyncio.get_event_loop().time()}
        
        print(f"[+] Подключился {nick}")
        
        # Уведомляем всех о новом пользователе
        await broadcast_system_message(f"{nick} присоединился к чату")
        
        # Отправляем текущий список пользователей всем
        await asyncio.gather(*[
            send_user_list(ws) for ws in clients
        ], return_exceptions=True)

        # Основной цикл обработки сообщений
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "private":
                # Личное сообщение
                await handle_private_message(
                    websocket, 
                    data["to"], 
                    data["content"]
                )
            elif data["type"] == "public":
                # Общее сообщение в чат
                msg_str = f"{nick}: {data['content']}"
                print(f"[PUBLIC] {msg_str}")
                
                public_msg = json.dumps({
                    "type": "public",
                    "from": nick,
                    "content": data["content"],
                    "timestamp": asyncio.get_event_loop().time()
                })
                
                await asyncio.gather(*[
                    ws.send(public_msg)
                    for ws in clients
                ], return_exceptions=True)

    except Exception as e:
        print(f"[!] Ошибка: {e}")

    finally:
        if websocket in clients:
            nick = clients[websocket]["nickname"]
            del clients[websocket]
            
            # Уведомляем об отключении
            await broadcast_system_message(f"{nick} покинул чат")
            
            # Обновляем список пользователей у оставшихся
            await asyncio.gather(*[
                send_user_list(ws) for ws in clients
            ], return_exceptions=True)
            
            print(f"[-] Отключился {nick}")

async def main():
    async with websockets.serve(handle_client, HOST, PORT):
        print(f"[*] WebSocket сервер запущен на ws://{HOST}:{PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
import socket
import threading

HOST = "0.0.0.0" 
PORT = 5555 
# DEBUG = " ------ отправлено от сервера"

clients = {}

def handle_client(conn, addr):
    print(f"[+] Подключился {addr}")
    while True:
        try:
            msg = conn.recv(1024).decode() #получение данных клиента
            if not msg:
                break
            msg_str = f"{clients[conn]}: {msg}"
            print(msg_str + "   ---- выведено в консоль")

            for clients_conn in clients:
                debugged_msg = msg_str
                clients_conn.sendall(debugged_msg.encode()) #отправка обработанных данных ВСЕМ клиентам
        except:
            break
    conn.close() #закрытие соединения
    del clients[conn] #удаление из списка
    print(f"[-] Отключился {addr}")

def main(): #запуск сервака
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT)) #назначение айпи и порта сервера
    server.listen() #прослушивание порта
    print(f"[*] Сервер запущен на {PORT}")

    while True:
        conn, addr = server.accept() #добавление клиента: conn - клиент. addr - айпи + порт.
        nick = conn.recv(1024).decode()
        clients[conn] = nick #добавление клиента в список + ник
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start() #запуск отдельного потока для клиента

if __name__ == "__main__":
    main()
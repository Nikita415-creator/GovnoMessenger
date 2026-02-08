import socketio
import eventlet
import json
import os
from datetime import datetime
import hashlib

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio)

DATA_FILE = 'messenger_data.json'

# Загрузка БД
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        storage = json.load(f)
else:
    storage = {"users": {}, "chats": {}}

def hash_password(password):
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(storage, f, ensure_ascii=False, indent=4)

@sio.event
def connect(sid, environ):
    print(f'Client connected: {sid}')

@sio.event
def disconnect(sid):
    print(f'Client disconnected: {sid}')
    # При отключении убираем статус онлайн
    for un, user_data in storage['users'].items():
        if user_data.get('sid') == sid:
            user_data['online'] = False
            user_data['typing'] = False
            # Уведомляем всех о статусе
            sio.emit('user_status', {'username': un, 'online': False, 'typing': False})
            break
    save_data()

@sio.on('register')
def handle_register(sid, data):
    un = data['username'].lower()
    dn = data['display_name']
    password = data['password']
    
    # Проверяем, не занят ли юзернейм
    if un in storage['users']:
        sio.emit('register_error', {'message': 'Юзернейм уже занят'}, room=sid)
        return
    
    # Сохраняем пользователя с хешем пароля
    storage['users'][un] = {
        'display_name': dn, 
        'sid': sid,
        'password_hash': hash_password(password),
        'online': True,
        'typing': False
    }
    
    save_data()
    
    # Отправляем успешную регистрацию
    sio.emit('register_success', {'username': un, 'display_name': dn}, room=sid)
    
    # Уведомляем всех о новом онлайн пользователе
    sio.emit('user_status', {'username': un, 'online': True, 'typing': False})
    
    # Автоматически входим после регистрации
    user_chats = {}
    for chat_id, messages in storage['chats'].items():
        users_in_chat = chat_id.split('__')
        if un in users_in_chat:
            user_chats[chat_id] = messages
    
    names_map = {u: info['display_name'] for u, info in storage['users'].items()}
    sio.emit('auth_success', {'chats': user_chats, 'names': names_map, 'current_user': un}, room=sid)

@sio.on('login')
def handle_login(sid, data):
    un = data['username'].lower()
    password = data['password']
    
    # Проверяем существование пользователя
    if un not in storage['users']:
        sio.emit('login_error', {'message': 'Пользователь не найден'}, room=sid)
        return
    
    # Проверяем пароль
    user_data = storage['users'][un]
    if user_data['password_hash'] != hash_password(password):
        sio.emit('login_error', {'message': 'Неверный пароль'}, room=sid)
        return
    
    # Обновляем SID, имя и статус онлайн
    user_data['sid'] = sid
    user_data['online'] = True
    user_data['typing'] = False
    # Сохраняем display name из БД для отправки клиенту
    dn = user_data['display_name']
    
    save_data()
    
    # Уведомляем всех о статусе онлайн
    sio.emit('user_status', {'username': un, 'online': True, 'typing': False})
    
    # Получаем чаты пользователя
    user_chats = {}
    for chat_id, messages in storage['chats'].items():
        users_in_chat = chat_id.split('__')
        if un in users_in_chat:
            user_chats[chat_id] = messages
    
    names_map = {u: info['display_name'] for u, info in storage['users'].items()}
    sio.emit('auth_success', {'chats': user_chats, 'names': names_map, 'current_user': un}, room=sid)

@sio.on('user_typing')
def handle_user_typing(sid, data):
    sender = data['from'].lower()
    target = data['to'].lower()
    is_typing = data['typing']
    
    # Обновляем статус печатания
    if sender in storage['users']:
        storage['users'][sender]['typing'] = is_typing
        # Отправляем статус получателю, если он онлайн
        if target in storage['users'] and storage['users'][target].get('sid'):
            sio.emit('user_typing_status', {
                'from': sender,
                'typing': is_typing,
                'display_name': storage['users'][sender]['display_name']
            }, room=storage['users'][target]['sid'])

@sio.on('update_password')
def handle_update_password(sid, data):
    un = data['username'].lower()
    old_password = data['old_password']
    new_password = data['new_password']
    
    if un not in storage['users']:
        sio.emit('password_update_error', {'message': 'Пользователь не найден'}, room=sid)
        return
    
    user_data = storage['users'][un]
    
    # Проверяем старый пароль
    if user_data['password_hash'] != hash_password(old_password):
        sio.emit('password_update_error', {'message': 'Неверный старый пароль'}, room=sid)
        return
    
    # Обновляем пароль
    user_data['password_hash'] = hash_password(new_password)
    save_data()
    sio.emit('password_update_success', {}, room=sid)

@sio.on('check_username')
def handle_check_username(sid, username):
    un = username.lower()
    exists = un in storage['users']
    sio.emit('username_check', {'exists': exists, 'username': un}, room=sid)

@sio.on('update_profile')
def handle_update(sid, data):
    un = data['username'].lower()
    new_dn = data['new_display_name']
    if un in storage['users']:
        old_dn = storage['users'][un]['display_name']
        storage['users'][un]['display_name'] = new_dn
        save_data()
        
        # Уведомляем всех об обновлении имени
        sio.emit('global_user_update', {'username': un, 'display_name': new_dn})
        
        # Рассылаем системное сообщение в активные чаты пользователя
        for chat_id in storage['chats']:
            if un in chat_id.split('__'):
                msg_obj = {
                    'sender': 'system',
                    'text': f"Пользователь {old_dn} сменил имя на {new_dn}",
                    'time': datetime.now().strftime("%H:%M"),
                    'date': datetime.now().strftime("%d %B"),
                    'type': 'sys'
                }
                
                if chat_id not in storage['chats']:
                    storage['chats'][chat_id] = []
                storage['chats'][chat_id].append(msg_obj)
                
                # Отправляем уведомление всем участникам чата
                users = chat_id.split('__')
                for user in users:
                    if user in storage['users'] and storage['users'][user].get('sid'):
                        sio.emit('new_message', {'chat_id': chat_id, 'msg': msg_obj}, 
                                room=storage['users'][user]['sid'])
        
        save_data()

@sio.on('send_message')
def handle_msg(sid, data):
    sender = data['from'].lower()
    target = data['to'].lower()
    chat_id = "__".join(sorted([sender, target]))
    
    msg_obj = {
        'sender': sender,
        'text': data['text'],
        'time': datetime.now().strftime("%H:%M"),
        'date': datetime.now().strftime("%d %B"),
        'type': data.get('type', 'text')
    }
    
    if chat_id not in storage['chats']:
        storage['chats'][chat_id] = []
    storage['chats'][chat_id].append(msg_obj)
    save_data()
    
    # Сбрасываем статус печатания после отправки сообщения
    if sender in storage['users']:
        storage['users'][sender]['typing'] = False
        # Уведомляем получателя, что отправитель перестал печатать
        if target in storage['users'] and storage['users'][target].get('sid'):
            sio.emit('user_typing_status', {
                'from': sender,
                'typing': False,
                'display_name': storage['users'][sender]['display_name']
            }, room=storage['users'][target]['sid'])
    
    # Отправляем сообщение отправителю
    sio.emit('new_message', {'chat_id': chat_id, 'msg': msg_obj}, room=sid)
    
    # Отправляем сообщение получателю, если он онлайн
    if target in storage['users'] and storage['users'][target].get('sid'):
        sio.emit('new_message', {'chat_id': chat_id, 'msg': msg_obj}, 
                room=storage['users'][target]['sid'])

@sio.on('search_user')
def handle_search(sid, query):
    q = query.lower()
    res = {}
    for u, info in storage['users'].items():
        if q in u or q in info['display_name'].lower():
            res[u] = info['display_name']
    sio.emit('search_results', res, room=sid)

@sio.on('signal')
def handle_signal(sid, data):
    target_un = data['to'].lower()
    sender_un = data.get('from', '').lower()
    
    # Сохраняем SID отправителя если его еще нет
    if sender_un and sender_un in storage['users']:
        storage['users'][sender_un]['sid'] = sid
        storage['users'][sender_un]['online'] = True
    
    if target_un in storage['users'] and storage['users'][target_un].get('sid'):
        sio.emit('signal', data, room=storage['users'][target_un]['sid'])

@sio.on('get_user_statuses')
def handle_get_statuses(sid, data):
    current_user = data.get('current_user', '').lower()
    statuses = {}
    
    for un, info in storage['users'].items():
        if un != current_user:  # Не отправляем статус самого пользователя
            statuses[un] = {
                'online': info.get('online', False),
                'typing': info.get('typing', False),
                'display_name': info['display_name']
            }
    
    sio.emit('user_statuses', statuses, room=sid)

if __name__ == '__main__':
    print("Starting server on port 25565...")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 25565)), app)
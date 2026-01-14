from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_socketio import SocketIO, join_room, leave_room, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'machi_secret_key'
socketio = SocketIO(app)

rooms = {}       # { 'room_id': 'password' }
# இப்போ User விபரங்களை இப்படி சேமிப்போம்: { 'room_id': [{'name': 'Machi', 'status': 'idle'}, ...] }
room_users = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        username = request.form.get('username')
        room_id = request.form.get('room_id')
        password = request.form.get('password')
        if room_id in rooms:
            flash('Room ID already exists!', 'error')
            return redirect(url_for('create'))
        rooms[room_id] = password
        room_users[room_id] = []
        session['username'] = username
        session['room'] = room_id
        return redirect(url_for('chat'))
    return render_template('create.html')

@app.route('/join', methods=['GET', 'POST'])
def join():
    r_id = request.args.get('room_id', '')
    r_pass = request.args.get('password', '')
    if request.method == 'POST':
        username = request.form.get('username')
        room_id = request.form.get('room_id')
        password = request.form.get('password')
        if room_id in rooms and rooms[room_id] == password:
            session['username'] = username
            session['room'] = room_id
            return redirect(url_for('chat'))
        else:
            flash('Invalid ID or Password', 'error')
            return redirect(url_for('join'))
    return render_template('join.html', r_id=r_id, r_pass=r_pass)

@app.route('/chat')
def chat():
    username = session.get('username')
    room = session.get('room')
    if not username or not room: return redirect(url_for('index'))
    if room not in rooms: return redirect(url_for('index'))
    current_password = rooms.get(room)
    share_link = url_for('join', room_id=room, password=current_password, _external=True)
    return render_template('chat.html', username=username, room=room, password=current_password, share_link=share_link)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Socket Logic ---
@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    if room not in room_users: room_users[room] = []
    
    # Check if user already exists to update socket id logic if needed, but for now simple append
    user_exists = False
    for user in room_users[room]:
        if user['name'] == username:
            user_exists = True
            break
    
    if not user_exists:
        room_users[room].append({'name': username, 'status': 'idle'}) # Default status: idle
    
    emit('update_users', {'users': room_users[room]}, room=room)
    emit('receive_message', {'msg': f"{username} joined.", 'user': 'System'}, room=room)

@socketio.on('disconnect')
def on_disconnect():
    username = session.get('username')
    room = session.get('room')
    if username and room and room in room_users:
        room_users[room] = [u for u in room_users[room] if u['name'] != username]
        leave_room(room)
        emit('update_users', {'users': room_users[room]}, room=room)
        emit('receive_message', {'msg': f"{username} left.", 'user': 'System'}, room=room)
        if not room_users[room]:
            if room in rooms: del rooms[room]
            del room_users[room]

@socketio.on('send_message')
def handle_message(data):
    emit('receive_message', data, room=data['room'])

@socketio.on('typing')
def handle_typing(data):
    emit('display_typing', {'user': data['username']}, room=data['room'], include_self=False)

# --- Call Status Updates ---
@socketio.on('update_status')
def handle_status(data):
    # data = {'status': 'video'/'audio'/'idle', 'room': ...}
    room = data['room']
    username = session.get('username')
    if room in room_users:
        for user in room_users[room]:
            if user['name'] == username:
                user['status'] = data['status']
                break
        emit('update_users', {'users': room_users[room]}, room=room)

# --- WebRTC Signaling ---
@socketio.on('call_invite')
def handle_call(data):
    emit('call_incoming', data, room=data['room'])

@socketio.on('signal_data')
def handle_signal(data):
    emit('signal_received', data, room=data['room'], include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True)
// ============ ПРАВИЛЬНЫЙ API.JS ДЛЯ PEERJS ============
const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const { PeerServer } = require('peer');
const cors = require('cors');

// ============ НАСТРОЙКИ ============
const HTTP_PORT = 3000;
const WS_PORT = 3001;
const PEERJS_PORT = 3002;

// ============ HTTP СЕРВЕР ============
const app = express();
app.use(cors());
app.use(express.json());

// ============ PEERJS СЕРВЕР (ПРАВИЛЬНЫЙ) ============
const server = http.createServer(app);
const peerServer = PeerServer({
    port: PEERJS_PORT,
    path: '/peerjs',
    allow_discovery: true,
    proxied: true
});

app.use('/peerjs', peerServer);

console.log(`🔄 PeerJS сервер запущен на порту ${PEERJS_PORT}`);
console.log(`   PeerJS путь: /peerjs`);

// ============ ХРАНИЛИЩЕ ИГРОКОВ ============
const players = {};
const gameRooms = {};
const pythonClients = new Map(); // playerId -> WebSocket

// ============ HTTP ЭНДПОИНТЫ ============

// Регистрация игрока
app.post('/register', (req, res) => {
    const { playerId, peerId, roomId } = req.body;
    
    if (!playerId || !peerId) {
        return res.status(400).json({ error: 'playerId and peerId required' });
    }
    
    const room = roomId || 'default';
    
    if (!gameRooms[room]) {
        gameRooms[room] = {
            host: null,
            players: {},
            gameState: null
        };
    }
    
    // Если это первый игрок в комнате - он хост
    if (Object.keys(gameRooms[room].players).length === 0) {
        gameRooms[room].host = playerId;
    }
    
    gameRooms[room].players[playerId] = {
        peerId: peerId,
        connected: true,
        lastSeen: Date.now()
    };
    
    players[playerId] = {
        peerId: peerId,
        room: room,
        connected: true
    };
    
    console.log(`✅ Игрок ${playerId} зарегистрирован в комнате ${room}`);
    console.log(`   PeerID: ${peerId}`);
    console.log(`   Всего игроков: ${Object.keys(gameRooms[room].players).length}`);
    
    res.json({
        success: true,
        isHost: gameRooms[room].host === playerId,
        players: Object.keys(gameRooms[room].players),
        hostPeerId: gameRooms[room].players[gameRooms[room].host]?.peerId
    });
});

// Получение списка игроков
app.get('/players/:roomId', (req, res) => {
    const roomId = req.params.roomId || 'default';
    
    if (!gameRooms[roomId]) {
        return res.json({ players: [], host: null });
    }
    
    const playerList = Object.keys(gameRooms[roomId].players);
    const hostPeerId = gameRooms[roomId].host ? 
        gameRooms[roomId].players[gameRooms[roomId].host]?.peerId : null;
    
    res.json({
        players: playerList,
        host: gameRooms[roomId].host,
        hostPeerId: hostPeerId,
        count: playerList.length
    });
});

// Отправка игрового состояния (для хоста)
app.post('/gamestate', (req, res) => {
    const { roomId, state } = req.body;
    
    if (!roomId || !state) {
        return res.status(400).json({ error: 'roomId and state required' });
    }
    
    if (!gameRooms[roomId]) {
        return res.status(404).json({ error: 'Room not found' });
    }
    
    gameRooms[roomId].gameState = state;
    gameRooms[roomId].gameState.timestamp = Date.now();
    
    // Отправляем состояние всем в комнате через WebSocket
    broadcastToRoom(roomId, {
        type: 'gameState',
        state: state
    });
    
    res.json({ success: true });
});

// Получение игрового состояния
app.get('/gamestate/:roomId', (req, res) => {
    const roomId = req.params.roomId || 'default';
    
    if (!gameRooms[roomId] || !gameRooms[roomId].gameState) {
        return res.json({ state: null });
    }
    
    res.json({
        state: gameRooms[roomId].gameState,
        timestamp: gameRooms[roomId].gameState?.timestamp || 0
    });
});

// Отключение игрока
app.post('/disconnect', (req, res) => {
    const { playerId, roomId } = req.body;
    
    const room = roomId || 'default';
    
    if (gameRooms[room] && gameRooms[room].players[playerId]) {
        delete gameRooms[room].players[playerId];
        delete players[playerId];
        
        if (gameRooms[room].host === playerId) {
            const remaining = Object.keys(gameRooms[room].players);
            if (remaining.length > 0) {
                gameRooms[room].host = remaining[0];
                console.log(`🔄 Новый хост: ${remaining[0]}`);
            } else {
                delete gameRooms[room];
            }
        }
        
        console.log(`👋 Игрок ${playerId} отключился`);
        broadcastToRoom(room, {
            type: 'playerLeft',
            playerId: playerId
        });
    }
    
    res.json({ success: true });
});

// Пинг
app.get('/ping', (req, res) => {
    res.json({ status: 'ok', timestamp: Date.now() });
});

// ============ WEBHOOKS ДЛЯ PEERJS ============
peerServer.on('connection', (client) => {
    console.log(`🔗 Peer подключился: ${client.getId()}`);
});

peerServer.on('disconnect', (client) => {
    console.log(`🔌 Peer отключился: ${client.getId()}`);
    
    // Удаляем игрока из всех комнат
    for (const roomId in gameRooms) {
        const room = gameRooms[roomId];
        for (const playerId in room.players) {
            if (room.players[playerId].peerId === client.getId()) {
                delete room.players[playerId];
                console.log(`👋 Игрок ${playerId} отключился (Peer)`);
                
                if (room.host === playerId) {
                    const remaining = Object.keys(room.players);
                    if (remaining.length > 0) {
                        room.host = remaining[0];
                        console.log(`🔄 Новый хост: ${remaining[0]}`);
                    }
                }
                break;
            }
        }
    }
});

// ============ WEBHOOKS ДЛЯ PYTHON (WebSocket) ============
const wss = new WebSocket.Server({ port: WS_PORT });

function broadcastToRoom(roomId, message) {
    for (const [playerId, ws] of pythonClients) {
        if (players[playerId] && players[playerId].room === roomId) {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(message));
            }
        }
    }
}

wss.on('connection', (ws, req) => {
    console.log('🐍 Python клиент подключился к WebSocket');
    let playerId = null;
    
    ws.on('message', (data) => {
        try {
            const message = JSON.parse(data);
            
            if (message.type === 'register') {
                playerId = message.playerId;
                const roomId = message.roomId || 'default';
                
                pythonClients.set(playerId, ws);
                console.log(`🐍 Python клиент зарегистрирован: ${playerId} в комнате ${roomId}`);
                
                ws.send(JSON.stringify({
                    type: 'registered',
                    playerId: playerId,
                    roomId: roomId,
                    timestamp: Date.now()
                }));
                
                if (gameRooms[roomId] && gameRooms[roomId].gameState) {
                    ws.send(JSON.stringify({
                        type: 'gameState',
                        state: gameRooms[roomId].gameState
                    }));
                }
            }
            
            if (message.type === 'gameState') {
                const roomId = message.roomId || 'default';
                if (gameRooms[roomId]) {
                    gameRooms[roomId].gameState = message.state;
                    gameRooms[roomId].gameState.timestamp = Date.now();
                    
                    broadcastToRoom(roomId, {
                        type: 'gameState',
                        state: message.state
                    });
                }
            }
            
            if (message.type === 'ping') {
                ws.send(JSON.stringify({
                    type: 'pong',
                    timestamp: Date.now()
                }));
            }
            
        } catch (e) {
            console.error('❌ Ошибка парсинга WebSocket сообщения:', e);
        }
    });
    
    ws.on('close', () => {
        if (playerId) {
            console.log(`🐍 Python клиент отключился: ${playerId}`);
            pythonClients.delete(playerId);
            
            const room = players[playerId]?.room;
            if (room && gameRooms[room]) {
                delete gameRooms[room].players[playerId];
                delete players[playerId];
                
                if (gameRooms[room].host === playerId) {
                    const remaining = Object.keys(gameRooms[room].players);
                    if (remaining.length > 0) {
                        gameRooms[room].host = remaining[0];
                    }
                }
            }
        }
    });
    
    ws.on('error', (error) => {
        console.error('WebSocket ошибка:', error);
    });
});

// ============ ЗАПУСК ============
app.listen(HTTP_PORT, () => {
    console.log(`🌐 HTTP API сервер запущен на порту ${HTTP_PORT}`);
    console.log(`   POST /register - регистрация игрока`);
    console.log(`   GET  /players/:roomId - список игроков`);
    console.log(`   POST /gamestate - отправить состояние`);
    console.log(`   GET  /gamestate/:roomId - получить состояние`);
});

console.log(`🔌 WebSocket сервер запущен на порту ${WS_PORT}`);
console.log(`   ws://localhost:${WS_PORT} - для Python клиентов`);

console.log('\n🎮 P2P сервер готов!');
console.log(`📡 PeerJS Server: http://localhost:${PEERJS_PORT}/peerjs`);
console.log(`📨 Python подключается через WebSocket к ws://localhost:${WS_PORT}\n`);
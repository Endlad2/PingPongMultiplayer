import pygame
import json
import random
import sys
import time
import threading
import requests
import websocket
from pygame.locals import *

# ============ НАСТРОЙКИ ============
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (135, 206, 235)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
PURPLE = (147, 0, 211)

PADDLE_WIDTH = 20
PADDLE_HEIGHT = 140
BALL_SIZE = 25
PADDLE_SPEED = 7
BALL_SPEED_X = 4
BALL_SPEED_Y = 3.5
WIN_TIME = 30

# ============ API НАСТРОЙКИ ============
API_URL = "http://localhost:3000"
WS_URL = "ws://localhost:3001"

# ============ КЛАССЫ ДЛЯ ИГРЫ ============
class GameObject:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rect = pygame.Rect(x, y, width, height)
    
    def update_rect(self):
        self.rect.x = self.x
        self.rect.y = self.y
    
    def move(self, dx, dy):
        self.x += dx
        self.y += dy
        self.update_rect()
    
    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.update_rect()
    
    def collides_with(self, other):
        return self.rect.colliderect(other.rect)

class Ball(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, BALL_SIZE, BALL_SIZE)
        self.dx = BALL_SPEED_X * random.choice([-1, 1])
        self.dy = BALL_SPEED_Y * random.choice([-1, 1])
        self.speed_multiplier = 1.0
    
    def update(self):
        self.x += self.dx * self.speed_multiplier
        self.y += self.dy * self.speed_multiplier
        self.update_rect()
    
    def bounce_x(self):
        self.dx *= -1
        self.speed_multiplier = min(self.speed_multiplier + 0.015, 1.4)
    
    def bounce_y(self):
        self.dy *= -1
    
    def reset(self):
        self.x = SCREEN_WIDTH//2 - BALL_SIZE//2
        self.y = SCREEN_HEIGHT//2 - BALL_SIZE//2
        self.dx = BALL_SPEED_X * random.choice([-1, 1])
        self.dy = BALL_SPEED_Y * random.choice([-1, 1])
        self.speed_multiplier = 1.0
        self.update_rect()
    
    def draw(self, screen):
        pygame.draw.rect(screen, WHITE, self.rect)
    
    def to_dict(self):
        return {"x": self.x, "y": self.y, "dx": self.dx, "dy": self.dy}
    
    def from_dict(self, data):
        self.x = data["x"]
        self.y = data["y"]
        self.dx = data["dx"]
        self.dy = data["dy"]
        self.update_rect()

class Paddle(GameObject):
    def __init__(self, x, y):
        super().__init__(x, y, PADDLE_WIDTH, PADDLE_HEIGHT)
    
    def move_up(self):
        if self.y > 0:
            self.move(0, -PADDLE_SPEED)
    
    def move_down(self):
        if self.y + self.height < SCREEN_HEIGHT:
            self.move(0, PADDLE_SPEED)
    
    def draw(self, screen):
        pygame.draw.rect(screen, WHITE, self.rect)
    
    def to_dict(self):
        return {"x": self.x, "y": self.y}
    
    def from_dict(self, data):
        self.x = data["x"]
        self.y = data["y"]
        self.update_rect()

# ============ P2P НЕТВОРКИНГ (WebSocket + PeerJS) ============
class P2PNetwork:
    def __init__(self):
        self.ws = None
        self.is_host = False
        self.connected = False
        self.player_id = None
        self.room_id = None
        self.peer_id = None
        self.host_peer_id = None
        self.running = True
        self.receive_thread = None
        self.last_received = None
        self.game_state = None
        self.players = []
        self.connection_method = "WebSocket+PeerJS"
        
    def register_player(self, player_id, room_id):
        """Зарегистрировать игрока на сервере"""
        try:
            response = requests.post(
                f"{API_URL}/register",
                json={
                    "playerId": player_id,
                    "peerId": f"player_{player_id}",
                    "roomId": room_id
                },
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                self.player_id = player_id
                self.room_id = room_id
                self.is_host = data.get("isHost", False)
                self.host_peer_id = data.get("hostPeerId")
                self.players = data.get("players", [])
                print(f"✅ Зарегистрирован как {'ХОСТ' if self.is_host else 'КЛИЕНТ'}")
                print(f"   Комната: {room_id}")
                print(f"   Игроки: {self.players}")
                return True
            else:
                print(f"❌ Ошибка регистрации: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка подключения к API: {e}")
            return False
    
    def connect_websocket(self):
        """Подключиться к WebSocket серверу"""
        try:
            print(f"🔌 Подключение к WebSocket: {WS_URL}")
            self.ws = websocket.WebSocketApp(
                WS_URL,
                on_open=self.on_ws_open,
                on_message=self.on_ws_message,
                on_close=self.on_ws_close,
                on_error=self.on_ws_error
            )
            
            # Запускаем WebSocket в отдельном потоке
            self.receive_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.receive_thread.start()
            
            # Ждем подключения
            time.sleep(1)
            return True
            
        except Exception as e:
            print(f"❌ Ошибка WebSocket: {e}")
            return False
    
    def on_ws_open(self, ws):
        print("✅ WebSocket подключен")
        # Отправляем регистрацию
        ws.send(json.dumps({
            "type": "register",
            "playerId": self.player_id,
            "roomId": self.room_id
        }))
    
    def on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            
            if data.get("type") == "registered":
                print(f"✅ Подтверждена регистрация в комнате {data.get('roomId')}")
                self.connected = True
                
            elif data.get("type") == "gameState":
                # Получено игровое состояние
                self.last_received = data.get("state")
                
            elif data.get("type") == "playerLeft":
                print(f"👋 Игрок {data.get('playerId')} покинул комнату")
                
            elif data.get("type") == "pong":
                # Ответ на ping
                pass
                
        except Exception as e:
            print(f"⚠️ Ошибка обработки WebSocket сообщения: {e}")
    
    def on_ws_close(self, ws, close_status_code, close_msg):
        print("🔌 WebSocket отключен")
        self.connected = False
    
    def on_ws_error(self, ws, error):
        print(f"⚠️ WebSocket ошибка: {error}")
    
    def start_host(self, room_id=None):
        """Стать хостом"""
        print("\n" + "="*50)
        print("🎮 ЗАПУСК В РЕЖИМЕ ХОСТА")
        print("="*50 + "\n")
        self.is_host = True
        
        # Генерируем ID игрока и комнаты
        self.player_id = f"host_{random.randint(1000, 9999)}"
        self.room_id = room_id or f"room_{random.randint(1000, 9999)}"
        
        # Регистрируемся
        if not self.register_player(self.player_id, self.room_id):
            return False
        
        # Подключаем WebSocket
        if not self.connect_websocket():
            return False
        
        # Ждем подключения
        print(f"\n📨 КОМНАТА: {self.room_id}")
        print(f"📨 Ваш ID: {self.player_id}")
        print("\n💡 Отправь другу:")
        print(f"   ROOM ID: {self.room_id}")
        print("⏳ Ожидаем подключения игрока...\n")
        
        # Ждем пока кто-то подключится
        timeout = 120
        start_wait = time.time()
        while not self.connected or len(self.players) < 2:
            if time.time() - start_wait > timeout:
                print("❌ Таймаут ожидания")
                return False
            time.sleep(1)
            # Обновляем список игроков
            self.update_players()
        
        print(f"\n✅ ИГРОК ПОДКЛЮЧИЛСЯ!")
        print(f"   Игроки: {self.players}\n")
        return True
    
    def connect_to_host(self, room_id):
        """Подключиться к хосту"""
        print("\n" + "="*50)
        print("🎮 ПОДКЛЮЧЕНИЕ К ХОСТУ")
        print("="*50 + "\n")
        self.is_host = False
        
        # Генерируем ID игрока
        self.player_id = f"client_{random.randint(1000, 9999)}"
        self.room_id = room_id
        
        # Регистрируемся
        if not self.register_player(self.player_id, self.room_id):
            return False
        
        # Подключаем WebSocket
        if not self.connect_websocket():
            return False
        
        print(f"\n📨 Подключение к комнате: {room_id}")
        print("⏳ Ожидаем начала игры...\n")
        
        # Ждем подключения
        timeout = 30
        start_wait = time.time()
        while not self.connected:
            if time.time() - start_wait > timeout:
                print("❌ Таймаут подключения")
                return False
            time.sleep(0.5)
        
        print(f"\n✅ ПОДКЛЮЧЕНО К КОМНАТЕ {room_id}!")
        print(f"   Ваш ID: {self.player_id}\n")
        return True
    
    def update_players(self):
        """Обновить список игроков в комнате"""
        try:
            response = requests.get(f"{API_URL}/players/{self.room_id}", timeout=2)
            if response.status_code == 200:
                data = response.json()
                self.players = data.get("players", [])
                self.host_peer_id = data.get("hostPeerId")
        except:
            pass
    
    def send_game_state(self, state):
        """Отправить состояние игры"""
        if not self.connected or not self.ws:
            return
        
        try:
            message = {
                "type": "gameState",
                "roomId": self.room_id,
                "state": state,
                "playerId": self.player_id,
                "isHost": self.is_host
            }
            self.ws.send(json.dumps(message))
        except Exception as e:
            print(f"⚠️ Ошибка отправки: {e}")
    
    def receive_game_state(self):
        """Получить состояние игры"""
        if self.last_received is not None:
            data = self.last_received
            self.last_received = None
            return data
        return None
    
    def close(self):
        """Закрыть соединение"""
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.ws = None

# ============ ГЛАВНОЕ МЕНЮ ============
class Menu:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.Font(None, 80)
        self.font = pygame.font.Font(None, 40)
        self.font_small = pygame.font.Font(None, 28)
        self.running = True
        self.selected = 0
        self.menu_items = ["🎮 Хост (Создать игру)", "🔗 Подключиться", "❌ Выход"]
        self.input_text = ""
        self.input_active = False
        self.input_mode = "host"  # "host" или "connect"
        self.input_rect = pygame.Rect(SCREEN_WIDTH//2 - 200, SCREEN_HEIGHT//2 + 30, 400, 50)
        self.status_message = "Выберите режим игры"
        self.status_color = WHITE
        
    def draw(self):
        self.screen.fill(BLUE)
        
        # Заголовок
        title = self.font_title.render("PING PONG P2P", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 50))
        
        # Подзаголовок
        subtitle = self.font.render("с поддержкой PeerJS", True, YELLOW)
        self.screen.blit(subtitle, (SCREEN_WIDTH//2 - subtitle.get_width()//2, 130))
        
        if not self.input_active:
            # Меню
            for i, item in enumerate(self.menu_items):
                color = YELLOW if i == self.selected else WHITE
                text = self.font.render(item, True, color)
                x = SCREEN_WIDTH//2 - text.get_width()//2
                y = 250 + i * 70
                self.screen.blit(text, (x, y))
                
                if i == self.selected:
                    pygame.draw.rect(self.screen, YELLOW, (x - 20, y - 5, text.get_width() + 40, 50), 2)
        else:
            # Режим ввода Room ID
            mode_text = "ВВЕДИТЕ ROOM ID:" if self.input_mode == "connect" else "ВВЕДИТЕ НАЗВАНИЕ КОМНАТЫ:"
            prompt = self.font.render(mode_text, True, WHITE)
            self.screen.blit(prompt, (SCREEN_WIDTH//2 - prompt.get_width()//2, SCREEN_HEIGHT//2 - 70))
            
            # Поле ввода
            pygame.draw.rect(self.screen, WHITE, self.input_rect, 2)
            text_surface = self.font.render(self.input_text, True, WHITE)
            self.screen.blit(text_surface, (self.input_rect.x + 10, self.input_rect.y + 10))
            
            # Подсказки
            hint1 = self.font_small.render("ESC - отмена | ENTER - продолжить", True, WHITE)
            self.screen.blit(hint1, (SCREEN_WIDTH//2 - hint1.get_width()//2, SCREEN_HEIGHT//2 + 100))
            
            if self.input_mode == "host":
                hint2 = self.font_small.render("Оставь пустым для автоматической генерации", True, (200, 200, 200))
            else:
                hint2 = self.font_small.render("Введи Room ID, который дал тебе хост", True, (200, 200, 200))
            self.screen.blit(hint2, (SCREEN_WIDTH//2 - hint2.get_width()//2, SCREEN_HEIGHT//2 + 130))
        
        # Статус
        if self.status_message:
            status_text = self.font_small.render(self.status_message, True, self.status_color)
            self.screen.blit(status_text, (SCREEN_WIDTH//2 - status_text.get_width()//2, SCREEN_HEIGHT - 50))
        
        pygame.display.flip()
    
    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    return None
                
                if event.type == KEYDOWN:
                    if self.input_active:
                        if event.key == K_ESCAPE:
                            self.input_active = False
                            self.input_text = ""
                            self.status_message = "Выберите режим игры"
                            self.status_color = WHITE
                        elif event.key == K_RETURN:
                            if self.input_mode == "host":
                                room_id = self.input_text.strip() or None
                                return ("host", room_id)
                            else:  # connect
                                if self.input_text.strip():
                                    return ("connect", self.input_text.strip())
                                else:
                                    self.status_message = "❌ Введите Room ID!"
                                    self.status_color = RED
                        elif event.key == K_BACKSPACE:
                            self.input_text = self.input_text[:-1]
                        else:
                            self.input_text += event.unicode
                    else:
                        if event.key == K_UP:
                            self.selected = (self.selected - 1) % len(self.menu_items)
                        elif event.key == K_DOWN:
                            self.selected = (self.selected + 1) % len(self.menu_items)
                        elif event.key == K_RETURN:
                            if self.selected == 0:  # Хост
                                self.input_active = True
                                self.input_mode = "host"
                                self.input_text = ""
                                self.status_message = "Введите название комнаты (или оставь пустым)"
                                self.status_color = YELLOW
                            elif self.selected == 1:  # Подключиться
                                self.input_active = True
                                self.input_mode = "connect"
                                self.input_text = ""
                                self.status_message = "Введите Room ID хоста"
                                self.status_color = YELLOW
                            elif self.selected == 2:  # Выход
                                return ("exit", None)
            
            self.draw()
            self.clock.tick(FPS)
        
        return None

# ============ КЛАСС ИГРЫ ============
class P2PGame:
    def __init__(self, screen, is_host, room_id=None):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.is_host = is_host
        self.running = True
        self.game_status = "waiting"
        self.start_time = None
        self.winner = None
        self.error_message = ""
        
        # Игровые объекты
        self.ball = Ball(SCREEN_WIDTH//2 - BALL_SIZE//2, SCREEN_HEIGHT//2 - BALL_SIZE//2)
        self.left_paddle = Paddle(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.right_paddle = Paddle(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        
        # Шрифты
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 72)
        self.small_font = pygame.font.Font(None, 28)
        
        # P2P сеть
        self.network = P2PNetwork()
        self.last_sync_time = 0
        self.sync_interval = 1.0 / 30
        self.frame_count = 0
        
        # Подключение
        if is_host:
            if not self.network.start_host(room_id):
                self.error_message = "Не удалось создать игру"
                self.running = False
                return
            self.game_status = "waiting"
        else:
            if not room_id:
                self.error_message = "Нет Room ID для подключения"
                self.running = False
                return
            if not self.network.connect_to_host(room_id):
                self.error_message = "Не удалось подключиться"
                self.running = False
                return
            self.game_status = "waiting"
        
        self.start_time = time.time()
        print("✅ Игра готова!")
        print(f"📡 Метод подключения: {self.network.connection_method}")
    
    def handle_input(self):
        keys = pygame.key.get_pressed()
        
        if self.is_host:
            if keys[K_w]:
                self.left_paddle.move_up()
            if keys[K_s]:
                self.left_paddle.move_down()
        else:
            if keys[K_UP]:
                self.right_paddle.move_up()
            if keys[K_DOWN]:
                self.right_paddle.move_down()
    
    def update(self):
        if self.game_status != "running":
            return
        
        self.ball.update()
        
        if self.ball.y <= 0 or self.ball.y + self.ball.height >= SCREEN_HEIGHT:
            self.ball.bounce_y()
        
        if self.ball.collides_with(self.left_paddle):
            self.ball.x = self.left_paddle.x + self.left_paddle.width
            self.ball.bounce_x()
        
        if self.ball.collides_with(self.right_paddle):
            self.ball.x = self.right_paddle.x - self.ball.width
            self.ball.bounce_x()
        
        if self.ball.x <= 0:
            self.game_status = "lose"
            self.winner = "opponent"
            self.running = False
        elif self.ball.x + self.ball.width >= SCREEN_WIDTH:
            self.game_status = "win"
            self.winner = "me"
            self.running = False
        
        if self.start_time and time.time() - self.start_time >= WIN_TIME:
            self.game_status = "win" if self.is_host else "lose"
            self.winner = "me" if self.is_host else "opponent"
            self.running = False
    
    def sync_network(self):
        current_time = time.time()
        if current_time - self.last_sync_time < self.sync_interval:
            return
        
        self.last_sync_time = current_time
        
        if self.is_host:
            # Хост отправляет полное состояние
            state = {
                "ball": self.ball.to_dict(),
                "left_paddle": self.left_paddle.to_dict(),
                "right_paddle": self.right_paddle.to_dict(),
                "status": self.game_status,
                "time": time.time() - self.start_time if self.start_time else 0
            }
            self.network.send_game_state(state)
        else:
            # Клиент отправляет только свою ракетку
            state = {
                "right_paddle": self.right_paddle.to_dict()
            }
            self.network.send_game_state(state)
            
            # Получаем состояние от хоста
            received = self.network.receive_game_state()
            if received:
                if "ball" in received:
                    self.ball.from_dict(received["ball"])
                if "left_paddle" in received:
                    self.left_paddle.from_dict(received["left_paddle"])
                if "status" in received:
                    self.game_status = received["status"]
                    if self.game_status != "running" and self.running:
                        self.running = False
    
    def draw(self):
        self.screen.fill(BLUE)
        
        # Центральная линия
        pygame.draw.line(self.screen, WHITE, (SCREEN_WIDTH//2, 0), (SCREEN_WIDTH//2, SCREEN_HEIGHT), 2)
        pygame.draw.circle(self.screen, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 60, 2)
        
        # Игровые объекты
        self.ball.draw(self.screen)
        self.left_paddle.draw(self.screen)
        self.right_paddle.draw(self.screen)
        
        # Время
        if self.start_time and self.game_status == "running":
            elapsed = int(time.time() - self.start_time)
            time_text = self.font.render(f"Time: {elapsed}s", True, WHITE)
            self.screen.blit(time_text, (10, 10))
        
        # Роль
        role = "ХОСТ" if self.is_host else "КЛИЕНТ"
        role_text = self.font.render(role, True, YELLOW)
        self.screen.blit(role_text, (SCREEN_WIDTH - 120, 10))
        
        # Room ID
        if self.network.room_id:
            room_text = self.small_font.render(f"Комната: {self.network.room_id}", True, (200, 200, 200))
            self.screen.blit(room_text, (10, SCREEN_HEIGHT - 30))
        
        # Игроки
        if self.network.players:
            players_text = self.small_font.render(f"Игроки: {len(self.network.players)}", True, (200, 200, 200))
            self.screen.blit(players_text, (SCREEN_WIDTH - 150, SCREEN_HEIGHT - 30))
        
        # Статус ожидания
        if self.game_status == "waiting":
            wait_text = self.big_font.render("ОЖИДАНИЕ", True, YELLOW)
            self.screen.blit(wait_text, (SCREEN_WIDTH//2 - wait_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            
            if self.is_host:
                sub_text = self.small_font.render(f"Ожидаем подключения в комнате {self.network.room_id}...", True, WHITE)
            else:
                sub_text = self.small_font.render("Ожидаем начала игры...", True, WHITE)
            self.screen.blit(sub_text, (SCREEN_WIDTH//2 - sub_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
            
            if self.is_host and self.network.connected and len(self.network.players) >= 2:
                start_text = self.font.render("Нажми SPACE для начала игры", True, GREEN)
                self.screen.blit(start_text, (SCREEN_WIDTH//2 - start_text.get_width()//2, SCREEN_HEIGHT//2 + 80))
            elif self.is_host:
                wait_players = self.small_font.render(f"Подключено игроков: {len(self.network.players)}/2", True, YELLOW)
                self.screen.blit(wait_players, (SCREEN_WIDTH//2 - wait_players.get_width()//2, SCREEN_HEIGHT//2 + 80))
        
        # Результат
        if self.game_status == "win":
            win_text = self.big_font.render("ТЫ ПОБЕДИЛ! 🏆", True, GREEN)
            self.screen.blit(win_text, (SCREEN_WIDTH//2 - win_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Нажми R для реванша", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
        elif self.game_status == "lose":
            lose_text = self.big_font.render("ТЫ ПРОИГРАЛ! 😢", True, RED)
            self.screen.blit(lose_text, (SCREEN_WIDTH//2 - lose_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Нажми R для реванша", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
        
        # Ошибка
        if self.error_message:
            error_text = self.small_font.render(f"❌ {self.error_message}", True, RED)
            self.screen.blit(error_text, (SCREEN_WIDTH//2 - error_text.get_width()//2, SCREEN_HEIGHT - 70))
        
        pygame.display.flip()
    
    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    self.running = False
                if event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        self.running = False
                    if event.key == K_SPACE and self.game_status == "waiting" and self.is_host:
                        if self.network.connected and len(self.network.players) >= 2:
                            self.game_status = "running"
                            self.start_time = time.time()
                            self.ball.reset()
                        else:
                            print("⏳ Ждем подключения второго игрока...")
                    if event.key == K_r and (self.game_status == "win" or self.game_status == "lose"):
                        self.game_status = "waiting"
                        self.start_time = None
                        self.running = True
                        self.ball.reset()
                        self.left_paddle.set_position(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
                        self.right_paddle.set_position(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
            
            if self.game_status == "running":
                self.handle_input()
                self.update()
                self.sync_network()
            
            self.draw()
            self.clock.tick(FPS)
        
        self.network.close()
        return

# ============ ГЛАВНАЯ ФУНКЦИЯ ============
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Ping Pong P2P")
    
    while True:
        menu = Menu(screen)
        result = menu.run()
        
        if not result or result[0] == "exit":
            break
        
        if result[0] == "host":
            room_id = result[1]
            game = P2PGame(screen, True, room_id)
            game.run()
        elif result[0] == "connect":
            room_id = result[1]
            game = P2PGame(screen, False, room_id)
            game.run()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
import pygame
import json
import random
import sys
import time
import threading
import requests
import websocket
from pygame.locals import *

# ============ SETTINGS ============
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (135, 206, 235)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)

PADDLE_WIDTH = 20
PADDLE_HEIGHT = 140
BALL_SIZE = 25
PADDLE_SPEED = 7
BALL_SPEED_X = 4
BALL_SPEED_Y = 3.5
WIN_TIME = 30

# ============ API SETTINGS ============
API_URL = "http://31.77.148.203:3001"
WS_URL = "ws://31.77.148.203:3001"

# ============ GAME CLASSES ============
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

# ============ NETWORK CLIENT (WebSocket) ============
class NetworkClient:
    def __init__(self):
        self.ws = None
        self.is_host = False
        self.connected = False
        self.player_id = None
        self.room_id = None
        self.receive_thread = None
        self.game_state = None
        self.running = True
        self.opponent_paddle = None
        self.ball_state = None
        self.status = "waiting"
        self.last_sync_time = 0
        self.sync_interval = 1.0 / 30
        self.room_ready = False  # Флаг готовности комнаты
    
    def create_room(self, name_hash: str, password: str):
        try:
            response = requests.post(
                f"{API_URL}/create_room",
                params={"name_hash": name_hash, "password": password},
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                self.room_id = data["room_id"]
                self.is_host = True
                self.status = data["status"]
                print(f"[OK] Room created! ID: {self.room_id}")
                print(f"   Status: {self.status}")
                return True
            else:
                print(f"[ERROR] {response.status_code}")
                return False
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            return False
    
    def connect_to_room(self, name_hash: str, password: str):
        try:
            response = requests.get(
                f"{API_URL}/connect",
                params={"name_hash": name_hash, "password": password},
                timeout=3
            )
            
            if response.status_code == 200:
                data = response.json()
                self.room_id = data["room_id"]
                self.is_host = False
                self.status = data["status"]
                print(f"[OK] Connected to room! ID: {self.room_id}")
                return True
            else:
                print(f"[ERROR] {response.status_code}")
                return False
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
            return False
    
    def connect_websocket(self):
        try:
            ws_url = f"{WS_URL}/ws/room/{self.room_id}"
            print(f"[WS] Connecting to WebSocket: {ws_url}")
            
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self.on_ws_open,
                on_message=self.on_ws_message,
                on_close=self.on_ws_close,
                on_error=self.on_ws_error
            )
            
            self.receive_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.receive_thread.start()
            
            timeout = 10
            start = time.time()
            while not self.connected and time.time() - start < timeout:
                time.sleep(0.1)
            
            return self.connected
            
        except Exception as e:
            print(f"[ERROR] WebSocket error: {e}")
            return False
    
    def on_ws_open(self, ws):
        print("[WS] WebSocket connected")
    
    def on_ws_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "connected":
                self.connected = True
                self.is_host = data.get("is_host", False)
                self.status = data.get("status", "waiting")
                print(f"[WS] Connected to room {data.get('room_id')}")
                print(f"   Role: {'HOST' if self.is_host else 'CLIENT'}")
                print(f"   Status: {self.status}")
                
            elif msg_type == "status":
                new_status = data.get("status")
                players = data.get("players", 0)
                print(f"[STATUS] Room status: {new_status} (players: {players})")
                self.status = new_status
                
                if new_status == "running" and players == 2:
                    print("[GAME] Game starting!")
                    self.room_ready = True
                
            elif msg_type == "game_state":
                state = data.get("state", {})
                if state:
                    self.game_state = state
                    
            elif msg_type == "paddle_move":
                paddle_data = data.get("paddle", {})
                if paddle_data:
                    self.opponent_paddle = paddle_data
                    
        except Exception as e:
            print(f"[ERROR] Message error: {e}")
    
    def on_ws_close(self, ws, close_status_code, close_msg):
        print("[WS] WebSocket disconnected")
        self.connected = False
    
    def on_ws_error(self, ws, error):
        print(f"[ERROR] WebSocket error: {error}")
    
    def send_game_state(self, state):
        if not self.connected or not self.ws:
            return
        
        try:
            message = {
                "type": "game_state",
                "state": state
            }
            self.ws.send(json.dumps(message))
        except Exception as e:
            print(f"[ERROR] Send error: {e}")
    
    def send_paddle_move(self, paddle_data):
        if not self.connected or not self.ws:
            return
        
        try:
            message = {
                "type": "paddle_move",
                "paddle": paddle_data
            }
            self.ws.send(json.dumps(message))
        except Exception as e:
            pass
    
    def get_latest_state(self):
        if self.game_state:
            state = self.game_state
            self.game_state = None
            return state
        return None
    
    def get_opponent_paddle(self):
        if self.opponent_paddle:
            paddle = self.opponent_paddle
            self.opponent_paddle = None
            return paddle
        return None
    
    def close(self):
        self.running = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
        self.ws = None

# ============ MAIN MENU ============
class Menu:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.font_title = pygame.font.Font(None, 80)
        self.font = pygame.font.Font(None, 40)
        self.font_small = pygame.font.Font(None, 28)
        self.running = True
        self.selected = 0
        self.menu_items = ["Host (Create Game)", "Connect", "Exit"]
        self.input_text = ""
        self.input_active = False
        self.input_mode = "host"
        self.input_rect = pygame.Rect(SCREEN_WIDTH//2 - 200, SCREEN_HEIGHT//2 + 30, 400, 50)
        self.status_message = "Select game mode"
        self.status_color = WHITE
        self.name_hash = f"player_{random.randint(1000, 9999)}"
        self.password = ""
        
    def draw(self):
        self.screen.fill(BLUE)
        
        title = self.font_title.render("PING PONG", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 50))
        
        subtitle = self.font.render("WebSocket Multiplayer", True, YELLOW)
        self.screen.blit(subtitle, (SCREEN_WIDTH//2 - subtitle.get_width()//2, 130))
        
        server_text = self.font_small.render(f"Server: {API_URL}", True, (200, 200, 200))
        self.screen.blit(server_text, (SCREEN_WIDTH//2 - server_text.get_width()//2, 180))
        
        if not self.input_active:
            for i, item in enumerate(self.menu_items):
                color = YELLOW if i == self.selected else WHITE
                text = self.font.render(item, True, color)
                x = SCREEN_WIDTH//2 - text.get_width()//2
                y = 250 + i * 70
                self.screen.blit(text, (x, y))
                
                if i == self.selected:
                    pygame.draw.rect(self.screen, YELLOW, (x - 20, y - 5, text.get_width() + 40, 50), 2)
        else:
            mode_text = "ENTER PASSWORD:" 
            prompt = self.font.render(mode_text, True, WHITE)
            self.screen.blit(prompt, (SCREEN_WIDTH//2 - prompt.get_width()//2, SCREEN_HEIGHT//2 - 70))
            
            pygame.draw.rect(self.screen, WHITE, self.input_rect, 2)
            text_surface = self.font.render("*" * len(self.password), True, WHITE)
            self.screen.blit(text_surface, (self.input_rect.x + 10, self.input_rect.y + 10))
            
            hint1 = self.font_small.render("ESC - cancel | ENTER - continue", True, WHITE)
            self.screen.blit(hint1, (SCREEN_WIDTH//2 - hint1.get_width()//2, SCREEN_HEIGHT//2 + 100))
            
            if self.input_mode == "host":
                hint2 = self.font_small.render("Create a password for the room", True, (200, 200, 200))
            else:
                hint2 = self.font_small.render("Enter the room password", True, (200, 200, 200))
            self.screen.blit(hint2, (SCREEN_WIDTH//2 - hint2.get_width()//2, SCREEN_HEIGHT//2 + 130))
        
        if self.status_message:
            status_text = self.font_small.render(self.status_message, True, self.status_color)
            self.screen.blit(status_text, (SCREEN_WIDTH//2 - status_text.get_width()//2, SCREEN_HEIGHT - 50))
        
        name_text = self.font_small.render(f"Your ID: {self.name_hash}", True, (200, 200, 200))
        self.screen.blit(name_text, (10, SCREEN_HEIGHT - 30))
        
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
                            self.password = ""
                            self.status_message = "Select game mode"
                            self.status_color = WHITE
                        elif event.key == K_RETURN:
                            if self.password.strip():
                                if self.input_mode == "host":
                                    return ("host", self.name_hash, self.password)
                                else:
                                    return ("connect", self.name_hash, self.password)
                            else:
                                self.status_message = "[ERROR] Enter password!"
                                self.status_color = RED
                        elif event.key == K_BACKSPACE:
                            self.password = self.password[:-1]
                        else:
                            self.password += event.unicode
                    else:
                        if event.key == K_UP:
                            self.selected = (self.selected - 1) % len(self.menu_items)
                        elif event.key == K_DOWN:
                            self.selected = (self.selected + 1) % len(self.menu_items)
                        elif event.key == K_RETURN:
                            if self.selected == 0:
                                self.input_active = True
                                self.input_mode = "host"
                                self.password = ""
                                self.status_message = "Enter password for room"
                                self.status_color = YELLOW
                            elif self.selected == 1:
                                self.input_active = True
                                self.input_mode = "connect"
                                self.password = ""
                                self.status_message = "Enter room password"
                                self.status_color = YELLOW
                            elif self.selected == 2:
                                return ("exit", None, None)
            
            self.draw()
            self.clock.tick(FPS)
        
        return None

# ============ GAME CLASS ============
class Game:
    def __init__(self, screen, is_host, name_hash, password):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.is_host = is_host
        self.running = True
        self.game_status = "waiting"
        self.start_time = None
        self.winner = None
        self.error_message = ""
        
        self.ball = Ball(SCREEN_WIDTH//2 - BALL_SIZE//2, SCREEN_HEIGHT//2 - BALL_SIZE//2)
        self.left_paddle = Paddle(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.right_paddle = Paddle(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 72)
        self.small_font = pygame.font.Font(None, 28)
        
        self.network = NetworkClient()
        
        if is_host:
            if not self.network.create_room(name_hash, password):
                self.error_message = "Failed to create room"
                self.running = False
                return
        else:
            if not self.network.connect_to_room(name_hash, password):
                self.error_message = "Failed to connect to room"
                self.running = False
                return
        
        if not self.network.connect_websocket():
            self.error_message = "Failed to connect to WebSocket"
            self.running = False
            return
        
        self.game_status = "waiting"
        self.start_time = None
        self.last_paddle_sync = 0
        self.paddle_sync_interval = 1.0 / 15
        self.waiting_for_start = True
        
        print("[GAME] Game ready!")
    
    def handle_input(self):
        keys = pygame.key.get_pressed()
        paddle_moved = False
        paddle_data = None
        
        if self.is_host:
            if keys[K_w]:
                self.left_paddle.move_up()
                paddle_moved = True
            if keys[K_s]:
                self.left_paddle.move_down()
                paddle_moved = True
            if paddle_moved:
                paddle_data = self.left_paddle.to_dict()
        else:
            if keys[K_UP]:
                self.right_paddle.move_up()
                paddle_moved = True
            if keys[K_DOWN]:
                self.right_paddle.move_down()
                paddle_moved = True
            if paddle_moved:
                paddle_data = self.right_paddle.to_dict()
        
        if paddle_moved and paddle_data:
            current_time = time.time()
            if current_time - self.last_paddle_sync >= self.paddle_sync_interval:
                self.network.send_paddle_move(paddle_data)
                self.last_paddle_sync = current_time
    
    def update(self):
        # Проверяем статус комнаты
        if self.network.status == "running" and self.game_status == "waiting":
            self.game_status = "running"
            self.start_time = time.time()
            self.ball.reset()
            print("[GAME] Game started!")
        
        if self.game_status != "running":
            return
        
        if not self.is_host:
            state = self.network.get_latest_state()
            if state:
                if "ball" in state:
                    self.ball.from_dict(state["ball"])
                if "left_paddle" in state:
                    self.left_paddle.from_dict(state["left_paddle"])
                if "right_paddle" in state:
                    self.right_paddle.from_dict(state["right_paddle"])
                if "status" in state:
                    self.game_status = state["status"]
                    if self.game_status != "running" and self.running:
                        self.running = False
                return
        
        if self.is_host:
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
                self.game_status = "lose" if self.is_host else "win"
                self.winner = "opponent" if self.is_host else "me"
                self.running = False
            elif self.ball.x + self.ball.width >= SCREEN_WIDTH:
                self.game_status = "win" if self.is_host else "lose"
                self.winner = "me" if self.is_host else "opponent"
                self.running = False
            
            if self.start_time and time.time() - self.start_time >= WIN_TIME:
                self.game_status = "win" if self.is_host else "lose"
                self.winner = "me" if self.is_host else "opponent"
                self.running = False
            
            if self.game_status == "running":
                state = {
                    "ball": self.ball.to_dict(),
                    "left_paddle": self.left_paddle.to_dict(),
                    "right_paddle": self.right_paddle.to_dict(),
                    "status": self.game_status,
                    "time": time.time() - self.start_time if self.start_time else 0
                }
                self.network.send_game_state(state)
            
            opponent_paddle = self.network.get_opponent_paddle()
            if opponent_paddle:
                self.right_paddle.from_dict(opponent_paddle)
    
    def draw(self):
        self.screen.fill(BLUE)
        
        pygame.draw.line(self.screen, WHITE, (SCREEN_WIDTH//2, 0), (SCREEN_WIDTH//2, SCREEN_HEIGHT), 2)
        pygame.draw.circle(self.screen, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 60, 2)
        
        self.ball.draw(self.screen)
        self.left_paddle.draw(self.screen)
        self.right_paddle.draw(self.screen)
        
        if self.start_time and self.game_status == "running":
            elapsed = int(time.time() - self.start_time)
            time_text = self.font.render(f"Time: {elapsed}s", True, WHITE)
            self.screen.blit(time_text, (10, 10))
        
        role = "HOST" if self.is_host else "CLIENT"
        role_text = self.font.render(role, True, YELLOW)
        self.screen.blit(role_text, (SCREEN_WIDTH - 120, 10))
        
        if self.network.room_id:
            room_text = self.small_font.render(f"Room: {self.network.room_id[:8]}...", True, (200, 200, 200))
            self.screen.blit(room_text, (10, SCREEN_HEIGHT - 30))
        
        status_text = self.small_font.render(f"Status: {self.network.status}", True, (150, 200, 150))
        self.screen.blit(status_text, (SCREEN_WIDTH - 200, SCREEN_HEIGHT - 30))
        
        if self.game_status == "waiting":
            wait_text = self.big_font.render("WAITING", True, YELLOW)
            self.screen.blit(wait_text, (SCREEN_WIDTH//2 - wait_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            
            if self.is_host:
                sub_text = self.small_font.render(f"Waiting for player in room {self.network.room_id[:12]}...", True, WHITE)
            else:
                sub_text = self.small_font.render("Waiting for game to start...", True, WHITE)
            self.screen.blit(sub_text, (SCREEN_WIDTH//2 - sub_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
            
            if self.is_host and self.network.connected and self.network.status == "running":
                start_text = self.font.render("Press SPACE to start", True, GREEN)
                self.screen.blit(start_text, (SCREEN_WIDTH//2 - start_text.get_width()//2, SCREEN_HEIGHT//2 + 80))
        
        if self.game_status == "win":
            win_text = self.big_font.render("YOU WIN!", True, GREEN)
            self.screen.blit(win_text, (SCREEN_WIDTH//2 - win_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Press R for rematch", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
        elif self.game_status == "lose":
            lose_text = self.big_font.render("YOU LOSE!", True, RED)
            self.screen.blit(lose_text, (SCREEN_WIDTH//2 - lose_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Press R for rematch", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 30))
        
        if self.error_message:
            error_text = self.small_font.render(f"[ERROR] {self.error_message}", True, RED)
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
                        if self.network.connected and self.network.status == "running":
                            self.game_status = "running"
                            self.start_time = time.time()
                            self.ball.reset()
                            print("[GAME] Game started by host!")
                        else:
                            print("[GAME] Waiting for second player...")
                    if event.key == K_r and (self.game_status == "win" or self.game_status == "lose"):
                        self.game_status = "waiting"
                        self.start_time = None
                        self.running = True
                        self.ball.reset()
                        self.left_paddle.set_position(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
                        self.right_paddle.set_position(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
                        self.network.status = "waiting"
            
            if self.game_status == "running":
                self.handle_input()
                self.update()
            
            self.draw()
            self.clock.tick(FPS)
        
        self.network.close()
        return

# ============ MAIN FUNCTION ============
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Ping Pong - WebSocket Multiplayer")
    
    while True:
        menu = Menu(screen)
        result = menu.run()
        
        if not result or result[0] == "exit":
            break
        
        if result[0] == "host":
            _, name_hash, password = result
            game = Game(screen, True, name_hash, password)
            game.run()
        elif result[0] == "connect":
            _, name_hash, password = result
            game = Game(screen, False, name_hash, password)
            game.run()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

import pygame
import json
import math
import random
import sys
import argparse
import requests
import time

pygame.init()

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (135, 206, 235)
PADDLE_WIDTH = 20
PADDLE_HEIGHT = 140
BALL_SIZE = 25
PADDLE_SPEED = 7
BALL_SPEED_X = 4
BALL_SPEED_Y = 3.5
WIN_TIME = 30

def parse_arguments():
    parser = argparse.ArgumentParser(description='Ping Pong Game')
    parser.add_argument('player_id', type=int, choices=[1, 2], help='Player ID: 1 or 2')
    parser.add_argument('--connect', type=str, required=True, help='Server URL (e.g., https://merkuriy.space/game.php)')
    return parser.parse_args()

def test_connection(url):
    try:
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    print("Connection successful! Server responded with valid JSON.")
                    return True
                else:
                    print("Connection failed: Server did not return a JSON object")
                    return False
            except json.JSONDecodeError:
                print("Connection failed: Server response is not valid JSON")
                return False
        else:
            print(f"Connection failed: Server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"Connection failed: Cannot reach {url}")
        return False
    except requests.exceptions.Timeout:
        print(f"Connection failed: Server at {url} is not responding (timeout)")
        return False
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

def get_game_state(url):
    try:
        response = requests.get(url, timeout=0.2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def post_game_state(url, state):
    try:
        requests.post(url, json=state, timeout=0.2)
    except:
        pass

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
    
    def get_position(self):
        return (self.x, self.y)
    
    def get_center(self):
        return (self.x + self.width/2, self.y + self.height/2)
    
    def collides_with(self, other):
        return self.rect.colliderect(other.rect)
    
    def get_rect(self):
        return self.rect

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

class Game:
    def __init__(self, url, player_id):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"Ping Pong - Player {player_id}")
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_status = "running"
        self.start_time = pygame.time.get_ticks()
        self.ball = Ball(SCREEN_WIDTH//2 - BALL_SIZE//2, SCREEN_HEIGHT//2 - BALL_SIZE//2)
        self.left_paddle = Paddle(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.right_paddle = Paddle(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.font = pygame.font.Font(None, 36)
        self.big_font = pygame.font.Font(None, 72)
        self.small_font = pygame.font.Font(None, 28)
        self.player_id = player_id
        self.url = url
        self.connection_error = False
        self.error_message = ""
        
        self.game_state = {
            "ball": {"x": self.ball.x, "y": self.ball.y, "dx": self.ball.dx, "dy": self.ball.dy},
            "left_paddle": {"x": self.left_paddle.x, "y": self.left_paddle.y},
            "right_paddle": {"x": self.right_paddle.x, "y": self.right_paddle.y},
            "status": self.game_status,
            "time_elapsed": 0
        }
        
        print(f"Player {player_id} connecting to {url}")
        
        if not test_connection(url):
            self.connection_error = True
            self.error_message = "Cannot connect to server"
            print("Press ESC to quit or wait for reconnection...")
        else:
            print("Connected successfully! Press ESC to quit.")
    
    def update_game_state(self):
        self.game_state["ball"]["x"] = self.ball.x
        self.game_state["ball"]["y"] = self.ball.y
        self.game_state["ball"]["dx"] = self.ball.dx
        self.game_state["ball"]["dy"] = self.ball.dy
        self.game_state["left_paddle"]["x"] = self.left_paddle.x
        self.game_state["left_paddle"]["y"] = self.left_paddle.y
        self.game_state["right_paddle"]["x"] = self.right_paddle.x
        self.game_state["right_paddle"]["y"] = self.right_paddle.y
        self.game_state["status"] = self.game_status
        if self.game_status == "running":
            elapsed = (pygame.time.get_ticks() - self.start_time) / 1000
            self.game_state["time_elapsed"] = round(elapsed, 1)
    
    def sync_from_server(self):
        state = get_game_state(self.url)
        if state:
            self.connection_error = False
            self.ball.x = state["ball"]["x"]
            self.ball.y = state["ball"]["y"]
            self.ball.dx = state["ball"]["dx"]
            self.ball.dy = state["ball"]["dy"]
            self.ball.update_rect()
            
            self.left_paddle.x = state["left_paddle"]["x"]
            self.left_paddle.y = state["left_paddle"]["y"]
            self.left_paddle.update_rect()
            
            self.right_paddle.x = state["right_paddle"]["x"]
            self.right_paddle.y = state["right_paddle"]["y"]
            self.right_paddle.update_rect()
            
            self.game_status = state["status"]
            if self.game_status != "running":
                self.running = False
        else:
            self.connection_error = True
            self.error_message = "Lost connection to server"
    
    def sync_to_server(self):
        self.update_game_state()
        post_game_state(self.url, self.game_state)
    
    def handle_input(self):
        keys = pygame.key.get_pressed()
        
        if self.player_id == 1:
            if keys[pygame.K_w]:
                self.left_paddle.move_up()
            if keys[pygame.K_s]:
                self.left_paddle.move_down()
        else:
            if keys[pygame.K_UP]:
                self.right_paddle.move_up()
            if keys[pygame.K_DOWN]:
                self.right_paddle.move_down()
    
    def check_collisions(self):
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
            self.running = False
        
        if self.ball.x + self.ball.width >= SCREEN_WIDTH:
            self.game_status = "lose"
            self.running = False
        
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000
        if elapsed >= WIN_TIME and self.game_status == "running":
            self.game_status = "win"
            self.running = False
    
    def draw(self):
        self.screen.fill(BLUE)
        pygame.draw.line(self.screen, WHITE, (SCREEN_WIDTH//2, 0), (SCREEN_WIDTH//2, SCREEN_HEIGHT), 2)
        pygame.draw.circle(self.screen, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 60, 2)
        
        self.ball.draw(self.screen)
        self.left_paddle.draw(self.screen)
        self.right_paddle.draw(self.screen)
        
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000
        
        if self.connection_error:
            error_text = self.big_font.render("CONNECTION FAILED", True, (255, 0, 0))
            self.screen.blit(error_text, (SCREEN_WIDTH//2 - error_text.get_width()//2, SCREEN_HEIGHT//2 - 100))
            msg_text = self.small_font.render(self.error_message, True, (255, 0, 0))
            self.screen.blit(msg_text, (SCREEN_WIDTH//2 - msg_text.get_width()//2, SCREEN_HEIGHT//2 - 30))
            retry_text = self.small_font.render("Trying to reconnect...", True, (255, 255, 0))
            self.screen.blit(retry_text, (SCREEN_WIDTH//2 - retry_text.get_width()//2, SCREEN_HEIGHT//2 + 20))
        
        time_text = self.font.render(f"Time: {int(elapsed)}s", True, WHITE)
        self.screen.blit(time_text, (10, 10))
        
        mode_text = self.font.render(f"Player {self.player_id}", True, (255, 255, 0))
        self.screen.blit(mode_text, (SCREEN_WIDTH - 150, 10))
        
        if self.game_status == "win":
            win_text = self.big_font.render("YOU WIN!", True, (0, 255, 0))
            self.screen.blit(win_text, (SCREEN_WIDTH//2 - win_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Press R to restart", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 20))
        elif self.game_status == "lose":
            lose_text = self.big_font.render("YOU LOSE!", True, (255, 0, 0))
            self.screen.blit(lose_text, (SCREEN_WIDTH//2 - lose_text.get_width()//2, SCREEN_HEIGHT//2 - 50))
            restart_text = self.font.render("Press R to restart", True, WHITE)
            self.screen.blit(restart_text, (SCREEN_WIDTH//2 - restart_text.get_width()//2, SCREEN_HEIGHT//2 + 20))
    
    def restart(self):
        self.game_status = "running"
        self.running = True
        self.start_time = pygame.time.get_ticks()
        self.ball.reset()
        self.left_paddle.set_position(30, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.right_paddle.set_position(SCREEN_WIDTH - 30 - PADDLE_WIDTH, SCREEN_HEIGHT//2 - PADDLE_HEIGHT//2)
        self.update_game_state()
        if self.player_id == 1:
            self.sync_to_server()
    
    def run(self):
        frame_count = 0
        reconnect_counter = 0
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        return
                    if event.key == pygame.K_r and (self.game_status == "win" or self.game_status == "lose"):
                        self.restart()
            
            if self.connection_error:
                reconnect_counter += 1
                if reconnect_counter % 60 == 0:
                    if test_connection(self.url):
                        self.connection_error = False
                        self.error_message = ""
                        print("Reconnected successfully!")
                        if self.player_id == 1:
                            self.sync_to_server()
                        else:
                            self.sync_from_server()
            
            if self.running and not self.connection_error:
                if self.player_id == 1:
                    self.handle_input()
                    self.ball.update()
                    self.check_collisions()
                    self.update_game_state()
                    frame_count += 1
                    if frame_count % 2 == 0:
                        self.sync_to_server()
                else:
                    self.sync_from_server()
                    if not self.connection_error:
                        self.handle_input()
                        self.update_game_state()
                        self.sync_to_server()
            
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)

if __name__ == "__main__":
    args = parse_arguments()
    game = Game(args.connect, args.player_id)
    game.run()

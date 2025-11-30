import pygame
import random
import time

# 初始化pygame
pygame.init()

# 定义颜色
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# 游戏设置
WIDTH, HEIGHT = 600, 600
GRID_SIZE = 20
GRID_WIDTH = WIDTH // GRID_SIZE
GRID_HEIGHT = HEIGHT // GRID_SIZE
FPS = 10

# 创建游戏窗口
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption('贪吃蛇游戏')
clock = pygame.time.Clock()

# 字体设置
font = pygame.font.SysFont('simhei', 25)

class Snake:
    def __init__(self):
        self.positions = [(GRID_WIDTH // 2, GRID_HEIGHT // 2)]
        self.direction = (1, 0)  # 初始向右移动
        self.length = 1
        self.score = 0
        self.grow = False

    def get_head_position(self):
        return self.positions[0]

    def move(self):
        head_x, head_y = self.get_head_position()
        dir_x, dir_y = self.direction
        new_x = (head_x + dir_x) % GRID_WIDTH
        new_y = (head_y + dir_y) % GRID_HEIGHT
        
        # 检查是否撞到自己
        if (new_x, new_y) in self.positions[1:]:
            return False
        
        self.positions.insert(0, (new_x, new_y))
        if not self.grow:
            self.positions.pop()
        else:
            self.grow = False
            self.length += 1
            self.score += 10
        
        return True

    def change_direction(self, new_direction):
        # 防止直接反向移动
        if (new_direction[0] * -1, new_direction[1] * -1) != self.direction:
            self.direction = new_direction

    def grow_snake(self):
        self.grow = True

    def draw(self, surface):
        for i, (x, y) in enumerate(self.positions):
            color = GREEN if i == 0 else BLUE  # 蛇头绿色，蛇身蓝色
            rect = pygame.Rect(x * GRID_SIZE, y * GRID_SIZE, GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(surface, color, rect)
            pygame.draw.rect(surface, BLACK, rect, 1)  # 黑色边框

class Food:
    def __init__(self, snake_positions):
        self.position = self.randomize_position(snake_positions)

    def randomize_position(self, snake_positions):
        while True:
            position = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
            if position not in snake_positions:
                return position

    def draw(self, surface):
        rect = pygame.Rect(self.position[0] * GRID_SIZE, self.position[1] * GRID_SIZE, GRID_SIZE, GRID_SIZE)
        pygame.draw.rect(surface, RED, rect)
        pygame.draw.rect(surface, BLACK, rect, 1)  # 黑色边框

def draw_grid(surface):
    for y in range(0, HEIGHT, GRID_SIZE):
        for x in range(0, WIDTH, GRID_SIZE):
            rect = pygame.Rect(x, y, GRID_SIZE, GRID_SIZE)
            pygame.draw.rect(surface, BLACK, rect, 1)

def show_score(surface, score):
    score_text = font.render(f'得分: {score}', True, BLACK)
    surface.blit(score_text, (10, 10))

def game_over_screen(surface, score):
    surface.fill(WHITE)
    game_over_text = font.render('游戏结束!', True, RED)
    score_text = font.render(f'最终得分: {score}', True, BLACK)
    restart_text = font.render('按R键重新开始', True, BLACK)
    
    surface.blit(game_over_text, (WIDTH // 2 - 50, HEIGHT // 2 - 50))
    surface.blit(score_text, (WIDTH // 2 - 60, HEIGHT // 2))
    surface.blit(restart_text, (WIDTH // 2 - 70, HEIGHT // 2 + 50))
    pygame.display.update()

def main():
    snake = Snake()
    food = Food(snake.positions)
    game_over = False
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            elif event.type == pygame.KEYDOWN:
                if game_over:
                    if event.key == pygame.K_r:
                        # 重新开始游戏
                        snake = Snake()
                        food = Food(snake.positions)
                        game_over = False
                else:
                    if event.key == pygame.K_UP:
                        snake.change_direction((0, -1))
                    elif event.key == pygame.K_DOWN:
                        snake.change_direction((0, 1))
                    elif event.key == pygame.K_LEFT:
                        snake.change_direction((-1, 0))
                    elif event.key == pygame.K_RIGHT:
                        snake.change_direction((1, 0))
        
        if not game_over:
            # 移动蛇
            if not snake.move():
                game_over = True
            
            # 检查是否吃到食物
            if snake.get_head_position() == food.position:
                snake.grow_snake()
                food = Food(snake.positions)
            
            # 绘制游戏
            screen.fill(WHITE)
            draw_grid(screen)
            snake.draw(screen)
            food.draw(screen)
            show_score(screen, snake.score)
            pygame.display.update()
            
            # 控制游戏速度
            clock.tick(FPS)
        else:
            game_over_screen(screen, snake.score)

if __name__ == "__main__":
    main()
import pygame
from pygame.math import Vector2

from colors import Colors
from settings import *


class Player(pygame.sprite.Sprite):
    def __init__(self, pos, groups, collision_sprites) -> None:
        super().__init__(groups)

        # --- Visual rendering ---
        self.image = pygame.Surface((48, 56))
        self.image.fill(Colors.green)
        self.rect: pygame.FRect = self.image.get_frect(topleft=pos)
        self.old_rect = self.rect.copy()

        # --- Environment ---
        self.collision_sprites = collision_sprites
        self.on_surface = {"floor": False, "left": False, "right": False}

        # --- Movement & Control ---
        self.velocity = Vector2(0, 0)
        self.speed = SPEED
        self.floor_control = 15.0
        self.air_control = 4.0

        # --- Gravity & Wall Slide ---
        self.normal_gravity = GRAVITY
        self.slide_gravity = GRAVITY * 0.15
        self.max_slide_speed = 80

        # --- Jump Settings ---
        self.jump_height = JUMP_HEIGHT
        self.max_jumps = 2
        self.jumps_left = self.max_jumps
        self.wall_jump_height = JUMP_HEIGHT * 0.85
        self.wall_jump_boost = 1.8

        # --- Input state ---
        self.jump_requested = False
        self.space_held = False
        self.left_held = False
        self.right_held = False

    def get_input(self):
        """Retrieves the state of keys to define movement intentions."""
        keys = pygame.key.get_pressed()

        self.left_held = keys[pygame.K_LEFT]
        self.right_held = keys[pygame.K_RIGHT]

        # Jump detection (single press)
        if keys[pygame.K_SPACE]:
            if not self.space_held:
                self.jump_requested = True
                self.space_held = True
        else:
            self.space_held = False

        if keys[pygame.K_r]:
            self.reset_position()

    def apply_horizontal_movement(self, delta_time):
        """Calculates and applies horizontal velocity (lerp)."""
        target_speed = 0
        if self.right_held:
            target_speed += self.speed
        if self.left_held:
            target_speed -= self.speed

        control_factor = (
            self.floor_control if self.on_surface["floor"] else self.air_control
        )

        self.velocity.x = pygame.math.lerp(
            self.velocity.x, target_speed, min(1.0, control_factor * delta_time)
        )

    def handle_jump(self):
        """Handles jump logic, double jump and wall jump."""
        if not self.jump_requested:
            return

        # Consume the input immediately to avoid ghost jump bug
        self.jump_requested = False

        # If we requested a jump but have no jumps left, cancel
        if self.jumps_left <= 0:
            return

        if self.on_surface["floor"]:
            # Standard ground jump
            self.velocity.y = -self.jump_height

        elif self.on_surface["left"] or self.on_surface["right"]:
            # Wall jump
            direction = 1 if self.on_surface["left"] else -1
            self.velocity.x = self.speed * self.wall_jump_boost * direction
            self.velocity.y = -self.wall_jump_height

        else:
            # Double jump in mid-air
            self.velocity.y = -self.jump_height

        # Reduce jump count
        self.jumps_left -= 1

    def apply_gravity(self, delta_time):
        """Applies normal gravity or slowed gravity when wall sliding."""
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        is_wall_sliding = not self.on_surface["floor"] and (
            on_left_wall or on_right_wall
        )

        if is_wall_sliding:
            self.velocity.y += self.slide_gravity * delta_time
            self.velocity.y = min(self.velocity.y, self.max_slide_speed)
        else:
            self.velocity.y += self.normal_gravity * delta_time

    def check_contact(self):
        """Checks whether the player is touching the ground or walls."""
        height_quarter = self.rect.height / 4
        half_height = self.rect.height / 2

        floor_rect = pygame.FRect(self.rect.bottomleft, (self.rect.width, 2))
        right_rect = pygame.FRect(
            self.rect.topright + Vector2(0, height_quarter), (2, half_height)
        )
        left_rect = pygame.FRect(
            self.rect.topleft + Vector2(-2, height_quarter), (2, half_height)
        )

        collide_rects = [sprite.rect for sprite in self.collision_sprites]

        self.on_surface["floor"] = floor_rect.collidelist(collide_rects) >= 0
        self.on_surface["right"] = right_rect.collidelist(collide_rects) >= 0
        self.on_surface["left"] = left_rect.collidelist(collide_rects) >= 0

        if self.on_surface["floor"]:
            self.jumps_left = self.max_jumps

    def move(self, delta_time):
        """Orchestrates movements and handles collisions axis by axis."""
        # 1. Horizontal movement
        self.apply_horizontal_movement(delta_time)
        self.rect.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")

        # 2. Vertical movement
        self.handle_jump()
        self.apply_gravity(delta_time)
        self.rect.y += self.velocity.y * delta_time
        self.handle_collisions("vertical")

    def handle_collisions(self, axis):
            """Handles repositioning when colliding with an obstacle."""
            collided_sprites = pygame.sprite.spritecollide(self, self.collision_sprites, False)
            
            for sprite in collided_sprites:
                if axis == "horizontal":
                    if self.velocity.x > 0:
                        self.rect.right = sprite.rect.left
                    elif self.velocity.x < 0:
                        self.rect.left = sprite.rect.right
                    self.velocity.x = 0

                elif axis == "vertical":
                    if self.velocity.y > 0:
                        self.rect.bottom = sprite.rect.top
                    elif self.velocity.y < 0:
                        self.rect.top = sprite.rect.bottom
                    self.velocity.y = 0

    def reset_position(self):
        """Resets the player to the center of the screen."""
        self.rect.center = (WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2)
        self.velocity = Vector2(0, 0)
        self.jumps_left = self.max_jumps
        self.jump_requested = False
        self.old_rect = self.rect.copy()

    def update(self, delta_time):
        """Main update loop for the player."""
        self.old_rect = self.rect.copy()
        self.check_contact()
        self.get_input()
        self.move(delta_time)
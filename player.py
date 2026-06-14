import pygame

from colors import Colors
from entity import Entity
from settings import JUMP_HEIGHT, SPEED


class Player(Entity):
    def __init__(self, pos, groups, collision_sprites, moving_platforms):
        super().__init__(pos, (48, 56), Colors.green, groups, collision_sprites)

        self.speed = SPEED
        self.floor_control = 15.0
        self.air_control = 4.0

        self.jump_height = JUMP_HEIGHT
        self.wall_jump_height = JUMP_HEIGHT * 0.85
        self.wall_jump_boost = 1.8

        self.max_midair_jumps = 1
        self.midair_jumps_left = self.max_midair_jumps
        self.max_wall_jumps = 9999
        self.wall_jumps_left = self.max_wall_jumps

        self.jump_requested = False
        self.space_held = False
        self.left_held = False
        self.right_held = False

        self.moving_platforms = moving_platforms

    def _is_wall_sliding(self):
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return not self.on_surface["floor"] and (on_left_wall or on_right_wall)

    def _on_floor_contact(self):
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def _on_wall_contact(self):
        self.midair_jumps_left = self.max_midair_jumps

    def get_input(self):
        keys = pygame.key.get_pressed()
        self.left_held = keys[pygame.K_LEFT]
        self.right_held = keys[pygame.K_RIGHT]

        if keys[pygame.K_SPACE]:
            if not self.space_held:
                self.jump_requested = True
                self.space_held = True
        else:
            self.space_held = False

        if keys[pygame.K_r]:
            self.reset_position()

    def apply_horizontal_movement(self, delta_time):
        target_speed = (self.right_held - self.left_held) * self.speed
        control = self.floor_control if self.on_surface["floor"] else self.air_control
        self.velocity.x = pygame.math.lerp(
            self.velocity.x, target_speed, min(1.0, control * delta_time)
        )

    def handle_jump(self):
        if not self.jump_requested:
            return
        self.jump_requested = False

        if self.on_surface["floor"]:
            self.velocity.y = -self.jump_height
        elif self.on_surface["left"] or self.on_surface["right"]:
            if self.wall_jumps_left > 0:
                direction = 1 if self.on_surface["left"] else -1
                self.velocity.x = self.speed * self.wall_jump_boost * direction
                self.velocity.y = -self.wall_jump_height
                self.wall_jumps_left -= 1
        elif self.midair_jumps_left > 0:
            self.velocity.y = -self.jump_height
            self.midair_jumps_left -= 1

    def move(self, delta_time):
        self.apply_moving_platform(self.moving_platforms)

        self.apply_horizontal_movement(delta_time)
        self.rect.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")

        self.handle_jump()
        self.apply_gravity(delta_time)
        self.rect.y += self.velocity.y * delta_time
        self.handle_collisions("vertical")

    def reset_position(self):
        super().reset_position()
        self.jump_requested = False
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def update(self, delta_time):
        super().update(delta_time)
        self.get_input()
        self.move(delta_time)
        self.apply_moving_platform(self.moving_platforms)

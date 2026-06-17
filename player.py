import pygame

from colors import Colors
from entity import Entity
from settings import JUMP_HEIGHT, SPEED


class Player(Entity):
    """
    Represents the playable character with precise, responsive platforming physics
    inspired by modern tight-control platformers like Celeste.
    """

    def __init__(self, pos, groups, collision_sprites, moving_platforms):
        super().__init__(
            pos,
            (48, 56),
            Colors.green,
            groups,
            collision_sprites,
            hitbox_inflate=(-8, 0),
        )

        self.speed = SPEED
        self.floor_control = 25.0
        self.air_control = 12.0

        # Jump physics
        self.jump_height = JUMP_HEIGHT
        self.wall_jump_height = JUMP_HEIGHT * 0.90
        self.wall_jump_boost = 1.6
        self.wall_slide_speed = 100.0

        # Jump counters
        self.max_midair_jumps = 1
        self.midair_jumps_left = self.max_midair_jumps
        self.max_wall_jumps = 9999
        self.wall_jumps_left = self.max_wall_jumps

        # Input states
        self.space_held = False
        self.left_held = False
        self.right_held = False

        self.coyote_timer = 0.0
        self.coyote_duration = 0.12

        self.jump_buffer_timer = 0.0
        self.jump_buffer_duration = 0.10

        self.wall_jump_timer = 0.0
        self.wall_jump_duration = 0.15

        self.moving_platforms = moving_platforms

    def _is_wall_sliding(self):
        """Checks if the player is actively pressing against a wall while falling."""
        on_left_wall = self.on_surface["left"] and self.left_held
        on_right_wall = self.on_surface["right"] and self.right_held
        return (
            not self.on_surface["floor"]
            and (on_left_wall or on_right_wall)
            and self.velocity.y > 0
        )

    def _on_floor_contact(self):
        """Resets jump resources upon touching the ground."""
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def _on_wall_contact(self):
        """Resets mid-air resources upon touching a wall."""
        self.midair_jumps_left = self.max_midair_jumps

    def get_input(self):
        """Gathers and processes keyboard inputs."""
        keys = pygame.key.get_pressed()
        self.left_held = keys[pygame.K_LEFT]
        self.right_held = keys[pygame.K_RIGHT]

        if keys[pygame.K_SPACE]:
            if not self.space_held:
                self.jump_buffer_timer = self.jump_buffer_duration
                self.space_held = True
        else:
            self.space_held = False

        if keys[pygame.K_r]:
            self.reset_position()

    def update_timers(self, delta_time):
        """Decrements all game-feel buffers and timers."""
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= delta_time
        if self.wall_jump_timer > 0:
            self.wall_jump_timer -= delta_time

        if self.on_surface["floor"]:
            self.coyote_timer = self.coyote_duration
        elif self.coyote_timer > 0:
            self.coyote_timer -= delta_time

    def apply_horizontal_movement(self, delta_time):
        """Calculates and interpolates horizontal velocity based on context and inputs."""
        if self.wall_jump_timer > 0:
            return

        target_speed = (self.right_held - self.left_held) * self.speed
        control = self.floor_control if self.on_surface["floor"] else self.air_control
        self.velocity.x = pygame.math.lerp(
            self.velocity.x, target_speed, min(1.0, control * delta_time)
        )

    def handle_jump(self):
        """Evaluates jump requests against buffered inputs and physics context."""
        if self.jump_buffer_timer <= 0:
            return

        if self.coyote_timer > 0:
            self.velocity.y = -self.jump_height
            self.jump_buffer_timer = 0
            self.coyote_timer = 0

        elif (
            self.on_surface["left"] or self.on_surface["right"]
        ) and self.wall_jumps_left > 0:
            direction = 1 if self.on_surface["left"] else -1
            self.velocity.x = self.speed * self.wall_jump_boost * direction
            self.velocity.y = -self.wall_jump_height
            self.wall_jumps_left -= 1
            self.jump_buffer_timer = 0
            self.wall_jump_timer = self.wall_jump_duration

        elif self.midair_jumps_left > 0:
            self.velocity.y = -self.jump_height
            self.midair_jumps_left -= 1
            self.jump_buffer_timer = 0

    def move(self, delta_time):
        """Performs full physics resolution sequence including collisions and movement application."""
        self.apply_moving_platform(self.moving_platforms)

        self.apply_horizontal_movement(delta_time)
        self.hitbox.x += self.velocity.x * delta_time
        self.handle_collisions("horizontal")

        self.handle_jump()

        if self._is_wall_sliding():
            self.velocity.y = self.wall_slide_speed
        else:
            self.apply_gravity(delta_time)

        self.hitbox.y += self.velocity.y * delta_time
        self.handle_collisions("vertical")

        self.check_contact()

    def reset_position(self):
        """Resets player position and fully replenishes state variables."""
        super().reset_position()
        self.jump_buffer_timer = 0.0
        self.wall_jump_timer = 0.0
        self.coyote_timer = 0.0
        self.midair_jumps_left = self.max_midair_jumps
        self.wall_jumps_left = self.max_wall_jumps

    def update(self, delta_time):
        """Core update cycle invoked each frame."""
        super().update(delta_time)
        self.get_input()
        self.update_timers(delta_time)
        self.move(delta_time)

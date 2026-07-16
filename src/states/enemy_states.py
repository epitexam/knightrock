"""
États de la machine d'état pour les ennemis (IA).
"""

import random
import pygame
from src.states.state_machine import State


class EnemyIdleState(State):
    """État d'attente : l'ennemi reste immobile un court instant."""

    def enter(self, previous=None):
        self.timer = self.entity.idle_duration

    def update(self, delta_time):
        self.timer -= delta_time
        if self.timer <= 0:
            if self.entity.can_see_player():
                self.entity.state_machine.change_state("chase")
            else:
                self.entity.state_machine.change_state("patrol")


class EnemyPatrolState(State):
    """État de patrouille : l'ennemi se déplace dans une direction."""

    def enter(self, previous=None):
        self.patrol_timer = self.entity.patrol_interval
        self.direction = self.entity.patrol_direction

    def update(self, delta_time):
        self.entity.move_axis = self.direction
        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.can_see_player():
            self.entity.state_machine.change_state("chase")
            return

        self.patrol_timer -= delta_time
        if self.patrol_timer <= 0:
            self.direction *= -1
            self.patrol_timer = self.entity.patrol_interval
            self.entity.facing_right = self.direction > 0

    def exit(self, next_state=None):
        self.entity.move_axis = 0.0


class EnemyChaseState(State):
    """État de poursuite : l'ennemi se dirige vers le joueur."""

    def enter(self, previous=None):
        self.entity.face_player()

    def update(self, delta_time):
        if self.entity.player is None:
            self.entity.state_machine.change_state("idle")
            return

        player_center = self.entity.player.hitbox.centerx
        enemy_center = self.entity.hitbox.centerx
        if abs(player_center - enemy_center) < 10:
            self.entity.move_axis = 0.0
        else:
            self.entity.move_axis = 1.0 if player_center > enemy_center else -1.0
            self.entity.facing_right = self.entity.move_axis > 0

        self.entity.apply_horizontal_movement(delta_time)

        if self.entity.is_player_in_range():
            self.entity.state_machine.change_state("attack")
        elif not self.entity.can_see_player():
            self.entity.state_machine.change_state("idle")


class EnemyAttackState(State):
    """État d'attaque : l'ennemi exécute son attaque."""

    def enter(self, previous=None):
        self.entity.face_player()

        if self.entity.attack_name is not None:
            self.entity.combat.start_attack(self.entity.attack_name)
        self._started = True

    def update(self, delta_time):
        if not self.entity.combat.is_attacking:
            self.entity.state_machine.change_state("idle")

    def exit(self, next_state=None):
        self._started = False


class EnemyHurtState(State):
    """État de réaction aux dégâts (hurt)."""

    def enter(self, previous=None):
        pass

    def update(self, delta_time):
        if not self.entity.combat.is_hurt:
            self.entity.state_machine.change_state("idle")


class EnemyStaggerState(State):
    """État de stagger (étourdissement)."""

    def enter(self, previous=None):
        pass

    def update(self, delta_time):
        if self.entity.stagger_timer <= 0:
            self.entity.state_machine.change_state("idle")

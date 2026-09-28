"""Enemy construction: the concrete types, their configs and the factory.

``Enemy`` is imported by the enemy states and the level, ``EnemyConfig`` /
``ENEMY_CONFIGS`` by the data layer and the tests, and ``create_enemy`` /
``is_enemy_type`` by the spawn system -- each from the module that defines it.
Nothing is re-exported here; the two factory names had no caller at all.
"""

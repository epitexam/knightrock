import os
from src.core.game import Game


def main():
    game = Game()
    game.run()


def main_debug():
    """Launch the game in debug mode."""
    os.environ["DEBUG"] = "1"
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
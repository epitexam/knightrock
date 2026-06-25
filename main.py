import os
from src.core.game import Game


def main():
    print("Hello from knightrock!")
    game = Game()
    game.run()


def main_debug():
    """Launch the game in debug mode."""
    os.environ["DEBUG"] = "1"
    print("Hello from knightrock! (DEBUG MODE)")
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
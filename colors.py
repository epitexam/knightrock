class Colors:
    dark_grey = (24, 28, 36)
    green = (56, 220, 90)
    red = (235, 70, 70)
    orange = (245, 140, 60)
    yellow = (245, 230, 90)
    purple = (170, 85, 235)
    cyan = (80, 220, 230)
    blue = (70, 110, 235)
    white = (245, 245, 245)
    dark_blue = (40, 45, 90)
    light_blue = (90, 130, 200)
    white = (255, 255, 255)

    @classmethod
    def get_cell_colors(cls):
        return [
            cls.dark_grey,
            cls.green,
            cls.red,
            cls.orange,
            cls.yellow,
            cls.purple,
            cls.cyan,
            cls.blue,
            cls.white,
        ]
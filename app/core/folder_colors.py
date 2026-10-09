"""Vivid, high-contrast folder colors shared by note and file folders."""

FOLDER_COLORS = (
    "#2387F5",  # blue
    "#E53935",  # red
    "#FF7A00",  # orange
    "#7B2FF7",  # purple
    "#00A6E8",  # sky blue
    "#D81B60",  # pink
    "#2E9B45",  # green
    "#F4B400",  # golden yellow
    "#3949AB",  # indigo
    "#A52DB5",  # violet
    "#546E7A",  # slate
    "#7CB342",  # lime green
)


def folder_color_at(index: int) -> str:
    """Return a stable vivid color, extending the palette for large libraries."""
    if index < len(FOLDER_COLORS):
        return FOLDER_COLORS[index]

    hue = ((index - len(FOLDER_COLORS)) * 137.508 + 19) % 360
    saturation, lightness = 0.78, 0.52
    chroma = (1 - abs(2 * lightness - 1)) * saturation
    section = hue / 60
    second = chroma * (1 - abs(section % 2 - 1))
    if section < 1:
        red, green, blue = chroma, second, 0
    elif section < 2:
        red, green, blue = second, chroma, 0
    elif section < 3:
        red, green, blue = 0, chroma, second
    elif section < 4:
        red, green, blue = 0, second, chroma
    elif section < 5:
        red, green, blue = second, 0, chroma
    else:
        red, green, blue = chroma, 0, second
    offset = lightness - chroma / 2
    channels = (red + offset, green + offset, blue + offset)
    return "#" + "".join(f"{round(channel * 255):02X}" for channel in channels)


def next_folder_color(existing_colors: list[str]) -> str:
    """Choose the first unused palette color, extending it when needed."""
    used = {color.upper() for color in existing_colors if color}
    index = 0
    while (color := folder_color_at(index)) in used:
        index += 1
    return color

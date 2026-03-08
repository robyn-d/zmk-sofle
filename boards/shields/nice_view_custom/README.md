# A nice!view

The nice!view is a low-power, high refresh rate display meant to replace I2C OLEDs traditionally used.

This shield requires that an `&nice_view_spi` labeled SPI bus is provided with _at least_ MOSI, SCK, and CS pins defined.

## Disable custom widget

The nice!view shield includes a custom vertical widget. To use the built-in ZMK one, add the following item to your `.conf` file:

```
CONFIG_ZMK_DISPLAY_STATUS_SCREEN_BUILT_IN=y
CONFIG_ZMK_LV_FONT_DEFAULT_SMALL_MONTSERRAT_26=y
CONFIG_LV_FONT_DEFAULT_MONTSERRAT_26=y
```

## Generate your own right-side art/animation

`widgets/art.c` and `widgets/art.h` are generated files. Use:

```bash
python scripts/generate_nice_view_art.py path/to/image_or_gif
```

You can also pass multiple files or a directory:

```bash
python scripts/generate_nice_view_art.py assets/nice-view-frames/
```

Useful options:

```bash
python scripts/generate_nice_view_art.py assets/nice-view-frames \
  --width 140 --height 68 \
  --threshold 128 \
  --resize-mode contain \
  --rotate cw \
  --frame-duration-ms 100
```

This writes:

- `boards/shields/nice_view_custom/widgets/art.c`
- `boards/shields/nice_view_custom/widgets/art.h`

Dependency:

```bash
python -m pip install pillow
```

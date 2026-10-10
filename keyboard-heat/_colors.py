"""打印各热度下的配色值 —— 调底火层颜色时不用靠肉眼猜。

    .pyenv\\Scripts\\python.exe _colors.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flame  # noqa: E402


def main():
    print("d=190 时各档：h_main / h_floor(px)")
    for h in (0.0, 0.05, 0.1, 0.25, 0.5, 0.8, 1.0):
        hm = flame.flame_height(h, 190.0 * flame.FLAME_MAX_H_K)
        hf = 190.0 * flame.FLAME_FLOOR_MIN_K      # 无贴图时的兜底高度
        print("  heat %.2f  main %6.1f  floor(min) %6.1f  ratio %.2f"
              % (h, hm, hf, hf / hm))

    print("\n配色（RGB）")
    for h in (0.0, 0.05, 0.1, 0.25, 0.5, 1.0):
        o, m, c = flame.flame_colors(h)
        fb, ft = flame.flame_floor_colors(h)
        print("  heat %.2f" % h)
        print("     main   outer=%-16s mid=%-16s core=%s" % (o, m, c))
        print("     floor  bottom=%-16s top=%s" % (fb, ft))

    print("\nfire_heat 的实际取值（决定空闲/暂停落在哪一档）")
    for frac, st in ((0.0, "idle"), (0.0, "paused"), (0.1, "typing"),
                     (0.25, "typing"), (0.5, "typing"), (1.0, "typing")):
        print("  frac=%.2f state=%-8s -> %.3f" % (frac, st, flame.fire_heat(frac, st)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

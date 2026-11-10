"""Compare a converted PS1 block with the block the PS1 game wrote after loading it.

Shows which regions the game changed when it re-saved (including the PS1-only regions the
PC->PS1 writer zero-fills). Usage:
  python -P tools/compare_ps1_rewrite.py <card> <converted block#> <game-written block#>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ffix_conv import ps1_card, ps1_save  # noqa: E402

REGIONS = [(0, 0x100, "header/icon"), (0x100, 0x134, "preview header"), (0x134, 0x174, "preview party"),
           (0x174, 0x180, "0x174 (save counter)"), (0x180, 0x1C0, "state"), (0x1C0, 0x9C0, "gEventGlobal"),
           (0x9C0, 0x9D0, "0x9C0"), (0x9D0, 0xEE0, "players"), (0xEE0, 0xEF2, "party"), (0xEF2, 0xF20, "0xEF2"),
           (0xF20, 0x1160, "items/key items"), (0x1160, 0x1178, "0x1160"), (0x1178, 0x13F4, "cards"),
           (0x13F4, 0x13FE, "0x13F4")]


def main(card, b1, b2):
    _, es = ps1_card.parse_file(open(card, "rb").read())
    blk = {e.block_index: e for e in es}
    a = ps1_save.PS1Save(blk[int(b1)].data, blk[int(b1)].product_code, blk[int(b1)].filename)
    b = ps1_save.PS1Save(blk[int(b2)].data, blk[int(b2)].product_code, blk[int(b2)].filename)
    print("blocks:", [(e.block_index, e.filename) for e in es])
    print("crc ok converted/game:", a.crc_ok, b.crc_ok)
    for lo, hi, n in REGIONS:
        d = [i for i in range(lo, hi) if a.block[i] != b.block[i]]
        if d:
            print(f"{n:22} {len(d):4} bytes differ   converted={a.block[lo:hi][:20].hex()}   game={b.block[lo:hi][:20].hex()}")
    for i, (p, q) in enumerate(zip(a.players(), b.players())):
        d = [o for o in range(144) if p.raw[o] != q.raw[o]]
        if d:
            print(f"  player {i} {p.name}: offsets {[hex(o) for o in d][:16]}")
    print("party converted/game:", a.party(), b.party())


if __name__ == "__main__":
    main(*sys.argv[1:4])

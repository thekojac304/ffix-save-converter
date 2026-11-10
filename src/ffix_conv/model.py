"""Platform-independent FF9 save state ("canonical model").

The canonical model is a JSON-serialisable dict. Both parsers fill it, the PC
serializer consumes it. Values use the PC/Memoria field names because the 2016
release serialises a direct port of the PS1 game structures; where the two
platforms encode a value differently the transform lives in the parser, never
in the model.

FIELD_MAP is the single source of truth for the field-mapping matrix and the
per-conversion report. Classes:
  verified-equivalent    same meaning and encoding, shown on real cross-platform fixtures
  verified-transformable same meaning, deterministic transform, shown on fixtures
  inferred               same struct position/semantics by strong structural evidence,
                         but no fixture pair proves the exact value
  unknown                PS1 location/meaning not established
  platform-specific      exists on one platform only
  incompatible           cannot be represented on the target
"""
import base64
import struct

from . import pc_schema, ps1_save

# (canonical path, PS1 location, PC path, type, transform, class, evidence, test)
FIELD_MAP = [
    ("state.mode", "0x180 u8", "10000_State.mode", "u8", "copy", "inferred",
     "1 on field saves, 3 on world-map saves in both corpora; PC pair 'Steeple' mode=1 equals PS1", "test_cross_platform_state"),
    ("state.prevMode", "0x181 u8", "10000_State.prevMode", "u8", "copy", "inferred",
     "Steeple pair equal (1/1); values 1/3/9 consistent with mode codes", "test_cross_platform_state"),
    ("state.fldMapNo", "0x1A0 i16", "10000_State.fldMapNo", "i16", "copy", "verified-equivalent",
     "Steeple pair 115==115; Gulug pair (scenario 9950) uses same field-ID space", "test_cross_platform_state"),
    ("state.fldLocNo", "0x1A2 i16", "10000_State.fldLocNo", "i16", "copy", "verified-equivalent",
     "Steeple pair 33==33", "test_cross_platform_state"),
    ("state.btlMapNo", "0x1A4 i16", "10000_State.btlMapNo", "i16", "copy", "verified-equivalent",
     "Steeple pair 336==336", "test_cross_platform_state"),
    ("state.btlSubMapNo", "0x1A6 i8 (0x1A7 = sign extension)", "10000_State.btlSubMapNo", "i8", "copy",
     "verified-equivalent", "Steeple pair -1==-1; PS1 0/1 values occur with 0x1A7=00", "test_cross_platform_state"),
    ("state.wldMapNo", "0x1A8 i16", "10000_State.wldMapNo", "i16", "copy", "verified-equivalent",
     "PS1 values 9000-9011 match PC world-map IDs (9000/9003/9005/9008 seen on PC). Before the first "
     "world-map visit PS1 holds 9009 where PC holds 0; the PC overwrites it on world-map entry (ff9.cs)",
     "test_cross_platform_state"),
    ("state.wldLocNo", "0x1AA i16", "10000_State.wldLocNo", "i16", "copy", "verified-equivalent",
     "68 on every PS1 save and every post-intro PC save (PC: 0 before first world-map visit)", "test_cross_platform_state"),
    ("state.timeCounter/timerControl/timerDisplay", "unknown", "10000_State.timer*", "f32/bool", "default 0/False/False",
     "unknown", "PS1 countdown-timer storage not located; save points are outside timed sequences", "test_defaults"),
    ("event.gEventGlobal", "0x1C0..0x9BF (2048 B)", "20000_Event.gEventGlobal (base64 in String4K)", "bytes[2048]",
     "base64 encode", "verified-transformable",
     "Steeple pair 2024/2048 identical, Gulug pair 1846/2048 identical across different players; "
     "u16[0] is the scenario counter in both", "test_gevent_cross_platform"),
    ("ps1 disc", "0x104 bitmask 1/2/4/8", "-", "u8", "PC->PS1: from scenario-counter ranges; ambiguous gaps need --disc",
     "verified-transformable", "masks of all 82 PS1 saves agree with the ranges (incl. 'Start of DISC 2/3/4' saves)",
     "test_disc_derivation_and_ambiguity"),
    ("ps1 header/title/icon", "0x000-0x0FF", "-", "bytes", "PC->PS1: title 'FF9/FILEnn/hh:mm', project-drawn icon",
     "platform-specific", "title format observed on all PS1 saves; icon is cosmetic",
     "test_pc_ps1_pc_preserves_common_fields"),
    ("event.gStepCount", "unknown (0x9C0 u32 grows monotonically; unproven)", "20000_Event.gStepCount", "i32",
     "write 0", "platform-specific", "Every PC fixture stores 0; Memoria notes the PC never tracks it", "test_defaults"),
    ("players[].name", "+0x00 10 B PS1 text", "players[].name (UTF-8 String128)", "string", "PS1 text table -> UTF-8",
     "verified-transformable", "'Zidane', 'Dagger', '??????' identical on Steeple pair", "test_player_names"),
    ("players[].category", "+0x0A u8", "players[].category", "u8", "copy", "verified-equivalent", "Steeple pair 9/5/6", "test_player_core"),
    ("players[].level", "+0x0B u8", "players[].level", "u8", "copy", "verified-equivalent", "Steeple pair; documented by both editors", "test_player_core"),
    ("players[].exp", "+0x0C u32", "players[].exp", "u32", "copy", "verified-equivalent", "documented by both editors", "test_player_core"),
    ("players[].cur.*", "+0x10 hp u16, mp i16, at i16, at_coef i8, capa u8", "players[].cur", "struct", "copy",
     "verified-equivalent", "Steeple pair hp/mp/at_coef/capa equal (at is live ATB gauge)", "test_player_core"),
    ("players[].max.*", "+0x18 same layout", "players[].max", "struct", "copy", "verified-equivalent",
     "Steeple pair equal incl. at=5920", "test_player_core"),
    ("players[].trance", "+0x20 u8", "players[].trance", "u8", "copy", "verified-equivalent", "documented; plausible ranges", "test_player_core"),
    ("players[].web_bone", "+0x21 u8", "players[].web_bone", "u8", "copy", "verified-equivalent",
     "Gulug pair slots 0-7 identical; PC leaves it 0 at game start and in slot 8 while PS1 does not. "
     "Never read by the PC runtime (Memoria source)", "test_player_core"),
    ("players[].elem.*", "+0x24 dex,str,mgc,wpr u8", "players[].elem", "struct", "copy", "verified-equivalent", "Steeple pair", "test_player_core"),
    ("players[].defence.*", "+0x28 p_def,p_ev,m_def,m_ev u8", "players[].defence", "struct", "copy", "verified-equivalent", "Steeple pair", "test_player_core"),
    ("players[].basis.*", "+0x2C max_hp i16, max_mp i16, dex,str,mgc,wpr u8", "players[].basis", "struct", "copy",
     "verified-equivalent", "Steeple pair", "test_player_core"),
    ("players[].info", "+0x34 u32: bits0-3 slot_no, 4-8 serial_no, 9 row, 10 win_pose, 11 party, 12-16 menu_type",
     "players[].info", "bitfield -> 6 bytes", "unpack/pack bits; PS1 write rejects values over the bit widths",
     "verified-transformable",
     "Steeple pair: all 9 records identical incl. Blank serial 16 / Beatrix 18; Phase 2 audit found menu_type "
     "is 5 bits (early Cinna/Marcus/Blank = 17/18/19, matching the user's PC save) - fixed. Runtime: the PC "
     "recomputes serial_no (FF9Play_GetSerialID; Steiner is always 7 on PC, PS1 may hold 8) after battles",
     "test_menu_type_is_five_bits_regression"),
    ("players[].status", "+0x38 u8", "players[].status", "u8", "copy", "verified-equivalent", "documented", "test_player_core"),
    ("players[].equip[5]", "+0x39..0x3D", "players[].equip", "u8[5]", "copy", "verified-equivalent",
     "Steeple pair identical equipment IDs", "test_player_core"),
    ("players[].bonus.*", "+0x3E dex,str,mgc,wpr u16", "players[].bonus", "u16[4]", "copy", "verified-equivalent",
     "vanilla ff9level formulas (basis = base + level term + bonus>>5) give one constant base per character "
     "across all 763 PS1+PC records", "test_stat_growth_bonus_reproduces_vanilla_formula"),
    ("players[].bonus.cap", "+0x46 u16", "94000_Common.00001_player_bonus[i]", "u16->u32",
     "copy; PC->PS1: 0 -> (level-1)*5 (+extra for serial 10/11), the vanilla PC load rule", "verified-transformable",
     "vanilla FF9Level_GetCap formula consistent on all records; PC treats 0 as 'derive' (JsonParser), so PS1 "
     "guests with cap 0 (Beatrix, early Marcus) get the derived cap on PC exactly like native PC saves",
     "test_ps1_pc_ps1_preserves_gameplay_state"),
    ("players[].pa[48]", "+0x58 u8[48]", "players[].pa", "u8[48]", "copy", "verified-equivalent",
     "every AP value <= the vanilla PA-table requirement of its slot for the character's menu_type (763 records)",
     "test_support_abilities_and_ap_follow_vanilla_rules_on_every_record"),
    ("players[].sa[2]", "+0x88 u32[2]", "players[].sa", "u32[2]", "copy", "verified-equivalent",
     "vanilla bit test sa[n>>5]&(1<<n); for all 763 PS1+PC records cur.capa == max.capa - sum(gem cost of set "
     "bits) and every set bit is learnable by that character (otherwise vanilla unequips all SAs on load)",
     "test_support_abilities_and_ap_follow_vanilla_rules_on_every_record"),
    ("party.slot[4]", "0xEE0 u8[4], empty=9", "40000_Common.slot", "u8[4]", "9 -> 255", "verified-transformable",
     "Steeple pair [1,9,9,9] vs [1,255,255,255]", "test_party_slots"),
    ("party.escape_no", "0xEE4 u16", "40000_Common.escape_no", "u16", "copy", "verified-equivalent",
     "vanilla PARTY_DATA order; grows on escapes through the user's own PS1 run", "test_party_counters"),
    ("party.summon_flag", "0xEE6 u16", "40000_Common.summon_flag", "u16", "copy", "inferred",
     "struct order; PC fixtures are always 0 (PC may ignore it)", "test_party_counters"),
    ("party.gil", "0xEE8 u32", "40000_Common.gil", "u32", "copy", "verified-equivalent",
     "equals PS1 preview gil on all 54 PS1 saves; documented", "test_party_counters"),
    ("party.frog_no", "0xEEC i16", "40000_Common.frog_no", "i16", "copy", "verified-equivalent",
     "RAM order frog/steal/dragon (vanilla FF9StateGlobal; CodeBreaker codes 8008B7B8/8008B7BA); 0 until "
     "Qu's Marsh in both PS1 corpora", "test_steal_and_dragon_counters_regression"),
    ("party.steal_no", "0xEEE i16", "40000_Common.steal_no", "i16", "copy", "verified-equivalent",
     "user's PS1 run: 3 at the Steeple (the opening steals, as in every PC save) rising to 31",
     "test_steal_and_dragon_counters_regression"),
    ("party.dragon_no", "0xEF0 i16", "40000_Common.dragon_no", "i16", "copy", "verified-equivalent",
     "user's PS1 run: 0 until the world map opens, then grows", "test_steal_and_dragon_counters_regression"),
    ("items[256]", "0xF20 (id u8, count u8) x256", "40000_Common.items", "struct[256]", "copy", "verified-equivalent",
     "Steeple pair: same item IDs in same order", "test_items"),
    ("rare_items[64]", "0x1120 u8[64]", "40000_Common.rareItems", "u8[64]", "copy", "verified-equivalent",
     "vanilla ff9item: 2 bits per key item (obtained, used); on 9 exact story pairs the PC player's obtained "
     "items are a subset of the PS1 player's", "test_exact_story_pairs_with_user_save"),
    ("minigame.sWin/sLose/sDraw", "0x1178 i16 x3", "30000_MiniGame.sWin/sLose/sDraw", "i16", "copy", "inferred",
     "documented by gjoerulv", "test_cards"),
    ("minigame.cards", "0x117E (id, arrow, atk, type, pdef, mdef) x105", "30000_MiniGame.MiniGameCard[100]",
     "struct", "copy fields; side=0; cpoint=10; empty -> all 255; compact; >100 rejected",
     "verified-transformable", "field order documented by both editors; cpoint=10 for all 100 IDs across PC fixtures",
     "test_cards"),
    ("playtime", "preview 0x12C u32 frames", "95000_Setting.00001_time (f64 seconds)", "u32->f64",
     "frames / 60 (NTSC) or / 50 (PAL); reverse rounds to whole frames", "inferred", "magnitudes plausible vs story position; frame rate per gjoerulv notes",
     "test_playtime"),
    ("preview.location", "0x110 28 B PS1 text", "preview.Location", "string", "decode PS1 text", "verified-transformable",
     "cosmetic: the PC rebuilds it from the field on next save", "test_preview"),
    ("settings.cfg", "unknown", "50000_Setting.cfg", "struct",
     "PC template slot, else vanilla FF9CFG + HonoInputManager defaults; dropped PC->PS1",
     "unknown", "PS1 config location not established; defaults equal the bindings in the user's own PC save",
     "test_defaults_match_what_the_game_writes"),
    ("settings.time", "-", "50000_Setting.time", "f32", "write -1.0", "platform-specific", "PC always writes -1 (dummy)", "test_defaults"),
    ("sound.auto_save_bgm_id", "-", "60000_Sound.auto_save_bgm_id", "i32", "write -1", "platform-specific", "all PC fixtures -1", "test_defaults"),
    ("world.camera/hintmap", "unknown", "70000_World.*", "mixed", "copy from template else 0", "unknown",
     "world-map camera angle only; not progression", "test_defaults"),
    ("achievements", "-", "80000_Achievement.*, 98000_Achievement.*", "mixed",
     "counters 0; abilities/passiveAbilities/QuadmistWinList = -1 (game's empty marker); dropped PC->PS1",
     "platform-specific", "Steam achievement tracking; vanilla treats any value other than -1 as an entry",
     "test_defaults_match_what_the_game_writes"),
    ("reserved buffers", "-", "91000..99000 reserved arrays", "i32[]", "zero", "platform-specific",
     "all PC fixtures are zero", "test_defaults"),
]


def _b64(b):
    return base64.b64encode(bytes(b)).decode("ascii")


def from_ps1(save):
    """Build the canonical model from a ps1_save.PS1Save."""
    region, lang, disc = save.region
    players = []
    for p in save.players():
        f = p.fields()
        f["name"] = p.name
        f["name_fully_decoded"] = p.name_decoded
        f["_ps1_unmapped"] = p.unmapped()
        players.append(f)
    prev = save.preview()
    fps = 50 if region == "PAL" else 60
    party = save.party()
    return {
        "source": {"platform": "ps1", "product_code": save.product_code, "region": region, "language": lang,
                   "disc_hint": disc, "crc_ok": save.crc_ok, "crc_stored": save.crc_stored,
                   "crc_computed": save.crc_computed},
        "state": save.state(),
        "event": {"gEventGlobal_b64": _b64(save.gevent), "scenario_counter": save.scenario_counter,
                  "gStepCount": None},
        "players": players,
        "party": party,
        "items": [{"id": i, "count": c} for i, c in save.items()],
        "rare_items": save.rare_items(),
        "minigame": dict(save.card_stats(), cards=save.cards()),
        "playtime_seconds": prev["playtime_frames"] / fps,
        "preview": prev,
        "settings": None,
        "unmapped": {"ps1_regions": save.unknown_regions()},
        # the untouched source block: lets the PS1 writer restore PS1-only bytes losslessly
        # when writing back the same playthrough (never used for other saves)
        "platform_extra": {"ps1_block_b64": _b64(save.block[:ps1_save.BLOCK_USED]),
                           "ps1_filename": save.filename},
    }


def from_pc(tree):
    """Build the canonical model from a decoded PC slot tree (pc_schema.decode)."""
    d = tree["Data"]
    st, ev, cm, mg = d["10000_State"], d["20000_Event"], d["40000_Common"], d["30000_MiniGame"]
    g = base64.b64decode(pc_schema.string_value(ev["gEventGlobal"]))
    players = []
    for i, p in enumerate(cm["players"]):
        q = {k: v for k, v in p.items() if k != "name"}
        q["name"] = pc_schema.string_value(p["name"])
        q["bonus_cap"] = d["94000_Common"]["00001_player_bonus"][i]
        players.append(q)
    return {
        "source": {"platform": "pc"},
        "state": {k: st[k] for k in ("mode", "prevMode", "fldMapNo", "fldLocNo", "btlMapNo", "btlSubMapNo",
                                     "wldMapNo", "wldLocNo")},
        "state_pc_only": {k: st[k] for k in ("timeCounter", "timerControl", "timerDisplay")},
        "event": {"gEventGlobal_b64": _b64(g), "scenario_counter": struct.unpack_from("<H", g)[0],
                  "gStepCount": ev["gStepCount"]},
        "players": players,
        "party": {k: cm[k] for k in ("slot", "escape_no", "summon_flag", "gil", "frog_no", "steal_no", "dragon_no")},
        "items": [{"id": x["id"], "count": x["count"]} for x in cm["items"]],
        "rare_items": list(cm["rareItems"]),
        "minigame": {"sWin": mg["sWin"], "sLose": mg["sLose"], "sDraw": mg["sDraw"], "cards": mg["MiniGameCard"]},
        "playtime_seconds": d["95000_Setting"]["00001_time"],
        "settings": d["50000_Setting"],
        "platform_extra": {"pc_slot_b64": _b64(pc_schema.encode(tree))},
    }


def gevent_bytes(model):
    return base64.b64decode(model["event"]["gEventGlobal_b64"])

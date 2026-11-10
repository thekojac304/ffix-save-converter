"""Print every occupied slot in the PC fixtures (research helper)."""
import base64, glob, struct, sys
sys.path.insert(0, 'src')
from ffix_conv import pc_container as pc, pc_schema as s
for f in sorted(glob.glob('fixtures/pc/originals/*/*SavedData_ww.dat')):
    c = pc.Container(open(f, 'rb').read())
    print('==', f.split('/')[-1], c.meta)
    for slot, save in c.occupied():
        t = c.slot_tree(slot, save)['Data']; pv = c.preview(slot, save)
        st = t['10000_State']; ev = t['20000_Event']
        g = base64.b64decode(s.string_value(ev['gEventGlobal']))
        sc = struct.unpack_from('<H', g)[0]
        print(f" {slot}/{save} loc={pv.location!r} fld={st['fldMapNo']} wld={st['wldMapNo']} mode={st['mode']} scen={sc} "
              f"gil={t['40000_Common']['gil']} t={t['95000_Setting']['00001_time']:.0f} glen={len(g)} "
              f"party={t['40000_Common']['slot']} lv={[p['level'] for p in t['40000_Common']['players']]}")

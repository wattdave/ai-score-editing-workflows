"""Read a Sibelius-exported vector PDF (OpusStd or HelsinkiStd music font) into per-staff, per-bar note events.

parse(pdf, nstaves_per_system, clefs) returns one dict per staff and system:
  page, sys, part, clef, bars (list of lists of events), edges (barline x positions), staff geometry,
  curves (tie/slur drawings) and words (page text).
An event is a dict: x, p (list of diatonic indices, C0 = 0, so C4 = 28), dur (sixteenths), rest, dot.
Pitches are *written* pitches: the 'G8' clef (treble 8vb tenor) is read as an ordinary treble staff.
CLI (debug dump with the bar sums):  python vecscore.py SCORE.pdf [--staves 4] [--clefs G,G,G8,F]
Only Sibelius PDFs (Opus and Helsinki fonts) have been tested, plus Opus PDFs printed through a Windows driver
(glyph codes shifted by 0xF000, see vecglyph.py); see SKILL.md for the limits."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymupdf
from vecglyph import normalize_glyph, has_music_code, stem_barline_cut, is_music_font
# Opus and Helsinki (Sibelius's two music fonts) use the same legacy glyph codes (verified, see SKILL.md); neither is SMuFL.
H_GLYPH={'œ':'q','˙':'h','w':'w'}           # notehead glyphs (stem drawn separately)
REST={'Ó':8,'Œ':4,'‰':2,'∑':16}   # half, quarter, eighth, whole-bar rest (other rest glyphs are not mapped yet)
STEPS='CDEFGAB'

def staves_of(pg):
    ys=[]
    for dr in pg.get_drawings():
        for it in dr['items']:
            if it[0]=='l' and abs(it[1].y-it[2].y)<0.01 and abs(it[1].x-it[2].x)>100:
                ys.append((round(it[1].y,2),min(it[1].x,it[2].x),max(it[1].x,it[2].x)))
    seen={}
    for y,x0,x1 in ys: seen[y]=(x0,x1)
    yy=sorted(seen)
    groups=[]; cur=[yy[0]]
    for y in yy[1:]:
        if y-cur[-1]<6: cur.append(y)
        else: groups.append(cur); cur=[y]
    groups.append(cur)
    out=[]
    for g in groups:
        if len(g)!=5: continue
        out.append(dict(top=g[0],bottom=g[4],sp=(g[4]-g[0])/4,x0=seen[g[0]][0],x1=seen[g[0]][1]))
    return out

def system_of(pg, st):
    """Per staff: (system index, part index within the system) from the thin vertical line that joins the staves at the
    left edge of a system (for pages whose systems have different numbers of staves)."""
    joins=[(it[1].x,min(it[1].y,it[2].y),max(it[1].y,it[2].y)) for dr in pg.get_drawings() for it in dr['items']
           if it[0]=='l' and abs(it[1].x-it[2].x)<0.01 and abs(it[1].y-it[2].y)>20]
    out=[]; sysi=-1; part=0
    for i,s in enumerate(st):
        prev=st[i-1] if i else None
        linked=prev is not None and any(abs(x-s['x0'])<8 and y0<=prev['top']+1.5 and y1>=s['bottom']-1.5 for x,y0,y1 in joins)
        if linked: part+=1
        else: sysi+=1; part=0
        out.append((sysi,part))
    return out

def parse(pdf, nstaves_per_system=4, clefs=('G','G','G8','F'), split_voices='auto'):
    """nstaves_per_system=0 (CLI --staves auto) finds the systems from the joining line, so systems may differ in size;
    clefs=None finds each staff's clef from its & (treble) or ? (bass) glyph. Otherwise as documented above.
    split_voices='auto' also gives each staff a 'voices' list parallel to 'bars': None for a one-voice bar, or
    [voice1, voice2] (stems up, stems down) for a bar with two voices on the staff (see split_bar_voices); 'off' skips it."""
    d=pymupdf.open(pdf); staves=[]; dbg=[]
    for pi,pg in enumerate(d):
        st=staves_of(pg)
        draws=pg.get_drawings()
        helsinki=any(s['font'].startswith('Helsinki') for b in pg.get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans'])
        vlines=[]; curves=[]; beams=[]
        for dr in draws:
            for it in dr['items']:
                if it[0]=='l' and abs(it[1].x-it[2].x)<0.01:
                    vlines.append((it[1].x,min(it[1].y,it[2].y),max(it[1].y,it[2].y),round(dr.get('width') or 0,2)))
            if dr['type'] in('f','fs') and len(dr['items'])==4 and dr['rect'].width>3 and dr['rect'].height<8: beams.append(dr['rect'])
            elif dr['type']=='f' and len(dr['items'])==1 and dr['items'][0][0]=='re' and dr['rect'].width>3 and 1<dr['rect'].height<3.2: beams.append(dr['rect'])   # flat beam drawn as a rectangle (some drivers); a stem must end on it, so multi-bar rests never match
            if dr['type'] in('fs','f','s') and any(it[0]=='c' for it in dr['items']): curves.append(dr)
        mrests=[dr['rect'] for dr in draws if dr['type']=='f' and dr['rect'].width>30 and dr['rect'].height<8 and len(dr['items'])==1]
        glyphs=[]
        for b in pg.get_text("rawdict")['blocks']:
            for l in b.get('lines',[]):
                for s in l['spans']:
                    if is_music_font(s['font'],''.join(c['c'] for c in s['chars'])):
                        for c in s['chars']:
                            ch=normalize_glyph(c['c'])
                            if ch!=' ': glyphs.append((c['origin'][0],c['origin'][1],ch,s['font']))
        words=[w for w in pg.get_text("words")]
        sysmap=system_of(pg,st) if not nstaves_per_system else None
        for si,s in enumerate(st):
            if nstaves_per_system: sysi=si//nstaves_per_system; part=si%nstaves_per_system
            else: sysi,part=sysmap[si]
            if clefs: clef=clefs[part]
            else:
                cg=[c for x,y,c,f in glyphs if c in '&?' and abs(x-s['x0'])<30 and s['top']-s['sp']<=y<=s['bottom']+s['sp']]
                clef='F' if '?' in cg else 'G'
            top,bot,sp=s['top'],s['bottom'],s['sp']
            hs=sp/2
            # stem/barline width threshold. Helsinki stems are 0.60 wide and barlines 0.75. Opus line widths scale with the
            # staff size (stems 0.09-0.10 sp, barlines 0.155 sp: 0.42/0.66 at sp 4.25, 0.36/0.60 at sp 3.75), so cut at 0.125 sp.
            BARW=stem_barline_cut(sp,helsinki)
            def pitch(y):
                n=round((bot-y)/hs)
                base=(4*7+2) if clef in('G','G8') else (2*7+4)
                return base+n    # diatonic index: C0=0
            # barlines: full-height thin verticals through this staff
            bl=sorted({(round(x,1),round(w,2)) for x,y0,y1,w in vlines if w>BARW and y0<=top+1.5 and y1>=bot-1.5 and y1-y0<sp*4+3 and s['x0']-1<=x<=s['x1']+1})
            bl=[(x,w) for x,w in bl if x>s['x0']+30]       # drop the system-start line
            # a repeat sign or final barline prints a thick and a thin line (and dots) close together: one bar edge, kind noted
            bars=[]; marks={}
            allots=[(x,y) for x,y,c,f in glyphs if c=='™']
            # repeat dots: two dots one staff space apart straddling the middle line (the glyph is also the augmentation dot)
            rdots=[(x,y) for x,y in allots if abs(y-(top+2*sp)+sp/2)<sp*0.3 and any(abs(x2-x)<0.5 and abs(y2-(y+sp))<sp*0.3 for x2,y2 in allots)
                   or abs(y-(top+2*sp)-sp/2)<sp*0.3 and any(abs(x2-x)<0.5 and abs(y2-(y-sp))<sp*0.3 for x2,y2 in allots)]
            rdots=[(dx,dy) for dx,dy in rdots if any(abs(dx-bx)<sp*2.8 for bx,bw in bl)]   # a dotted chord also has two dots: keep only those at a barline
            for x,w in bl:
                if bars and x-bars[-1]<sp*1.5:
                    marks[len(bars)-1]=marks.get(len(bars)-1) or ('thick' if w>1.5 else 'twothin')
                    continue
                bars.append(x)
                if w>1.5: marks[len(bars)-1]='thick'
            for k,x in enumerate(bars):
                cl=[x]+[bl_x for bl_x,w in bl if 0<bl_x-x<sp*1.5]
                right=any(0<dx-max(cl)<sp*2.5 for dx,dy in rdots); left=any(0<min(cl)-dx<sp*2.5 for dx,dy in rdots)
                if right and left: marks[k]='repeat-both'
                elif right: marks[k]='repeat-start'
                elif left: marks[k]='repeat-end'
                elif marks.get(k)=='thick': marks[k]='final'
                elif marks.get(k)=='twothin': marks[k]='double'
            # measure boundaries
            edges=[s['x0']]+bars
            if bars and bars[-1]<s['x1']-3: edges.append(s['x1']+1)
            nbars=len(edges)-1
            # noteheads and rests belonging to this staff (y within staff +- 3sp)
            def band_dist(t, b, y): return max(t - y, y - b, 0)
            def mine(y):
                # within 4.2 spaces of this staff and nearer to it than to any other staff on the page
                d = band_dist(top, bot, y)
                return d <= 4.2*sp and all(d <= band_dist(o['top'], o['bottom'], y) for o in st)
            heads=[(x,y,c) for x,y,c,f in glyphs if c in H_GLYPH and mine(y) and x>s['x0']+15]
            rests=[(x,y,c) for x,y,c,f in glyphs if c in REST and mine(y) and x>s['x0']+15]
            dots=[(x,y) for x,y,c,f in glyphs if c=='™' and mine(y) and (x,y) not in rdots]
            flags=[(x,y,c) for x,y,c,f in glyphs if c in 'jJ' and mine(y)]
            stems=[(x,y0,y1) for x,y0,y1,w in vlines if 0.3<w<=BARW and y1-y0>sp*2 and y1>top-3.2*sp and y0<bot+3.2*sp and s['x0']<x<s['x1']]
            ev=[]; raw=[]
            for x,y,c in heads:
                p=pitch(y)
                base=16 if c=='w' else 8 if c=='˙' else 4
                # stem for this head: a stem line with x near head left/right edge and spanning y
                st_=[(sx,y0,y1) for sx,y0,y1 in stems if (abs(sx-x)<1.3 or abs(sx-(x+sp*1.18))<1.3) and y0-1<=y<=y1+1]
                beam=0; flag=0
                if st_ and c=='œ':
                    sx,y0,y1=st_[0]
                    end_ys=[y0,y1]
                    for r in beams:
                        if r.x0-1.5<=sx<=r.x1+1.5 and (min(abs(r.y0-e) for e in end_ys)<3.5 or min(abs(r.y1-e) for e in end_ys)<3.5): beam+=1
                    for fx,fy,fc in flags:
                        if abs(fx-sx)<3 and (min(abs(fy-e) for e in end_ys)<6): flag+=1
                dur=base
                if c=='œ':
                    lv=beam+flag
                    if lv==1: dur=2
                    elif lv>=2: dur=1
                dot=any(0<dx-x<sp*2.6 and abs(dy-y)<sp*0.9 for dx,dy in dots)
                ev.append(dict(x=x,p=[p],dur=dur*3//2 if dot else dur,y=y,beam=beam,flag=flag,stem=bool(st_),dot=dot,rest=False))
                raw.append(dict(x=x,y=y,c=c,p=p,dot=dot))
            for x,y,c in rests:
                rdot=any(0<dx-x<sp*2.4 and abs(dy-y)<sp*1.6 for dx,dy in dots)
                ev.append(dict(x=x,p=[],dur=REST[c]*3//2 if rdot else REST[c],rest=True,y=y,dot=rdot))
            ev.sort(key=lambda e:e['x'])
            # merge chords: same x
            merged=[]
            for e in ev:
                if merged and not e['rest'] and not merged[-1]['rest'] and abs(e['x']-merged[-1]['x'])<1.0:
                    merged[-1]['p']=sorted(set(merged[-1]['p']+e['p']))
                else: merged.append(e)
            # accidentals printed in the bar: '#', 'b', 'n' glyph left of a notehead at about the same height; they hold
            # for the same pitch for the rest of the bar. e['alt'] = {pitch index: -1|0|1} for pitches that carry one.
            accs=[(x,y,{'#':1,'b':-1,'n':0}[c]) for x,y,c,f in glyphs if c in '#bn' and mine(y) and x>s['x0']+15]
            for e in merged:
                e['alt']={}
                if e['rest']: continue
                for (ax,ay,av) in accs:
                    if 0<e['x']-ax<18:
                        for pp in e['p']:
                            if abs(pitch(ay)-pp)<=0 : e['alt'][pp]=av
            held={}; lastbar=None
            for e in merged:
                bi=next((i for i in range(nbars) if edges[i]<=e['x']<edges[i+1]),None)
                if bi!=lastbar: held={}; lastbar=bi
                if e['rest']: continue
                for pp in e['p']:
                    if pp in e['alt']: held[pp]=e['alt'][pp]
                    elif pp in held: e['alt'][pp]=held[pp]
            # distribute to bars
            bar_ev=[[] for _ in range(nbars)]
            for e in merged:
                for bi in range(nbars):
                    if edges[bi]<=e['x']<edges[bi+1]: bar_ev[bi].append(e); break
            # multi-bar rest: a thick horizontal bar inside an otherwise empty bar, with the bar count printed above it
            for bi in range(nbars):
                if bar_ev[bi]: continue
                for r in mrests:
                    if edges[bi]-1<=r.x0 and r.x1<=edges[bi+1]+1 and top<r.y0 and r.y1<bot and r.height<sp:
                        num=''.join(c for x,y,c,f in sorted(glyphs) if c.isdigit() and r.x0<=x<=r.x1 and y<top)
                        bar_ev[bi].append(dict(x=r.x0,p=[],dur=0,rest=True,multirest=int(num) if num else 1,dot=False,y=r.y0))
            while bar_ev and not bar_ev[-1]: bar_ev.pop(); nbars-=1
            st_d=dict(page=pi,sys=sysi,part=part,clef=clef,bars=bar_ev,edges=edges,marks=marks,staff=s,curves=curves,words=words)
            if split_voices!='off':
                st_d['voices']=[split_bar_voices([h for h in raw if edges[bi]<=h['x']<edges[bi+1]],[e for e in bar_ev[bi] if e['rest']],
                                                 bar_ev[bi],stems,beams,flags,dots,s) for bi in range(nbars)]
            staves.append(st_d)
    return staves

def split_bar_voices(heads, rests, merged, stems, beams, flags, dots, staff):
    """Two voices on one staff: return [voice1, voice2] (events as in parse, in x order) or None for a one-voice bar.
    A bar has two voices when a stem-up and a stem-down note sound together (x within 1.5 spaces), or a rest sits a
    space or more off its usual height (voice 1 rests are raised, voice 2 rests lowered). Each stem is one event:
    its heads are a chord, its direction is the side it extends to, its beams and flags give the duration. Stem-up
    events go to voice 1 and stem-down to voice 2; a notehead on both an up and a down stem (unison) is in both.
    Stemless heads (whole notes) join the voice they are above or below at the same x, or both voices when alone."""
    sp=staff['sp']; mid=staff['top']+2*sp
    if not heads and not rests: return None
    sinfo=[]   # (stem x, y0, y1, [head idx])
    for sx,y0,y1 in stems:
        hs_=[i for i,h in enumerate(heads) if h['c']!='w' and (abs(sx-h['x'])<1.3 or abs(sx-(h['x']+sp*1.18))<1.3) and y0-1<=h['y']<=y1+1]
        if hs_: sinfo.append((sx,y0,y1,hs_))
    sev=[]
    for sx,y0,y1,hs_ in sinfo:
        hy=[heads[i]['y'] for i in hs_]
        up=(min(hy)-y0)>(y1-max(hy))
        tip=y0 if up else y1
        lo,hi=(tip-1.5,tip+sp*1.6) if up else (tip-sp*1.6,tip+1.5)   # beams stack from the tip towards the heads
        beam=sum(1 for r in beams if r.x0-1.5<=sx<=r.x1+1.5 and r.y1>lo and r.y0<hi)
        flag=sum(1 for fx,fy,fc in flags if abs(fx-sx)<3 and abs(fy-tip)<6)
        c=heads[hs_[0]]['c']; base=8 if c=='˙' else 4
        if c=='œ': base=2 if beam+flag==1 else 1 if beam+flag>=2 else 4
        dot=any(heads[i]['dot'] for i in hs_)
        sev.append(dict(x=min(heads[i]['x'] for i in hs_),p=sorted({heads[i]['p'] for i in hs_}),dur=base*3//2 if dot else base,
                        rest=False,dot=dot,up=up,hidx=hs_,beam=beam,flag=flag,stem=True))
    ups=[e for e in sev if e['up']]; downs=[e for e in sev if not e['up']]
    together=any(abs(a['x']-b['x'])<sp*1.5 for a in ups for b in downs)
    # a whole note (no stem) at the x of a stemmed note sounds with it but cannot share its voice
    wholes=[h for h in heads if h['c']=='w']
    together=together or any(abs(o['x']-h['x'])<sp*1.5 for h in wholes for o in sev)
    offrest=any(abs(r['y']-mid)>=sp*0.5 for r in rests if not r.get('multirest'))
    if not together and not offrest: return None
    if not together and not any(abs(r['y']-mid)>=sp*0.5 and not r.get('multirest') for r in rests if (r['y']<mid)==(not ups)):
        return None   # a displaced rest only on the side of the notes' own voice: leave the bar as read
    v1=list(ups); v2=list(downs)
    stemmed={i for e in sev for i in e['hidx']}
    for i,h in enumerate(heads):
        if i in stemmed: continue
        base=16 if h['c']=='w' else 8 if h['c']=='˙' else 4
        e=dict(x=h['x'],p=[h['p']],dur=base*3//2 if h['dot'] else base,rest=False,dot=h['dot'],stem=False)
        other=[o for o in sev if abs(o['x']-h['x'])<sp*1.5]
        if other and h['c']=='w' and len({o['up'] for o in other})==1: (v2 if other[0]['up'] else v1).append(e)   # opposite the stems
        elif other and h['p']>max(max(o['p']) for o in other): v1.append(e)
        elif other and h['p']<min(min(o['p']) for o in other): v2.append(e)
        else: v1.append(e); v2.append(dict(e))
    for r in rests:
        if r.get('multirest'): v1.append(r); v2.append(dict(r)); continue
        off=(r['y']-mid)/sp
        if off<=-0.5: v1.append(r)
        elif off>=0.5: v2.append(r)
        else:   # at the usual height: the voice with nothing at this x
            if any(abs(e['x']-r['x'])<sp*1.5 for e in v1): v2.append(r)
            else: v1.append(r)
    for vv in (v1,v2):
        vv.sort(key=lambda e:e['x'])
        for e in vv:
            if e['rest']: continue
            e['alt']={}
            for m in merged:
                if not m['rest'] and abs(m['x']-e['x'])<sp*1.5:
                    for pp in e['p']:
                        if pp in m.get('alt',{}): e['alt'][pp]=m['alt'][pp]
            for k in ('hidx','up'): e.pop(k,None)
    if [(e['dur'],e['rest']) for e in v1]==[(e['dur'],e['rest']) for e in v2]:
        # same rhythm in both voices: one voice of chords, as merged, but with the durations read from each stem
        one=[dict(a,p=sorted(set(a['p'])|set(b['p'])),alt={**b.get('alt',{}),**a.get('alt',{})}) if not a['rest'] else a for a,b in zip(v1,v2)]
        if [(e['dur'],e['rest']) for e in one]==[(e['dur'],e['rest']) for e in merged]: return None
        return [one]
    return [v1,v2]

def midi_name(p):  # diatonic index -> name+octave
    return f"{STEPS[p%7]}{p//7}"

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('pdf'); ap.add_argument('--staves',default='4',help='staves per system, or auto (systems found from the joining line; may differ in size)')
    ap.add_argument('--clefs',default='G,G,G8,F',help='clef per staff within a system: G, G8 (treble 8vb) or F; auto reads each clef from its glyph (never finds G8)')
    ap.add_argument('--split-voices',default='auto',choices=('auto','off'),help='auto: read two voices on one staff (stems up = voice 1, down = voice 2)')
    a=ap.parse_args()
    sts=parse(a.pdf,0 if a.staves=='auto' else int(a.staves),None if a.clefs=='auto' else tuple(a.clefs.split(',')),a.split_voices)
    def evs(b): return ' '.join(('r' if e['rest'] else '/'.join(midi_name(p) for p in e['p']))+(f":{e['dur']}" if not e.get('multirest') else f"x{e['multirest']}bars") for e in b)
    for s in sts:
        print(f"page {s['page']} sys {s['sys']} part {s['part']} ({s['clef']}) bars {len(s['bars'])}")
        for bi,b in enumerate(s['bars']):
            tot=sum(e['dur'] for e in b)
            mk=s['marks'].get(bi-1) if bi else None; mk2=s['marks'].get(bi)
            note=('|: ' if mk in ('repeat-start','repeat-both') else '')+('[ends '+mk2+']' if mk2 else '')
            vv=(s.get('voices') or [None]*len(s['bars']))[bi]
            if vv: print('  bar',bi,'sum','+'.join(str(sum(e['dur'] for e in x)) for x in vv),note.strip(),' | '.join(f"v{i+1}: "+evs(x) for i,x in enumerate(vv)))
            else: print('  bar',bi,'sum',tot,note.strip(),evs(b))

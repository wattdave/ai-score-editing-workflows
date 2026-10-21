"""Read a Sibelius-exported vector PDF (OpusStd music font) into per-staff, per-bar note events.

parse(pdf, nstaves_per_system, clefs) returns one dict per staff and system:
  page, sys, part, clef, bars (list of lists of events), edges (barline x positions), staff geometry,
  curves (tie/slur drawings) and words (page text).
An event is a dict: x, p (list of diatonic indices, C0 = 0, so C4 = 28), dur (sixteenths), rest, dot.
Pitches are *written* pitches: the 'G8' clef (treble 8vb tenor) is read as an ordinary treble staff.
CLI (debug dump with the bar sums):  python vecscore.py SCORE.pdf [--staves 4] [--clefs G,G,G8,F]
Only Sibelius PDFs (Opus font) have been tested; see SKILL.md for the limits."""
import sys
import pymupdf
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

def parse(pdf, nstaves_per_system=4, clefs=('G','G','G8','F')):
    d=pymupdf.open(pdf); staves=[]; dbg=[]
    for pi,pg in enumerate(d):
        st=staves_of(pg)
        draws=pg.get_drawings()
        vlines=[]; curves=[]; beams=[]
        for dr in draws:
            for it in dr['items']:
                if it[0]=='l' and abs(it[1].x-it[2].x)<0.01:
                    vlines.append((it[1].x,min(it[1].y,it[2].y),max(it[1].y,it[2].y),round(dr.get('width') or 0,2)))
            if dr['type'] in('f','fs') and len(dr['items'])==4 and dr['rect'].width>3 and dr['rect'].height<8: beams.append(dr['rect'])
            if dr['type'] in('fs','f','s') and any(it[0]=='c' for it in dr['items']): curves.append(dr)
        glyphs=[]
        for b in pg.get_text("rawdict")['blocks']:
            for l in b.get('lines',[]):
                for s in l['spans']:
                    if s['font'].startswith('Opus'):
                        for c in s['chars']:
                            if c['c']!=' ': glyphs.append((c['origin'][0],c['origin'][1],c['c'],s['font']))
        words=[w for w in pg.get_text("words")]
        for si,s in enumerate(st):
            sysi=si//nstaves_per_system; part=si%nstaves_per_system
            clef=clefs[part]
            top,bot,sp=s['top'],s['bottom'],s['sp']
            hs=sp/2
            def pitch(y):
                n=round((bot-y)/hs)
                base=(4*7+2) if clef in('G','G8') else (2*7+4)
                return base+n    # diatonic index: C0=0
            # barlines: full-height thin verticals through this staff
            bars=sorted({round(x,1) for x,y0,y1,w in vlines if w>0.6 and y0<=top+1.5 and y1>=bot-1.5 and y1-y0<sp*4+3 and s['x0']-1<=x<=s['x1']+1})
            bars=[b for b in bars if b>s['x0']+30]       # drop the system-start line
            # measure boundaries
            edges=[s['x0']]+bars
            if bars and bars[-1]<s['x1']-3: edges.append(s['x1']+1)
            nbars=len(edges)-1
            # noteheads and rests belonging to this staff (y within staff +- 3sp)
            def mine(y): return top-3.2*sp<=y<=bot+3.2*sp
            heads=[(x,y,c) for x,y,c,f in glyphs if c in H_GLYPH and mine(y) and x>s['x0']+25]
            rests=[(x,y,c) for x,y,c,f in glyphs if c in REST and mine(y) and x>s['x0']+25]
            dots=[(x,y) for x,y,c,f in glyphs if c=='™' and mine(y)]
            flags=[(x,y,c) for x,y,c,f in glyphs if c in 'jJ' and mine(y)]
            stems=[(x,y0,y1) for x,y0,y1,w in vlines if 0.3<w<0.6 and y1-y0>sp*2 and y1>top-3.2*sp and y0<bot+3.2*sp and s['x0']<x<s['x1']]
            ev=[]
            for x,y,c in heads:
                p=pitch(y)
                base=8 if c=='˙' else 4
                # stem for this head: a stem line with x near head left/right edge and spanning y
                st_=[(sx,y0,y1) for sx,y0,y1 in stems if (abs(sx-x)<1.3 or abs(sx-(x+sp*1.18))<1.3) and y0-1<=y<=y1+1]
                beam=0; flag=0
                if st_ and c!='˙':
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
            # distribute to bars
            bar_ev=[[] for _ in range(nbars)]
            for e in merged:
                for bi in range(nbars):
                    if edges[bi]<=e['x']<edges[bi+1]: bar_ev[bi].append(e); break
            while bar_ev and not bar_ev[-1]: bar_ev.pop(); nbars-=1
            staves.append(dict(page=pi,sys=sysi,part=part,clef=clef,bars=bar_ev,edges=edges,staff=s,curves=curves,words=words))
    return staves

def midi_name(p):  # diatonic index -> name+octave
    return f"{STEPS[p%7]}{p//7}"

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(); ap.add_argument('pdf'); ap.add_argument('--staves',type=int,default=4,help='staves per system')
    ap.add_argument('--clefs',default='G,G,G8,F',help='clef per staff within a system: G, G8 (treble 8vb) or F')
    a=ap.parse_args()
    sts=parse(a.pdf,a.staves,tuple(a.clefs.split(',')))
    for s in sts:
        print(f"page {s['page']} sys {s['sys']} part {s['part']} ({s['clef']}) bars {len(s['bars'])}")
        for bi,b in enumerate(s['bars']):
            tot=sum(e['dur'] for e in b)
            print('  bar',bi,'sum',tot,' '.join(('r' if e['rest'] else '/'.join(midi_name(p) for p in e['p']))+f":{e['dur']}" for e in b))

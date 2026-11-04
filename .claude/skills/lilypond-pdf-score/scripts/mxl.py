import os, sys, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from build import collect
from xml.sax.saxutils import escape
DIV=4  # per quarter
BAR=16
NAMES=["Cantus","Contra","Tenor","Bassus"]
FIFTHS=-2
FLAT_ORDER=[6,2,5,1,4,0,3]   # B E A D G C F as indexes into LETTER
SHARP_ORDER=[3,0,4,1,5,2,6]
LETTER="CDEFGAB"
TYPES=[(16,'whole',0),(12,'half',1),(8,'half',0),(6,'quarter',1),(4,'quarter',0),(3,'eighth',1),(2,'eighth',0),(1,'16th',0)]

def normalise(v):
    """sorted events -> list of (onset16,dur16,ev) covering [0,end) with rests; trims overlapping rests"""
    v=sorted(v,key=lambda e:(e["onset"],e.get("rest",False)))
    out=[]; t=0
    for e in v:
        on=round(e["onset"]*DIV); du=round(e["dur"]*DIV)
        if out and out[-1][2].get("rest") and on<out[-1][0]+out[-1][1]:
            o,d,x=out[-1]; out[-1]=(o,on-o,x) if on>o else None
            if out[-1] is None: out.pop()
            t=out[-1][0]+out[-1][1] if out else 0
        if on<t:
            if e.get("rest"):
                du-= (t-on); on=t
                if du<=0: continue
            else:
                raise SystemExit(f"note overlap at {on/DIV} voice {e['voice']}")
        if on>t: out.append((t,on-t,{"rest":True}))
        out.append((on,du,e)); t=on+du
    return out

def merge_rests(L):
    M=[]
    for o,d,e in L:
        if M and e.get("rest") and M[-1][2].get("rest") and M[-1][0]+M[-1][1]==o: M[-1]=(M[-1][0],M[-1][1]+d,M[-1][2])
        else: M.append((o,d,e))
    return M

def pieces(d):
    out=[]
    while d>0:
        for n,_,_ in TYPES:
            if n<=d: out.append(n); d-=n; break
    return out
def tinfo(n): return [t for t in TYPES if t[0]==n][0]

def build(pdf,out,title,composer,fifths=-2):
    global KEY
    KEY={i:-1 for i in FLAT_ORDER[:-fifths]} if fifths<0 else {i:1 for i in SHARP_ORDER[:fifths]}
    voices,starts,systems=collect(pdf)
    total=max(round((v_["onset"]+v_["dur"])*DIV) for v in voices for v_ in v)
    nbars=(total+BAR-1)//BAR
    X=['<?xml version="1.0" encoding="UTF-8"?>','<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">','<score-partwise version="3.1">',f'<work><work-title>{escape(title)}</work-title></work>',f'<identification><creator type="composer">{escape(composer)}</creator></identification>','<part-list>']
    for i,n in enumerate(NAMES): X.append(f'<score-part id="P{i+1}"><part-name>{n}</part-name></score-part>')
    X.append('</part-list>')
    report=[]
    for vi,v in enumerate(voices):
        L=merge_rests(normalise(v))
        if L[-1][0]+L[-1][1]<nbars*BAR: L.append((L[-1][0]+L[-1][1],nbars*BAR-L[-1][0]-L[-1][1],{"rest":True}))
        # split at barlines
        segs=[]
        for o,d,e in L:
            while d>0:
                room=BAR-(o%BAR); take=min(room,d)
                segs.append((o,take,e,o>e.get("_o",o) if False else None)); o+=take; d-=take
        X.append(f'<part id="P{vi+1}">')
        bars={}
        for o,d,e,_ in segs: bars.setdefault(o//BAR,[]).append((o,d,e))
        # tie info: a note event split into several segs -> ties
        count={}
        for o,d,e,_ in segs: count[id(e)]=count.get(id(e),0)+1
        seen={}
        state={}
        for b in range(nbars):
            X.append(f'<measure number="{b+1}">')
            if b==0:
                X.append(f'<attributes><divisions>{DIV}</divisions><key><fifths>{fifths}</fifths></key><time symbol="cut"><beats>2</beats><beat-type>2</beat-type></time>')
                if vi==0: X.append('<clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>')
                else: X.append('<clef><sign>F</sign><line>4</line></clef>')
                X.append('</attributes>')
            state={}
            for o,d,e in bars.get(b,[]):
                parts=pieces(d)
                for pi,pn in enumerate(parts):
                    typ,dot=tinfo(pn)[1],tinfo(pn)[2]
                    if e.get("rest"):
                        if d==BAR and len(parts)==1: X.append(f'<note><rest measure="yes"/><duration>{pn}</duration></note>')
                        else: X.append(f'<note><rest/><duration>{pn}</duration><voice>1</voice><type>{typ}</type>'+'<dot/>'*dot+'</note>')
                        continue
                    n=e["step"]; letter=LETTER[n%7]; octv=n//7
                    key=KEY.get(n%7,0)
                    if e.get("alt") is not None:
                        alt=e["alt"]
                        if e.get("acc"): state[n]=alt
                    else: alt=state.get(n,key)
                    if vi==0: octv-=1
                    k=seen.get(id(e),0); seen[id(e)]=k+1
                    tot=count[id(e)]*0+sum(len(pieces(dd)) for oo,dd,ee,_ in segs if ee is e)
                    idx=k; 
                    # global piece index across segments
                    tie_prev= idx>0; tie_next= idx<tot-1
                    nx=f'<note><pitch><step>{letter}</step>'+(f'<alter>{alt}</alter>' if alt else '')+f'<octave>{octv}</octave></pitch><duration>{pn}</duration>'
                    if tie_prev: nx+='<tie type="stop"/>'
                    if tie_next: nx+='<tie type="start"/>'
                    nx+=f'<voice>1</voice><type>{typ}</type>'+'<dot/>'*dot
                    if alt==0 and (e.get("ficta") or key!=0) or alt!=0 and (e.get("acc") or e.get("ficta")):
                        if not tie_prev: nx+='<accidental>'+('natural' if alt==0 else 'flat' if alt==-1 else 'sharp')+'</accidental>'
                    if tie_prev or tie_next:
                        nx+='<notations>'+('<tied type="stop"/>' if tie_prev else '')+('<tied type="start"/>' if tie_next else '')+'</notations>'
                    if e.get("lyric") and not tie_prev:
                        tx,sy=e["lyric"]
                        nx+=f'<lyric number="1"><syllabic>{sy}</syllabic><text>{escape(tx)}</text></lyric>'
                    nx+='</note>'
                    X.append(nx)
            X.append('</measure>')
        X.append('</part>')
    X.append('</score-partwise>')
    open(out,'w').write("\n".join(X))
    print("wrote",out,"bars",nbars)

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description="Glyph-read a LilyPond PDF into MusicXML")
    ap.add_argument("pdf"); ap.add_argument("out")
    ap.add_argument("--title",default="Untitled"); ap.add_argument("--composer",default="")
    ap.add_argument("--names",default=",".join(NAMES),help="four part names, comma separated, top staff first")
    ap.add_argument("--fifths",type=int,default=-2,help="key signature: negative flats, positive sharps")
    a=ap.parse_args()
    NAMES[:]=a.names.split(",")
    build(a.pdf,a.out,a.title,a.composer,a.fifths)

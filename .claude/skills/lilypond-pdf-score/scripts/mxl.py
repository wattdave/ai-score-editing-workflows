import os, sys, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from build import *
from xml.sax.saxutils import escape
DIV=12  # per quarter (12 so that triplets are whole numbers)
BAR=48
NAMES=["Cantus","Contra","Tenor","Bassus"]
FIFTHS=-2
FLAT_ORDER=[6,2,5,1,4,0,3]   # B E A D G C F as indexes into LETTER
SHARP_ORDER=[3,0,4,1,5,2,6]
LETTER="CDEFGAB"
TYPES=[(48,'whole',0),(36,'half',1),(24,'half',0),(18,'quarter',1),(12,'quarter',0),(9,'eighth',1),(6,'eighth',0),(3,'16th',0)]

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
                raise SystemExit(f"notes overlap at beat {on/DIV} in voice {e['voice']+1}: two voices share a staff or there is a chord. "
                                 "This reader needs one voice per staff (see SKILL.md).")
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

def build(pdf,out,title,composer,names=None,nvoices=4,pages=None,clefs=None,fifths=None,time=None,pickup=True):
    global KEY, BAR
    D=Doc(pdf)
    res=extract(D,nvoices,pages)
    clefs=clefs or detect_clefs(D,res)
    fifths=detect_key(D,res) if fifths is None else fifths
    beats,beattype,symbol=time if time else detect_time(D,res)
    bar_beats=beats*4/beattype            # quarter notes per bar
    BAR=int(round(bar_beats*DIV))
    names=names or [f"Voice {i+1}" for i in range(nvoices)]
    KEY={i:-1 for i in FLAT_ORDER[:-fifths]} if fifths<0 else {i:1 for i in SHARP_ORDER[:fifths]}
    voices,starts,systems=collect(D,res,nvoices,clefs,bar_beats,fifths)
    # pickup: the first barline falls this many beats after the start
    pickup_beats=0.0
    if pickup:
        first=[b for b in systems[0][1]["bars"][1:2]]
        if first:
            ons=timeline(systems[0][0],systems[0][1])
            L=ons[systems[0][1]["staves"][0]][0]
            t=[tt for e,tt in L if e["x"]>first[0]]
            if t and t[0]%bar_beats>1e-6: pickup_beats=t[0]%bar_beats
    shift=int(round((bar_beats-pickup_beats)%bar_beats*DIV))
    sigs=time_changes(D,res,*([x for x in system_starts(res,bar_beats)])) if not time else []
    sigs=[(int(round(t*DIV))+shift,b,d,sym) for t,b,d,sym in sigs]
    for v in voices:
        for e in v: e["onset"]+=shift/DIV
    total=max(round((v_["onset"]+v_["dur"])*DIV) for v in voices for v_ in v)
    # bar edges in divisions, following the time-signature changes
    sigs=[x for x in sigs if x[0]>0]
    edges=[0]; cur=(beats,beattype,symbol); si_=0; changes={0:cur}
    while edges[-1]<total:
        if si_<len(sigs) and sigs[si_][0]<=edges[-1]:
            cur=sigs[si_][1:]; changes[len(edges)-1]=cur; si_+=1
        blen=int(round(cur[0]*4/cur[1]*DIV))
        nxt=edges[-1]+blen
        if si_<len(sigs) and edges[-1]<sigs[si_][0]<nxt: nxt=sigs[si_][0]   # the change falls inside a bar: cut it short
        edges.append(nxt)
    nbars=len(edges)-1
    import bisect
    def bar_of(o): return bisect.bisect_right(edges,o)-1
    X=['<?xml version="1.0" encoding="UTF-8"?>','<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">','<score-partwise version="3.1">',f'<work><work-title>{escape(title)}</work-title></work>',f'<identification><creator type="composer">{escape(composer)}</creator></identification>','<part-list>']
    for i,n in enumerate(names): X.append(f'<score-part id="P{i+1}"><part-name>{n}</part-name></score-part>')
    X.append('</part-list>')
    report=[]
    for vi,v in enumerate(voices):
        L=merge_rests(normalise(v))
        if L[-1][0]+L[-1][1]<edges[-1]: L.append((L[-1][0]+L[-1][1],edges[-1]-L[-1][0]-L[-1][1],{"rest":True}))
        # split at barlines
        segs=[]
        for o,d,e in L:
            while d>0:
                room=edges[bar_of(o)+1]-o; take=min(room,d)
                segs.append((o,take,e,o>e.get("_o",o) if False else None)); o+=take; d-=take
        X.append(f'<part id="P{vi+1}">')
        bars={}
        for o,d,e,_ in segs: bars.setdefault(bar_of(o),[]).append((o,d,e))
        if shift:   # drop the padding that makes the pickup a full bar
            fixed=[]
            for o,d,e in bars.get(0,[]):
                if o+d<=shift: continue
                if o<shift: o,d=shift,d-(shift-o)
                fixed.append((o,d,e))
            bars[0]=fixed
        # tie info: a note event split into several segs -> ties
        count={}
        for o,d,e,_ in segs: count[id(e)]=count.get(id(e),0)+1
        seen={}
        state={}
        for b in range(nbars):
            X.append(f'<measure number="{b if shift else b+1}"'+(' implicit="yes"' if (b==0 and shift) else '')+'>')
            if b in changes:
                bb,bt,sy=changes[b]
                tsym=f' symbol="{sy}"' if sy else ''
                if b==0:
                    X.append(f'<attributes><divisions>{DIV}</divisions><key><fifths>{fifths}</fifths></key><time{tsym}><beats>{bb}</beats><beat-type>{bt}</beat-type></time>')
                    sign={"G":("G",2),"F":("F",4),"C":("C",3)}[clefs[vi][0]]
                    oc='<clef-octave-change>-1</clef-octave-change>' if clefs[vi].endswith("8") else ''
                    X.append(f'<clef><sign>{sign[0]}</sign><line>{sign[1]}</line>{oc}</clef>')
                else:
                    X.append(f'<attributes><time{tsym}><beats>{bb}</beats><beat-type>{bt}</beat-type></time>')
                X.append('</attributes>')
            state={}
            for o,d,e in bars.get(b,[]):
                parts=[d] if e.get('tup') else pieces(d)
                for pi,pn in enumerate(parts):
                    typ,dot=tinfo(round(pn*1.5) if e.get('tup') else pn)[1:]
                    tm='<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>' if e.get('tup') else ''
                    if e.get("rest"):
                        if d==edges[b+1]-edges[b] and len(parts)==1: X.append(f'<note><rest measure="yes"/><duration>{pn}</duration></note>')
                        else: X.append(f'<note><rest/><duration>{pn}</duration><voice>1</voice><type>{typ}</type>'+'<dot/>'*dot+tm+'</note>')
                        continue
                    n=e["step"]; letter=LETTER[n%7]; octv=n//7
                    key=KEY.get(n%7,0)
                    if e.get("alt") is not None:
                        alt=e["alt"]
                        if e.get("acc"): state[n]=alt
                    else: alt=state.get(n,key)
                    k=seen.get(id(e),0); seen[id(e)]=k+1
                    tot=count[id(e)]*0+sum(1 if ee.get('tup') else len(pieces(dd)) for oo,dd,ee,_ in segs if ee is e)
                    idx=k; 
                    # global piece index across segments
                    tie_prev= idx>0; tie_next= idx<tot-1
                    nx=f'<note><pitch><step>{letter}</step>'+(f'<alter>{alt}</alter>' if alt else '')+f'<octave>{octv}</octave></pitch><duration>{pn}</duration>'
                    if tie_prev: nx+='<tie type="stop"/>'
                    if tie_next: nx+='<tie type="start"/>'
                    nx+=f'<voice>1</voice><type>{typ}</type>'+'<dot/>'*dot
                    if alt==0 and (e.get("ficta") or key!=0) or alt!=0 and (e.get("acc") or e.get("ficta")):
                        if not tie_prev: nx+='<accidental>'+('natural' if alt==0 else 'flat' if alt==-1 else 'sharp')+'</accidental>'
                    nx+=tm
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
    ap.add_argument("--names",help="part names, comma separated, top staff first")
    ap.add_argument("--voices",type=int,default=4,help="staves per system (one voice each)")
    ap.add_argument("--pages",help="vocal pages to read, 1-based, comma separated (default all)")
    ap.add_argument("--clefs",help="per voice, e.g. G,G,G8,F (G8 = treble down an octave); default read from the print")
    ap.add_argument("--fifths",type=int,help="key signature: negative flats, positive sharps; default read from the print")
    ap.add_argument("--time",help="e.g. 4/4, 2/2, 3/2; default read from the print")
    ap.add_argument("--no-pickup",action="store_true",help="do not look for an anacrusis")
    ap.add_argument("--scrambled",action="store_true",help="lyric text layer is a cipher (re-saved PDF): decode with lyr.SH")
    a=ap.parse_args()
    import lyr; lyr.SCRAMBLED=a.scrambled
    tm=None
    if a.time:
        n,d=a.time.split("/"); tm=(int(n),int(d),"cut" if a.time=="2/2" else None)
    build(a.pdf,a.out,a.title,a.composer,a.names.split(",") if a.names else None,a.voices,
          [int(x)-1 for x in a.pages.split(",")] if a.pages else None,
          a.clefs.split(",") if a.clefs else None,a.fifths,tm,not a.no_pickup)

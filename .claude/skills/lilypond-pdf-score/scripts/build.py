import os, sys, statistics, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from onset2 import *
from collections import Counter
import pymupdf
from reader import Page
from lyr import page_lyrics

LET="CDEFGAB"
def load(pdf):
    doc=pymupdf.open(pdf); res=extract(pdf)
    pages=[Page(doc,pn) for pn in range(len(doc))]
    return doc,res,pages

def system_starts(res):
    S=[]; cur=0.0; systems=[]
    for pg in res:
        for s in pg["systems"]:
            systems.append((pg,s))
    starts=[]; 
    for n,(pg,s) in enumerate(systems):
        ons=timeline(pg,s)
        # residue of barline times
        cands=[]
        for b in s["bars"][1:-1] if n>0 else s["bars"][2:-1]:
            c=[]
            for st,(L,t) in ons.items():
                prev=[(e,tt) for e,tt in L if e["x"]<b]; nxt=[(e,tt) for e,tt in L if e["x"]>b]
                if prev and nxt:
                    pe,pt=prev[-1]; ne,nt=nxt[0]
                    if abs(pt+dur(pe)-nt)<1e-6: c.append(round(nt%4,2))
            cands+= c
        res_mode=Counter(cands).most_common(1)[0][0] if cands else 0.0
        if n==0: S0=0.0
        else:
            ppg,ps=systems[n-1]; pons=timeline(ppg,ps)
            tot=statistics.median([t for _,t in pons.values()])
            base=starts[-1]+tot
            want=(-res_mode)%4
            # nearest value to base with value%4==want
            k=round((base-want)/4); S0=want+4*k
        starts.append(S0)
    return systems,starts

def pitch_of(staff_in_sys,hs):
    if staff_in_sys==0: n=28+2+hs     # E4 = 30
    else: n=14+4+hs                   # G2 = 18 (C2=14)
    return n

def collect(pdf):
    doc,res,pages=load(pdf)
    systems,starts=system_starts(res)
    voices=[[] for _ in range(4)]
    ptoks={pn:page_lyrics(doc,pn) for pn in range(len(pages))}
    unplaced=[]
    for n,((pg,s),S) in enumerate(zip(systems,starts)):
        pgobj=pages[pg["pn"]]
        ons=timeline(pg,s)
        # ficta glyphs (small) on this page
        small=[g for g in pgobj.glyphs if g["size"]<15 and g["gid"] in (1,2)]  # gid 0 is an editorial bracket, not a sharp
        flats=[g for g in pgobj.glyphs if g["gid"]==7 and g["x"]>85]
        for vi,st in enumerate(s["staves"]):
            L,_=ons[st]
            for e,t in L:
                ev=dict(onset=S+t,dur=dur(e),x=e["x"],page=pg["pn"],sys=n,voice=vi)
                if e["t"]=="R": ev["rest"]=True
                else:
                    n_=pitch_of(vi,e["hs"]); alt=None
                    for g in small:
                        if pgobj.staff_of(g["y"])==st and -3.2<=e["x"]-g["x"]<=-0.5 or False: pass
                    for g in small:
                        if pgobj.staff_of(g["y"])==st and 0<=g["x"]-e["x"]<=3.2:
                            alt={1:0,2:-1}[g["gid"]]; ev["ficta"]=True
                    if alt is None:
                        for g in flats:
                            if pgobj.staff_of(g["y"])==st and 2<=e["x"]-g["x"]<=14 and abs(pgobj.hs(st,g["y"])-e["hs"])<0.6:
                                alt=-1; ev["acc"]=True
                    ev["step"]=n_; ev["alt"]=alt
                voices[vi].append(ev)
                ev["_e"]=e
            # lyrics for this voice in this system
            sb=pgobj.staves[st]["bot"]; 
            nxt=pgobj.staves[st+1]["top"] if st+1<len(pgobj.staves) else sb+60
            row=[t for t in ptoks[pg["pn"]] if sb<t["y"]-5<nxt and t["x0"]>=pgobj.staves[st]["x0"]]
            row.sort(key=lambda t:t["x0"])
            notes=[ev for ev in voices[vi] if ev["sys"]==n and not ev.get("rest")]
            sy=[t for t in row if t["text"]!="-"]
            last=-1
            for ti,t in enumerate(sy):
                xc=(t["x0"]+t["x1"])/2
                best=None
                for k,ev in enumerate(notes):
                    if k<=last: continue
                    dxx=abs(xc-(ev["x"]+2.6))
                    if best is None or dxx<best[0]: best=(dxx,k)
                if best is None or best[0]>14: unplaced.append((pg["pn"],n,vi,t["text"],round(xc,1))); continue
                last=best[1]
                # hyphen after / before
                after=[h for h in row if h["text"]=="-" and t["x1"]-1<=h["x0"]<= (sy[ti+1]["x0"] if ti+1<len(sy) else 1e9)]
                before=[h for h in row if h["text"]=="-" and (sy[ti-1]["x1"] if ti>0 else -1e9)-1<=h["x0"]<=t["x0"]+1]
                syl="middle" if (after and before) else "begin" if after else "end" if before else "single"
                notes[best[1]]["lyric"]=(t["text"],syl)
    collect.unplaced=unplaced
    return voices,starts,systems

if __name__=="__main__":
    P=sys.argv[1]
    voices,starts,systems=collect(P)
    print("system starts",starts)
    for vi,v in enumerate(voices):
        v.sort(key=lambda e:e["onset"])
        over=0;gaps=0
        for a,b in zip(v,v[1:]):
            if a["onset"]+a["dur"]>b["onset"]+1e-6: over+=1; print("overlap v",vi,a["onset"],a["dur"],b["onset"],"sys",a["sys"])
            elif b["onset"]>a["onset"]+a["dur"]+1e-6: gaps+=1; print("gap v",vi,a["onset"]+a["dur"],"->",b["onset"],"sys",b["sys"])
        print("voice",vi,"events",len(v),"end",v[-1]["onset"]+v[-1]["dur"],"overlaps",over,"gaps",gaps)

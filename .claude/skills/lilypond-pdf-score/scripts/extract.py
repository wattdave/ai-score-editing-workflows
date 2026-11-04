import os, sys,pymupdf,json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from reader import *
from collections import defaultdict

HEAD_W=5.2
def extract(pdf):
    doc=pymupdf.open(pdf); out=[]
    for pn in range(len(doc)):
        pg=Page(doc,pn)
        nst=len(pg.staves); nsys=nst//4
        # stems
        stems=[]
        for (x,y,w,h) in pg.rects:
            if abs(w-0.2)<0.05 and 7<h<16: stems.append((x,y,y+h))
        stems=sorted(set((round(a,1),round(b,1),round(c,1)) for a,b,c in stems))
        beams=[q for q in pg.polys if q[2]-q[0]>3.0 and q[3]-q[1]<8]
        # barlines per system
        bar_rects=[(x,y,h) for (x,y,w,h) in pg.rects if 0.7<w<1.0 and h>15]
        events=defaultdict(list)  # staff -> list
        gl=[g for g in pg.glyphs if g["size"]==15.9]
        by_staff=defaultdict(list)
        for g in gl:
            by_staff[pg.staff_of(g["y"])].append(g)
        for si,gs in by_staff.items():
            s=pg.staves[si]
            gs.sort(key=lambda g:g["x"])
            heads=[g for g in gs if g["gid"] in (3,4,5,2) and g["x"]>0]
            for g in gs:
                gid=g["gid"]; h=pg.hs(si,g["y"])
                if gid in (3,4,5) or (gid==2):
                    kind={3:'w',2:'B',4:'h',5:'b'}[gid]
                    ev=dict(t='N',kind=kind,x=g["x"],hs=h,dots=0,flags=0,beams=0,gid=gid)
                    events[si].append(ev)
                elif gid==8: events[si].append(dict(t='R',dur=1.0,x=g["x"],hs=h,gid=gid,dots=0))
                elif gid==1: events[si].append(dict(t='R',dur=2.0,x=g["x"],hs=h,gid=gid,dots=0))
                elif gid==0: events[si].append(dict(t='R',dur=4.0,x=g["x"],hs=h,gid=gid,dots=0))
                elif gid==6: events[si].append(dict(t='R',dur=8.0,x=g["x"],hs=h,gid=gid,dots=0))
            # dots, flags, accidentals
            notes=[e for e in events[si] if e['t']=='N']
            rests=[e for e in events[si] if e['t']=='R']
            for g in gs:
                gid=g["gid"]
                if gid==9:
                    cand=[e for e in notes+rests if 3<=g["x"]-e["x"]<=14]
                    if cand:
                        e=min(cand,key=lambda e:g["x"]-e["x"]); e["dots"]+=1
                elif gid in (13,16):
                    exp=5.3 if gid==13 else 0.6
                    cand=[e for e in notes if abs(g["x"]-e["x"]-exp)<=1.5 and e['kind']=='b']
                    cand=[e for e in cand if 8<abs(g["y"]-(s["bot"]-e["hs"]*s["sp"]/2))<18]
                    if cand:
                        e=min(cand,key=lambda e:abs(g["x"]-e["x"]-exp)); e["flags"]+=1
                elif gid==7 and g["x"]>0:
                    # flat accidental left of a note
                    cand=[e for e in notes if 2<=e["x"]-g["x"]<=14 and abs(e["hs"]-pg.hs(si,g["y"]))<=0]
                    if cand:
                        e=min(cand,key=lambda e:e["x"]-g["x"]); e["acc"]='b'
                elif gid==8 and False: pass
            # beams: for each note, find stem and beams
            for e in notes:
                if e['kind']!='b': continue
                y=s["bot"]-e["hs"]*s["sp"]/2
                st=None
                for (x0,ya,yb) in stems:
                    if -0.7<= x0-e["x"] <=5.8 and (abs(ya-y)<1.2 or abs(yb-y)<1.2): st=(x0,ya,yb);break
                if not st: e['nostem']=True; continue
                tip = yb if abs(ya-y)<1.2 else ya
                n=0
                for (bx0,by0,bx1,by1) in beams:
                    if bx0-0.8<=st[0]<=bx1+0.8 and by0-3<=tip<=by1+3: n+=1
                e["beams"]=n
        for si in events:
            events[si].sort(key=lambda e:e["x"])
        # staff x extents & systems
        systems=[]
        for k in range(nsys):
            sts=list(range(4*k,4*k+4))
            ytop=pg.staves[sts[0]]["top"]-15; ybot=pg.staves[sts[-1]]["bot"]+5
            bl=sorted({round(x,1) for (x,y,h) in bar_rects if ytop<=y<=ybot})
            systems.append(dict(staves=sts,bars=bl,x0=pg.staves[sts[0]]["x0"],x1=pg.staves[sts[0]]["x1"]))
        out.append(dict(pn=pn,events={si:events[si] for si in events},systems=systems,staves=pg.staves))
    return out

def dur(e):
    if e['t']=='R': base=e['dur']
    else:
        base={'B':8.0,'w':4.0,'h':2.0,'b':1.0}[e['kind']]
        if e['kind']=='b':
            n=max(e['flags'],e['beams'])
            base=base/(2**n)
    d=base
    add=base/2
    for _ in range(e['dots']): d+=add; add/=2
    return d

if __name__=="__main__":
    res=extract(sys.argv[1])
    for pg in res:
        print("page",pg["pn"]+1,"systems",[ (s["staves"][0], len(s["bars"])) for s in pg["systems"]])
        for s in pg["systems"]:
            print(" system staves",s["staves"],"barlines",s["bars"])
            for si in s["staves"]:
                ev=pg["events"].get(si,[])
                # split by barlines
                bl=s["bars"]
                bars=defaultdict(float)
                for e in ev:
                    pass
                    k=sum(1 for b in bl if b<e["x"]+3)
                    bars[k]+=dur(e)
                print("  staff",si,"bar sums",[round(bars[k],2) for k in sorted(bars)])

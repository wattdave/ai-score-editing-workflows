import os, sys
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from extract import *
def timeline(pg,s):
    """onsets per staff with invisible lead-in filled from voices aligned at the same x"""
    ons={}
    for st in s["staves"]:
        t=0.0; L=[]
        for e in pg["events"].get(st,[]):
            L.append((e,t)); t+=dur(e)
        ons[st]=(L,t)
    # lead-in: voices whose first event is right of the system start
    xs0=min(L[0][0]["x"] for L,_ in ons.values() if L)
    refs=[st for st,(L,_) in ons.items() if L and L[0][0]["x"]<=xs0+5]
    for st,(L,t) in list(ons.items()):
        if not L or st in refs: continue
        lead=None
        for e,tt in L:
            for r in refs:
                for e2,t2 in ons[r][0]:
                    if abs(e2["x"]-e["x"])<1.5: lead=t2-tt;break
                if lead is not None: break
            if lead is not None: break
        if lead:
            ons[st]=([(e,tt+lead) for e,tt in L],t+lead)
    # rest retiming: a rest followed by an event whose column time disagrees with the majority
    from collections import Counter
    for _ in range(3):
        cols=defaultdict(list)
        for st,(L,t) in ons.items():
            seenR=False
            for e,tt in L:
                if e["t"]=="R" and e["dur"]>=2: seenR=True
                if not seenR: cols[round(e["x"]/1.5)].append(round(tt,3))
        maj={k:Counter(v).most_common(1)[0][0] for k,v in cols.items() if len(v)>=1}
        changed=False
        for st,(L,t) in list(ons.items()):
            shift=0.0; NL=[]
            for i,(e,tt) in enumerate(L):
                tt2=tt+shift
                k=round(e["x"]/1.5)
                if i>0 and L[i-1][0]["t"]=="R" and k in maj and abs(maj[k]-tt2)<=1.0 and abs(maj[k]-tt2)>1e-6 and shift==0.0:
                    shift=maj[k]-tt2; tt2=maj[k]; changed=True
                    p=NL[-1]; p[0]["dur"]=p[0].get("dur",0)+shift if p[0]["t"]=="R" else None
                NL.append([e,tt2])
            ons[st]=([(e,tt) for e,tt in NL],t+shift)
        if not changed: break
    return ons
if __name__=="__main__":
    res=extract(sys.argv[1])
    for pg in res:
        for si_,s in enumerate(pg["systems"]):
            ons=timeline(pg,s)
            cols=defaultdict(dict)
            for st,(L,t) in ons.items():
                for e,tt in L: cols[round(e["x"]/1.5)][st]=round(tt,3)
            mism=[(k*1.5,v) for k,v in sorted(cols.items()) if len(set(v.values()))>1]
            print(f"p{pg['pn']+1} sys{si_+1} totals {[round(t,2) for _,t in ons.values()]} misaligned {len(mism)}")
            for m in mism[:3]: print("    x",m[0],m[1])

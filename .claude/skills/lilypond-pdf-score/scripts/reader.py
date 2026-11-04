import pymupdf, sys, json
from collections import defaultdict

NAMES="CDEFGAB"
def diat_name(d):
    """d = diatonic index, C0=0. returns (letter, octave)."""
    return NAMES[d%7], d//7

class Page:
    def __init__(self, doc, pn):
        self.pn=pn; p=doc[pn]; self.p=p
        lines=[]
        for d in p.get_drawings():
            for it in d["items"]:
                if it[0]=="l":
                    a,b=it[1],it[2]
                    if abs(a.y-b.y)<0.01 and abs(a.x-b.x)>100:
                        lines.append((round(a.y,2),min(a.x,b.x),max(a.x,b.x)))
        ys=sorted({l[0] for l in lines})
        self.staves=[]
        for i in range(0,len(ys),5):
            g=ys[i:i+5]
            xs=[l for l in lines if l[0] in g]
            self.staves.append(dict(top=g[0],bot=g[4],sp=(g[4]-g[0])/4,x0=min(l[1] for l in xs),x1=max(l[2] for l in xs)))
        self.glyphs=[]
        for sp in p.get_texttrace():
            if "Emmentaler" in sp["font"]:
                for ch in sp["chars"]:
                    self.glyphs.append(dict(gid=ch[1],x=ch[2][0],y=ch[2][1],size=round(sp["size"],1),bb=ch[3]))
        self.rects=[]; self.polys=[]
        for d in p.get_drawings():
            for it in d["items"]:
                if it[0]=="re":
                    r=it[1]; self.rects.append((r.x0,r.y0,r.width,r.height))
            if d.get("fill") is not None and d["items"] and all(it[0]=="l" for it in d["items"]):
                r=d["rect"]; self.polys.append((r.x0,r.y0,r.x1,r.y1))
    def staff_of(self,y):
        best=None;bd=1e9
        for i,s in enumerate(self.staves):
            c=(s["top"]+s["bot"])/2; dd=abs(y-c)
            if dd<bd: bd=dd;best=i
        return best
    def hs(self,si,y):
        s=self.staves[si]; return round((s["bot"]-y)/(s["sp"]/2))

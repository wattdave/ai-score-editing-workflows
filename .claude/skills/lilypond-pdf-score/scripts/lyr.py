import os, sys, pymupdf
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
SH="A y n c M B o d C p e D q f P E r g Q F s h t i u j T v J l a m b ] 8 - 9 . é 0 1 2 ’ 3 ( 4 ) 5 [ 6 _ 7 ,".split(" ")
def gidmap():
    m={}
    for i,ch in enumerate(SH): m[i+2]= " " if ch=="_" else ("'" if ch=="’" else ch)
    return m
GM=gidmap()
def page_lyrics(doc,pn):
    """return list of dict(text,x0,x1,y) tokens from Roman 9.7 pt font (words split on gaps), plus hyphen tokens"""
    chars=[]
    for tr in doc[pn].get_texttrace():
        if "CenturySchL-Roma" not in tr["font"] or abs(tr["size"]-9.7)>0.4: continue
        for ch in tr["chars"]:
            x0,y0,x1,y1=ch[3]
            chars.append(dict(u=GM.get(ch[1],'?'),x0=x0,x1=x1,y=round(ch[2][1],1),ox=ch[2][0]))
    # group by baseline
    rows={}
    for c in chars: rows.setdefault(c["y"],[]).append(c)
    toks=[]
    for y,cs in rows.items():
        cs.sort(key=lambda c:c["ox"]); cur=None
        for c in cs:
            if cur and c["x0"]-cur["x1"]<1.6 and c["u"] != "-":
                cur["text"]+=c["u"]; cur["x1"]=c["x1"]
            else:
                if cur: toks.append(cur)
                cur=dict(text=c["u"],x0=c["x0"],x1=c["x1"],y=y)
                if c["u"]=="-":
                    toks.append(cur); cur=None
        if cur: toks.append(cur)
    seen=set()
    for dd in doc[pn].get_drawings():
        r=dd["rect"]
        if dd["type"] in ("f","fs") and 1.8<r.width<4.6 and r.height<1.2:
            k=(round(r.x0,1),round(r.y0,1))
            if k in seen: continue
            seen.add(k)
            toks.append(dict(text="-",x0=r.x0,x1=r.x1,y=round(r.y0+2.0,1)))
    return toks
if __name__=="__main__":
    d=pymupdf.open(sys.argv[1]); pn=int(sys.argv[2])
    for t in sorted(page_lyrics(d,pn),key=lambda t:(t["y"],t["x0"])):
        print(t["y"],round(t["x0"],1),round(t["x1"],1),repr(t["text"]))

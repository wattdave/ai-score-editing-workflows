"""Silent Night (Reinecke harmonisation), IMSLP235900, in C as printed. Pitches read from the PDF's glyph
coordinates (MusiXTeX font); rhythm, slurs and lyric alignment read from the page and checked against it."""
import sys
from xml.sax.saxutils import escape
STEP={"C":0,"D":1,"E":2,"F":3,"G":4,"A":5,"B":6}
TYPE={1:("16th",0),2:("eighth",0),3:("eighth",1),4:("quarter",0),6:("quarter",1),12:("half",1)}
def P(s): return (s[0],int(s[1:]))
def note(p,dur,voice=1,chord=False,ties=(),slurs=(),lyrics=(),staff=None):
    step,octv=P(p); ty,dot=TYPE[dur]
    x="<note>"+("<chord/>" if chord else "")
    x+=f"<pitch><step>{step}</step><octave>{octv}</octave></pitch><duration>{dur}</duration>"
    for t in ties: x+=f'<tie type="{t}"/>'
    x+=f"<voice>{voice}</voice><type>{ty}</type>"+("<dot/>" if dot else "")
    nt=""
    for t in ties: nt+=f'<tied type="{t}"/>'
    for t,n in slurs: nt+=f'<slur type="{t}" number="{n}"/>'
    if nt: x+=f"<notations>{nt}</notations>"
    for n,(txt,syl) in lyrics: x+=f'<lyric number="{n}"><syllabic>{syl}</syllabic><text>{escape(txt)}</text></lyric>'
    return x+"</note>"
def chord(pitches,dur,voice=1,ties_for=None,slurs_for=None,lyrics=()):
    ties_for=ties_for or {}; slurs_for=slurs_for or {}
    out=""
    for i,p in enumerate(pitches):
        out+=note(p,dur,voice,chord=i>0,ties=ties_for.get(i,()),slurs=slurs_for.get(i,()),lyrics=lyrics if i==0 else ())
    return out
# ---- lyrics: per bar, per soprano note; None = melisma. suffix: "-" begins/continues a word
def L(txt):
    if txt is None: return None
    mid_before=txt.startswith("~"); txt=txt.lstrip("~"); cont=txt.endswith("-"); txt=txt.rstrip("-")
    syl={(False,False):"single",(False,True):"begin",(True,True):"middle",(True,False):"end"}[(mid_before,cont)]
    return (txt,syl)
V={1:{},2:{},3:{},4:{}}
def setbar(b,v1,v2,v3,v4):
    for n,l in zip((1,2,3,4),(v1,v2,v3,v4)): V[n][b]=[L(t) for t in l]
setbar(1,["Si-",None,"~lent","night,"],["Si-",None,"~lent","night,"],["Si-",None,"~lent","night,"],["Stil-",None,"~le","Nacht,"])
setbar(2,["ho-",None,"~ly","night!"],["ho-",None,"~ly","night!"],["ho-",None,"~ly","night!"],["hei-","~li-","~ge","Nacht!"])
setbar(3,["All","is","calm,"],["Shep-","~hers","quake"],["Son","of","God"],["Al-","~les","schläft,"])
setbar(4,["all","is","bright."],["at","the","sight."],["love's","pure","light."],["ein-","~sam","wacht"])
setbar(5,["Round","yon","Vir-",None,"~gin,"],["Glo-","~ries","stream",None,"from"],["Ra-","~diant","beams",None,"from"],["nur","das","trau-","~te","hoch-"])
setbar(6,["Moth-","~er","and","Child."],["heav-","~en","a-","~far,"],["Thy","ho-","~ly","face"],["~hei-","~li-","~ge","Paar."])
setbar(7,["Ho-","~ly","in-","~fant","so"],["Heav'n-","~ly","hosts",None,"sing"],["With","the","dawn","of","re-"],["Hol-","~der","Kna-","~be","im"])
setbar(8,["ten-","~der","and","mild,"],["Al-","~le-","~lu-","~ia,"],["~deem-",None,"~ing","grace."],["lok-","~ki-","~gen","Haar,"])
setbar(9,["Sleep","in","heav-","~en-","~ly"],["Christ","the","Sav-","~ior","is"],["Je-","~sus","Lord,","at","Thy"],["Schlaf","in","himm-","~li-","~scher"])
setbar(10,["peace,",None],["born!",None],["birth.",None],["Ruh,",None])
setbar(11,["Sleep",None,"in","heav-","~en-","~ly"],["Christ",None,"the","Sav-","~ior","is"],["Je-",None,"~sus","Lord,","at","Thy"],["schlaf",None,"in","himm-","~li-","~scher"])
setbar(12,["peace."],["born!"],["birth."],["Ruh!"])
def lyr(b,i):
    return [(n,V[n][b][i]) for n in (1,2,3,4) if V[n][b][i] is not None]
# ---- music. Soprano/alto part: per bar list of (dur, S, A); tenor/bass part likewise.
RH_A=(3,1,2,6); RH_Q=(4,2,6); RH_5=(4,2,3,1,2)
SA={1:(RH_A,"G4 A4 G4 E4","E4 F4 E4 C4"),2:(RH_A,"G4 A4 G4 E4","E4 F4 E4 C4"),3:(RH_Q,"D5 D5 B4","F4 F4 F4"),
    4:(RH_Q,"C5 C5 G4","E4 E4 E4"),5:(RH_5,"A4 A4 C5 B4 A4","F4 F4 A4 G4 F4"),6:(RH_A,"G4 A4 G4 E4","E4 E4 E4 C4"),
    7:(RH_5,"A4 A4 C5 B4 A4","F4 F4 A4 G4 F4"),8:(RH_A,"G4 A4 G4 E4","E4 F4 E4 C4"),9:(RH_5,"D5 D5 F5 D5 B4","G4 G4 G4 G4 G4")}
TB={1:(RH_Q,"G3 G3 G3","C3 C3 C3"),2:(RH_Q,"G3 G3 G3","C3 C3 C3"),3:(RH_Q,"B3 B3 D4","G3 G3 F3"),4:(RH_Q,"C4 C4 C4","C3 C3 C3"),
    5:((4,2,4,2),"C4 C4 C4 C4","F3 F3 F3 F3"),6:(RH_A,"C4 C4 C4 C4","C3 C3 C3 C3"),7:(RH_5,"C4 C4 C4 C4 C4","F3 F3 F3 F3 F3"),
    8:(RH_A,"C4 C4 C4 C4","C3 C3 C3 C3"),9:(RH_5,"B3 B3 B3 B3 G3","G3 G3 G3 G3 G3")}
SLUR={(1,0):{"S":("start",1),"A":("start",2)},(1,1):{"S":("stop",1),"A":("stop",2)},
      (2,0):{"S":("start",1),"A":("start",2)},(2,1):{"S":("stop",1),"A":("stop",2)},
      (5,2):{"S":("start",1),"A":("start",2)},(5,3):{"S":("stop",1),"A":("stop",2)}}
def part1():
    out=""
    for b in range(1,13):
        out+=f'<measure number="{b}">'
        if b==1:
            out+="<attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>6</beats><beat-type>8</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>"
        if b in SA:
            rh,s,a=SA[b]; s=s.split(); a=a.split()
            for i,(d,sp,ap) in enumerate(zip(rh,s,a)):
                sl=SLUR.get((b,i),{})
                out+=chord([sp,ap],d,slurs_for={0:[sl["S"]] if "S" in sl else (),1:[sl["A"]] if "A" in sl else ()},lyrics=lyr(b,i))
        elif b==10:
            out+=chord(["C5","G4"],6,ties_for={1:("start",)},slurs_for={0:[("start",1)]},lyrics=lyr(b,0))
            out+=chord(["E5","G4"],6,ties_for={1:("stop",)},slurs_for={0:[("stop",1)]},lyrics=lyr(b,1))
        elif b==11:
            S=[("C5",3),("G4",1),("E4",2),("G4",3),("F4",1),("D4",2)]
            for i,(p,d) in enumerate(S): out+=note(p,d,1,lyrics=lyr(b,i))
            out+="<backup><duration>12</duration></backup>"
            for p,d in [("C4",4),("C4",2),("B3",3),("B3",1),("B3",2)]: out+=note(p,d,2)
        elif b==12:
            out+=note("C4",12,1,lyrics=lyr(b,0))+'<barline location="right"><bar-style>light-heavy</bar-style></barline>'
        out+="</measure>"
    return out
def part2():
    out=""
    for b in range(1,13):
        out+=f'<measure number="{b}">'
        if b==1:
            out+="<attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>6</beats><beat-type>8</beat-type></time><clef><sign>F</sign><line>4</line></clef></attributes>"
        if b in TB:
            rh,t,bs=TB[b]; t=t.split(); bs=bs.split()
            for i,(d,tp,bp) in enumerate(zip(rh,t,bs)):
                if b==9 and i==4: out+=note("G3",d,1)         # tenor and bass share this G3
                else: out+=chord([tp,bp],d)
        elif b==10:
            out+=chord(["E4","C4"],6,ties_for={1:("start",)},slurs_for={0:[("start",1)]})
            out+=note("C4",6,1,ties=("stop",),slurs=[("stop",1)])   # tenor and bass share this C4
        elif b==11:
            TT=[("G3",4),("G3",2),("G3",3),("G3",1),("G3",2)]; BB=[("E3",4),("C3",2),("G2",3),("G2",1),("G2",2)]
            for (tp,d),(bp,_) in zip(TT,BB): out+=chord([tp,bp],d)
        elif b==12:
            out+=chord(["E3","C3"],12)+'<barline location="right"><bar-style>light-heavy</bar-style></barline>'
        out+="</measure>"
    return out
xml=f'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.0">
<work><work-title>Silent Night</work-title></work>
<identification><creator type="composer">Franz Xaver Gruber (1818)</creator><creator type="arranger">harmonisation: Carl H. Reinecke (1824-1910)</creator><creator type="lyricist">Text: Joseph Mohr, 1818; translation by John Freeman Young (1820-1885)</creator>
<rights>Public domain. Transcribed from IMSLP #235900 for rehearsal use.</rights></identification>
<part-list><score-part id="P1"><part-name>Soprano/Alto</part-name><part-abbreviation>S/A</part-abbreviation></score-part>
<score-part id="P2"><part-name>Tenor/Bass</part-name><part-abbreviation>T/B</part-abbreviation></score-part></part-list>
<part id="P1">{part1()}</part><part id="P2">{part2()}</part></score-partwise>'''
open(sys.argv[1],"w",encoding="utf-8").write(xml)

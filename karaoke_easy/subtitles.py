"""Genera subtítulos ASS con efecto karaoke (\\kf)."""
from dataclasses import dataclass


@dataclass
class Word:
    text: str
    start: float
    end: float


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(s: str) -> str:
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_lines(words, max_chars=42, max_gap=1.2):
    lines, cur = [], []
    for w in words:
        forced = w.text.startswith("\n")
        if forced:
            w = Word(w.text[1:], w.start, w.end)
        if cur and forced:
            # Línea de la letra original: respetarla (partirla solo si es muy larga)
            lines.append(cur)
            cur = []
        if cur:
            length = sum(len(x.text) + 1 for x in cur) + len(w.text)
            if length > max_chars or w.start - cur[-1].end > max_gap:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


MIN_GAP = 4.0     # segundos sin voz a partir de los cuales se muestran puntitos
COUNT_MAX = 4.0   # duración máxima de la cuenta atrás
N_DOTS = 4


def countdowns(lines):
    """Puntitos que se rellenan antes de que vuelva la voz (intro y pausas largas)."""
    out = []
    prev_end = 0.0
    for line in lines:
        start = line[0].start
        gap = start - prev_end
        if gap >= MIN_GAP or (prev_end == 0.0 and start >= 2.0):
            dur = min(COUNT_MAX, gap)
            step = max(1, int(round(dur * 100 / N_DOTS)))
            text = "".join(f"{{\\kf{step}}}● " for _ in range(N_DOTS)).strip()
            out.append(f"Dialogue: 1,{_ts(start - dur)},{_ts(start)},Dots,,0,0,0,,{{\\fad(150,0)}}{text}")
        prev_end = line[-1].end
    return out


def build_ass(words, title, palette, width=1920, height=1080, lead=1.5):
    """palette: dict con 'sung','unsung','outline' en formato &HBBGGRR."""
    lines = group_lines(words)
    fs = int(height * 0.075)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Top,Arial,{fs},{palette['sung']},{palette['unsung']},{palette['outline']},&H80000000,-1,0,0,0,100,100,1,0,1,4,2,8,60,60,{int(height*0.38)},1
Style: Bot,Arial,{fs},{palette['sung']},{palette['unsung']},{palette['outline']},&H80000000,-1,0,0,0,100,100,1,0,1,4,2,2,60,60,{int(height*0.30)},1
Style: Dots,Arial,{int(fs*0.9)},{palette['sung']},&H00FFFFFF,{palette['outline']},&H80000000,-1,0,0,0,100,100,12,0,1,4,2,8,60,60,{int(height*0.38 - fs*1.4)},1
Style: Title,Arial,{int(fs*1.1)},&H00FFFFFF,&H00FFFFFF,{palette['outline']},&H80000000,-1,0,0,0,100,100,2,0,1,4,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    first = lines[0][0].start if lines else 5.0
    for d in countdowns(lines):
        ev.append(d)
    if first > 2.5:
        title_end = first - min(COUNT_MAX, first) if first >= MIN_GAP else first - lead
        ev.append(f"Dialogue: 0,{_ts(0)},{_ts(max(0.5, title_end))},Title,,0,0,0,,{{\\fad(400,400)}}{_esc(title)}")
    for i, line in enumerate(lines):
        style = "Top" if i % 2 == 0 else "Bot"
        start = line[0].start
        prev_end = lines[i - 1][-1].end if i else 0.0
        show = max(prev_end if i else 0.0, start - lead)
        # La línea siguiente aparece mientras se canta ésta: alternar arriba/abajo
        if i >= 1:
            show = max(lines[i - 1][0].start, start - lead * 2)
        end = line[-1].end + 0.4
        text = ""
        pre = int(round((start - show) * 100))
        if pre > 0:
            text += f"{{\\k{pre}}}"
        for j, w in enumerate(line):
            nxt = line[j + 1].start if j + 1 < len(line) else w.end
            dur = max(1, int(round((nxt - w.start) * 100)))
            text += f"{{\\kf{dur}}}{_esc(w.text.strip())} "
        ev.append(f"Dialogue: 0,{_ts(show)},{_ts(end)},{style},,0,0,0,,{{\\fad(200,200)}}{text.strip()}")
    return head + "\n".join(ev) + "\n"

# Inline text formatting (bold / italic / underline) for ZeroWriter.
#
# Formatting is stored in the text itself as invisible control characters that
# toggle a style on/off, e.g. "plain \x01bold\x01 plain". They take no screen
# width and are ignored by word/character counts. Every line is self-contained:
# when a style is still active at a line break, the next line starts with the
# markers needed to turn it back on.
#
# The only font is Courier Prime regular, so bold is faked by double-striking,
# italic by shearing the rendered glyphs, and underline by drawing a line.

from PIL import Image, ImageDraw

BOLD = '\x01'
ITALIC = '\x02'
UNDERLINE = '\x03'
MARKERS = (BOLD, ITALIC, UNDERLINE)
_ORDER = {BOLD: 0, ITALIC: 1, UNDERLINE: 2}

ITALIC_SLANT = 0.22


def is_marker(ch):
    return ch in _ORDER


def strip_markers(s):
    return ''.join(c for c in s if c not in _ORDER)


def vis_len(s):
    """Number of characters that take up screen width."""
    return sum(1 for c in s if c not in _ORDER)


def raw_index(s, nvis):
    """Index in s just after its first nvis visible characters."""
    seen = 0
    for i, c in enumerate(s):
        if c in _ORDER:
            continue
        if seen == nvis:
            return i
        seen += 1
    return len(s)


def format_state(s):
    """(bold, italic, underline) in effect at the end of s."""
    state = [False, False, False]
    for c in s:
        if c in _ORDER:
            state[_ORDER[c]] = not state[_ORDER[c]]
    return tuple(state)


def active_markers(state):
    """Markers that turn on every style set in state (for the start of a line)."""
    return ''.join(m for m, on in zip(MARKERS, state) if on)


def toggle(s, marker):
    """s with marker toggled at the end. Pressing the same shortcut twice in a
    row cancels out instead of leaving a pair of useless markers."""
    if s.endswith(marker):
        return s[:-1]
    return s + marker


def _draw_run(image, draw, x, y, run, font, bold, italic, underline, line_h):
    width = font.getlength(run)
    if not run:
        return width
    ascent = font.getmetrics()[0]
    if italic:
        pad = int(ITALIC_SLANT * ascent) + 2
        size = (int(width) + pad + 2, line_h)
        mask = Image.new('L', size, 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.fontmode = '1'
        mdraw.text((0, 0), run, font=font, fill=255)
        if bold:
            mdraw.text((1, 0), run, font=font, fill=255)
        # shear about the baseline: the top of each glyph leans to the right
        mask = mask.transform(size, Image.AFFINE,
                              (1, ITALIC_SLANT, -ITALIC_SLANT * ascent, 0, 1, 0),
                              resample=Image.NEAREST)
        image.paste(0, (int(round(x)), int(y)), mask)
    else:
        draw.text((x, y), run, font=font, fill=0)
        if bold:
            draw.text((x + 1, y), run, font=font, fill=0)
    if underline:
        uy = y + ascent + 3
        draw.line((x, uy, x + width, uy), fill=0, width=1)
    return width


def draw_formatted(image, draw, x, y, text, font, state=(False, False, False), line_h=36):
    """Draw text containing style markers starting at (x, y) with the given
    initial style. Returns (x after the text, style at the end of the text)."""
    bold, italic, underline = state
    run = ''
    for c in text:
        if c in _ORDER:
            x += _draw_run(image, draw, x, y, run, font, bold, italic, underline, line_h)
            run = ''
            if c == BOLD:
                bold = not bold
            elif c == ITALIC:
                italic = not italic
            else:
                underline = not underline
        else:
            run += c
    x += _draw_run(image, draw, x, y, run, font, bold, italic, underline, line_h)
    return x, (bold, italic, underline)


# ---- Markdown on disk -------------------------------------------------------
# bold = **x**, italic = *x*, underline = <u>x</u> (Markdown has no underline).
# Each line is converted on its own, so a style that spans a wrapped line break
# is closed at the end of one line and reopened on the next.

import re

_ESCAPE = re.compile(r'([\\*_<`])')
_MD_TOKEN = re.compile(r'\\[\\*_<`]|<u>|</u>|\*\*\*|\*\*|\*')


def _wrap_md(text, bold, italic, underline):
    text = _ESCAPE.sub(r'\\\1', text)
    stars = '*' * ((2 if bold else 0) + (1 if italic else 0))
    text = stars + text + stars
    return '<u>' + text + '</u>' if underline else text


def to_markdown(line):
    """One line with style markers -> Markdown."""
    runs, buf, state = [], '', (False, False, False)
    for c in line:
        if c in _ORDER:
            if buf:
                runs.append((buf, state))
            buf = ''
            s = list(state)
            s[_ORDER[c]] = not s[_ORDER[c]]
            state = tuple(s)
        else:
            buf += c
    if buf:
        runs.append((buf, state))
    out = []
    for text, st in runs:
        if not any(st):
            out.append(_ESCAPE.sub(r'\\\1', text))
            continue
        # Markdown won't close emphasis after whitespace, so keep it outside
        core = text.strip(' ')
        if not core:
            out.append(text)
            continue
        lead = text[:len(text) - len(text.lstrip(' '))]
        trail = text[len(text.rstrip(' ')):]
        out.append(lead + _wrap_md(core, *st) + trail)
    return ''.join(out)


def from_markdown(line):
    """One line of Markdown -> text with style markers."""
    out, pos = [], 0
    for m in _MD_TOKEN.finditer(line):
        out.append(line[pos:m.start()])
        tok = m.group()
        if tok[0] == '\\':
            out.append(tok[1])
        elif tok in ('<u>', '</u>'):
            out.append(UNDERLINE)
        else:
            if len(tok) >= 2:
                out.append(BOLD)
            if len(tok) % 2 == 1:
                out.append(ITALIC)
        pos = m.end()
    out.append(line[pos:])
    return ''.join(out)

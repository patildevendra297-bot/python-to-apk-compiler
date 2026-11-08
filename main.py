"""
Code Nexus v1.0 (made from SmartHazri v6.1) - Attendance + Online Tests + Marks + protected PDF Notes + Fees (UPI QR) + WhatsApp to parents (Kivy + Supabase, single file)
(upgrade of main_v4.py: same look, tabs and features; Firebase replaced by Supabase)

Cloud  : Supabase Auth + Postgres with Row Level Security, called over HTTPS with urllib (no SDK needed).
Offline: SQLite cache + outbox. Anything done offline is uploaded automatically when internet returns.
Sync   : runs in background threads while the app is open (UI never freezes).
APK    : copy this file as main.py in Buildozer. requirements = see requirements.txt
SETUP  : 1) run supabase_setup.sql (old) THEN supabase_setup_v6.sql (new) in Supabase SQL Editor  2) paste your sb_publishable_ key below.
BUILD  : buildozer requirements must also include: qrcode (auto UPI QR), pillow (resize QR/photos), pyjnius (PDF viewer + screenshot block).
"""
import os, re, csv, io, time, json, ssl, uuid, socket, threading, sqlite3, calendar, base64, traceback
import urllib.request, urllib.error, urllib.parse, email.utils, datetime as dt
from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.utils import get_color_from_hex as hx
from kivy.graphics import Color, Line, Rectangle, Ellipse
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# ===================== CONFIGURATION =====================
SUPABASE_URL = "https://xznopglutfgkpgkabsvf.supabase.co"
SUPABASE_KEY = "sb_publishable_CvtK6-eOPB_mBWbqdTZqsQ_lJZpLdaq"      # publishable key (safe to ship; never use a secret/service_role key)
APP_VERSION = "6.1.0"
# =========================================================

def asset(name):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    return p if os.path.exists(p) else ""


LOGO = asset("logo.png")      # Code Nexus logo (shown top-left)


def configured():
    return "PUT_" not in SUPABASE_KEY and len(SUPABASE_KEY) > 20


# ---------- colors (same palette as SmartHazri v4) ----------
WHITE = [1, 1, 1, 1]
BG, AC, OK, NO, LV = hx("#f6f2fb"), hx("#5a1c8a"), hx("#16a34a"), hx("#dc2626"), hx("#d97706")
GOLD = hx("#c9962b")
MU, TX, GR = hx("#6f6a7d"), hx("#14192e"), hx("#ebe4f3")
HERO_SUB = [.93, .87, 1, 1]
CARD, IN = WHITE, hx("#f3eef9")
ST_COL = {"P": OK, "A": NO, "L": LV}
ST_TXT = {"P": "Present", "A": "Absent", "L": "Leave"}
BRANCHES = ["CSE", "AI/ML", "DS", "EC", "IT", "Other"]
BRANCH_ORDER = ["CSE", "AI/ML", "DS", "IT", "EC"]      # order used in the daily attendance text file
DAY_FOLDER = "today attendance"                          # folder in phone storage (Documents/today attendance)
YEARS = ["1st", "2nd", "3rd", "4th"]
SEMS = ["1", "2", "3", "4", "5", "6", "7", "8"]
SECS = ["A", "B", "C", "D", "E", "F"]
BATCHES = ["B1", "B2", "B3", "B4"]
CLASSES = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
SSECS = ["-", "A", "B", "C", "D", "E"]
NS = uuid.UUID("6f1f3c5e-0b7a-4a43-9a0e-5b2f0c1d7a11")   # namespace for deterministic ids
DEFAULT_SUB = str(uuid.uuid5(NS, "code-nexus-default-subject"))   # the app has no subjects: one hidden default subject is used everywhere
SEM_BY_YEAR = {"1st": ["1", "2"], "2nd": ["3", "4"], "3rd": ["5", "6"], "4th": ["7", "8"]}

KV = """
<Panel>:
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(self.rad)]
<RBtn>:
    canvas.before:
        Color:
            rgba: self.bg if self.state == 'normal' else [self.bg[0]*.78, self.bg[1]*.78, self.bg[2]*.78, 1]
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
<Cell>:
    canvas.before:
        Color:
            rgba: self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]
<Bar>:
    canvas:
        Color:
            rgba: self.track
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(5)]
        Color:
            rgba: self.col
        RoundedRectangle:
            pos: self.pos
            size: self.width * min(max(self.value, 0), 100) / 100., self.height
            radius: [dp(5)]
<Ring>:
    canvas:
        Color:
            rgba: self.track
        Line:
            circle: (self.center_x, self.center_y, min(self.width, self.height) / 2 - dp(8))
            width: dp(9)
        Color:
            rgba: self.col
        Line:
            circle: (self.center_x, self.center_y, min(self.width, self.height) / 2 - dp(8), 0, max(0.5, self.value * 3.6))
            width: dp(9)
            cap: 'round'
    Label:
        text: '%d%%' % root.value
        font_size: sp(24)
        bold: True
        color: root.tx
<Initials>:
    canvas.before:
        Color:
            rgba: self.col
        Ellipse:
            pos: self.pos
            size: self.size
    Label:
        text: root.text
        font_size: self.parent.height * .38 if self.parent else sp(20)
        bold: True
        color: 1, 1, 1, 1
<Loader>:
    canvas.before:
        Color:
            rgba: 0, 0, 0, .45
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: root.card
        RoundedRectangle:
            pos: self.center_x - dp(110), self.center_y - dp(60)
            size: dp(220), dp(120)
            radius: [dp(18)]
        Color:
            rgba: root.col
        Line:
            circle: (self.center_x, self.center_y + dp(20), dp(16), root.angle, root.angle + 260)
            width: dp(3)
            cap: 'round'
    Label:
        text: root.text
        size_hint: None, None
        size: dp(200), dp(40)
        pos: root.center_x - dp(100), root.center_y - dp(52)
        color: root.tx
        font_size: sp(13)
"""


# ---------- widgets ----------
class Panel(BoxLayout):
    bg = ListProperty([1, 1, 1, 1])
    rad = NumericProperty(16)

    def __init__(self, **k):
        k.setdefault("bg", list(CARD))
        super().__init__(**k)


class Card(Panel):
    def __init__(self, **k):
        k.setdefault("orientation", "vertical")
        k.setdefault("padding", dp(14))
        k.setdefault("spacing", dp(6))
        super().__init__(size_hint_y=None, **k)
        self.bind(minimum_height=self.setter("height"))


class RBtn(ButtonBehavior, Label):
    bg = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        k.setdefault("size_hint_y", None)
        k.setdefault("height", dp(46))
        k.setdefault("bold", True)
        k.setdefault("font_size", sp(14))
        k.setdefault("bg", list(AC))
        super().__init__(**k)


class Cell(Label):
    bg = ListProperty([.9, .9, .9, 1])


class DayCell(ButtonBehavior, Cell):
    pass


class Bar(Widget):
    value = NumericProperty(0)
    col = ListProperty([0, .6, .2, 1])
    track = ListProperty([.9, .91, .94, 1])

    def __init__(self, **k):
        k.setdefault("track", list(GR))
        super().__init__(**k)


class Ring(FloatLayout):
    value = NumericProperty(0)
    col = ListProperty([0, .6, .2, 1])
    track = ListProperty([.9, .91, .94, 1])
    tx = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        k.setdefault("track", list(GR))
        k.setdefault("tx", list(TX))
        super().__init__(**k)


class Initials(FloatLayout):
    text = StringProperty("")
    col = ListProperty([.49, .23, .93, 1])


class Loader(FloatLayout):
    text = StringProperty("Please wait...")
    angle = NumericProperty(0)
    card = ListProperty([1, 1, 1, 1])
    col = ListProperty([.3, .2, .8, 1])
    tx = ListProperty([0, 0, 0, 1])

    def __init__(self, **k):
        super().__init__(card=list(CARD), col=list(AC), tx=list(TX), **k)
        self.anim = Animation(angle=360, d=.9) + Animation(angle=0, d=0)
        self.anim.repeat = True

    def start(self):
        self.anim.start(self)

    def stop(self):
        self.anim.cancel(self)

    def on_touch_down(self, t):
        return True

    def on_touch_move(self, t):
        return True

    def on_touch_up(self, t):
        return True


# ---------- small ui helpers ----------
def lbl(t, size=14, color=None, bold=False, align="left", w=None):
    l = Label(text=str(t), font_size=sp(size), color=color or TX, bold=bold, halign=align, valign="middle", size_hint_y=None)
    if w:
        l.size_hint_x = None
        l.width = dp(w)
    l.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
    l.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(6)))
    return l


def inp(hint, text="", password=False, h=46):
    return TextInput(hint_text=hint, text=text, multiline=False, password=password, size_hint_y=None, height=dp(h),
                     padding=[dp(12), dp(13)], font_size=sp(15), write_tab=False, background_normal="", background_active="",
                     background_color=list(IN), foreground_color=TX, cursor_color=AC, hint_text_color=MU)


def tin(st, key, hint, password=False, num=False):
    t = inp(hint, st.get(key, ""), password)
    if num:
        t.input_filter = "int"
    t.bind(text=lambda i, v: st.__setitem__(key, v))
    return t


def spin(st, key, values, cb=None):
    values = list(values) or ["-"]
    s = Spinner(text=st.get(key) if st.get(key) in values else values[0], values=values, size_hint_y=None, height=dp(46),
                font_size=sp(15), background_normal="", background_color=list(IN), color=TX)
    st[key] = s.text
    s.bind(text=lambda i, v: (st.__setitem__(key, v), cb and Clock.schedule_once(lambda d: cb(), 0)))
    return s


def row(*ws, h=46, gap=8):
    r = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(h), spacing=dp(gap))
    for w in ws:
        r.add_widget(w)
    return r


KINDS = {"primary": ("AC", "W"), "muted": ("MU", "W"), "ghost": ("GR", "AC"), "danger": ("NO", "W"), "ok": ("OK", "W"),
         "warn": ("LV", "W"), "plain": ("CARD", "MU"), "plaindanger": ("CARD", "NO")}


def btn(text, cb, kind="primary", **k):
    bgk, fgk = KINDS[kind]
    g = globals()
    b = RBtn(text=text, bg=list(g[bgk]), color=WHITE if fgk == "W" else g[fgk], **k)
    b.bind(on_release=lambda *_: cb())
    return b


def small(text, cb, kind="muted", w=48, **k):
    return btn(text, cb, kind, size_hint_x=None, width=dp(w), **k)


def pop(title, content, h=None, w=.92):
    return Popup(title=title, content=content, size_hint=(w, None if h else .8), height=dp(h or 100), background="",
                 background_color=list(CARD), title_color=TX, separator_color=AC, auto_dismiss=False)


def msg(title, text, h=None):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    b.add_widget(lbl(text, 14))
    n = len(text) // 38 + text.count("\n") + 1
    p = pop(title, b, h or min(max(190, 130 + n * 24), 480))
    b.add_widget(btn("OK", p.dismiss))
    p.open()
    return p


def ask(title, text, yes, yes_text="Yes", kind="danger"):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    b.add_widget(lbl(text, 14))
    n = len(text) // 38 + text.count("\n") + 1
    p = pop(title, b, min(max(210, 150 + n * 24), 500))
    b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn(yes_text, lambda: (p.dismiss(), yes()), kind)))
    p.open()


def prompt(title, hint, done, password=True, text=""):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    t = inp(hint, text, password=password)
    b.add_widget(t)
    p = pop(title, b, 220)
    b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn("OK", lambda: (p.dismiss(), done(t.text)))))
    p.open()


def info(title, text):
    b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
    sv = ScrollView()
    sv.add_widget(lbl(text, 13))
    b.add_widget(sv)
    p = pop(title, b)
    b.add_widget(btn("Close", p.dismiss))
    p.open()


def grow(bar, val, delay=.2):
    Clock.schedule_once(lambda d: Animation(value=val, d=.8, t="out_cubic").start(bar), delay)


# ---------- pure helpers ----------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(s):
    return bool(EMAIL_RE.match(s or ""))


def valid_mobile(s):
    return bool(re.fullmatch(r"\+?\d{10,15}", s or ""))


def valid_enroll(s):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/.]{2,29}", s or ""))


def vd(x):
    try:
        dt.date.fromisoformat(x)
        return True
    except Exception:
        return False


def today():
    return dt.date.today().isoformat()


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def calc(p, a, l, mode="total"):
    """Return (total, percent). mode 'total': leave counts in total (Present/(P+A+L)); 'excluded': old SmartHazri (P/(P+A))."""
    t = p + a + l if mode == "total" else p + a
    return t, (p * 100.0 / t if t else 0.0)


def pstr(pc, t):
    return "%.2f%%" % pc if t else "-"


def class_label(c, batch=None):
    s = "%s | %s Year" % (c.get("branch"), c.get("year"))
    if c.get("semester") not in (None, "", "-"):
        s += " | Sem %s" % c.get("semester")
    if c.get("section") not in (None, "", "-"):
        s += " | Sec %s" % c.get("section")
    b = batch if batch is not None else c.get("batch")
    return s + (" | " + b if b else "")


def branch_key(b):
    """Sort key so branches come as CSE, AI/ML, DS, EC, EX and everything else after."""
    x = str(b or "").strip().upper().replace(" ", "").replace("-", "").replace("/", "")
    for i, name in enumerate(BRANCH_ORDER):
        if x == name.upper().replace("/", ""):
            return (i, "")
    return (len(BRANCH_ORDER), str(b or "").upper())


def year_rank(y):
    return YEARS.index(y) if y in YEARS else len(YEARS)


def initials(name):
    p = (name or "?").split()
    return ((p[0][:1] + (p[-1][:1] if len(p) > 1 else "")) or "?").upper()


def sid_for(class_id, subject_id, date, batch):
    return str(uuid.uuid5(NS, "%s|%s|%s|%s" % (class_id, subject_id, date, batch)))


def rid_for(session_id, student_id):
    return str(uuid.uuid5(NS, "%s|%s" % (session_id, student_id)))


class NetError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status, msg, code=""):
        super().__init__(msg)
        self.status, self.msg, self.code = status, msg, code


def friendly(e):
    if isinstance(e, NetError):
        return 'Could not connect to the server (internet / SSL / permission). Your changes are safe on the phone and will sync when internet returns.\n\nDetail: %s' % str(e)[:160]
    if isinstance(e, ApiError):
        m, c = (e.msg or "").lower(), str(e.code or "")
        if c == "PGRST202" or "could not find the function" in m:
            return 'Supabase database setup is incomplete. Run supabase_setup.sql (and supabase_setup_v6.sql) fully in the Supabase SQL Editor.'
        if "invalid login" in m or c == "invalid_credentials":
            return "Wrong email/ID or password."
        if "already registered" in m or c in ("user_already_exists", "email_exists"):
            return "This email is already registered."
        if c == "23505" or "duplicate key" in m:
            return "This record already exists (duplicate)."
        if c == "23503":
            return "This item is linked to other records, so it cannot be removed."
        if c == "42501" or e.status == 403:
            return "You do not have permission for this action."
        if e.status == 429 or "rate limit" in m or c.startswith("over_"):
            if "email" in m or c == "over_email_send_rate_limit":
                return ("Supabase has hit its email sending limit (it is very low on the free plan).\n\nFix: Supabase > Authentication > Sign In / Providers > Email, turn 'Confirm email' OFF, then wait about 1 hour or add a Custom SMTP.")
            return 'Too many attempts. Wait 5-10 minutes and try again.\n\nServer: %s' % (e.msg or c)[:120]
        if "not confirmed" in m:
            return "Please confirm your email first (check your inbox), then login."
        if "password" in m and any(x in m for x in ("least", "weak", "short", "characters")):
            return "Password is too weak. Use at least 6 characters."
        if "token" in m and any(x in m for x in ("expired", "invalid")):
            return "The code is wrong or expired. Request a new one."
        if "database error saving new user" in m:
            return "Could not create the account. Email or enrollment number may already be in use."
        if "same" in m and "password" in m:
            return "New password must be different from the old one."
        if "sending" in m and "email" in m or c in ("unexpected_failure", "over_email_send_rate_limit"):
            return ("Supabase could not send the email. Go to Supabase > Authentication > Sign In / Providers > Email and turn 'Confirm email' OFF (or wait for the email rate limit to reset).\n\nServer: %s" % (e.msg or "")[:140])
        if e.status >= 500:
            return 'Server problem. Please try again.\n\nServer: %s' % (e.msg or c or e.status)[:160]
        return e.msg or "Something went wrong."
    return "Something went wrong: %s" % e


def make_csv(head, rows):
    o = io.StringIO()
    w = csv.writer(o)
    w.writerow(head)
    w.writerows(rows)
    return o.getvalue().encode("utf-8-sig")


def _pe(s):
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")


def make_pdf(title, sub, head, rows, widths=None):
    """Tiny dependency-free PDF table writer (A4 landscape, Helvetica)."""
    W, H, M, per = 842, 595, 36, 27
    n = len(head)
    widths = widths or [1] * n
    tot, xs, x = float(sum(widths)), [], float(M)
    for w in widths:
        xs.append(x)
        x += (W - 2 * M) * w / tot
    cw = [(W - 2 * M) * w / tot for w in widths]
    pages = [rows[i:i + per] for i in range(0, len(rows), per)] or [[]]
    out, offs = [b"%PDF-1.4\n"], []

    def add(body):
        offs.append(sum(len(z) for z in out))
        out.append(("%d 0 obj\n" % len(offs)).encode() + body + b"\nendobj\n")

    kids = " ".join("%d 0 R" % (5 + 2 * i) for i in range(len(pages)))
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(pages))).encode())
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    for pi, pg in enumerate(pages):
        ops = ["BT /F2 15 Tf %d %d Td (%s) Tj ET" % (M, H - 36, _pe(title)),
               "BT /F1 9 Tf %d %d Td (%s  -  page %d/%d) Tj ET" % (M, H - 52, _pe(sub), pi + 1, len(pages))]
        y = H - 78

        def line(vals, font, y):
            for i, v in enumerate(vals):
                s = str(v)
                mx = max(3, int(cw[i] / 4.7))
                s = s if len(s) <= mx else s[:mx - 1] + "."
                ops.append("BT /%s 9 Tf %.1f %d Td (%s) Tj ET" % (font, xs[i], y, _pe(s)))

        line(head, "F2", y)
        ops.append("%d %d m %d %d l S" % (M, y - 4, W - M, y - 4))
        for r in pg:
            y -= 16
            line(r, "F1", y)
        st = "\n".join(ops).encode("latin-1", "replace")
        add(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
             % (W, H, 6 + 2 * pi)).encode())
        add(b"<< /Length %d >>\nstream\n" % len(st) + st + b"\nendstream")
    xo = sum(len(z) for z in out)
    out.append(("xref\n0 %d\n0000000000 65535 f \n" % (len(offs) + 1)).encode())
    for o in offs:
        out.append(("%010d 00000 n \n" % o).encode())
    out.append(("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(offs) + 1, xo)).encode())
    return b"".join(out)


# ---------- local database (SQLite cache + outbox) ----------
SCHEMA = {
    "profiles": ["id", "role", "first_name", "last_name", "full_name", "email", "mobile", "is_active", "created_at", "updated_at"],
    "classes": ["id", "kind", "branch", "year", "semester", "section", "created_at", "updated_at"],
    "subjects": ["id", "code", "name", "created_at", "updated_at"],
    "students": ["id", "enrollment", "class_id", "batch", "college_name", "mentor_id", "created_at", "updated_at"],
    "teachers": ["id", "employee_id", "department", "subject_note", "created_at", "updated_at"],
    "class_subjects": ["id", "class_id", "subject_id", "teacher_id", "created_at", "updated_at"],
    "student_subjects": ["id", "student_id", "subject_id", "created_at", "updated_at"],
    "attendance_sessions": ["id", "class_id", "subject_id", "date", "batch", "marked_by", "created_at", "updated_at"],
    "attendance_records": ["id", "session_id", "student_id", "status", "remark", "marked_by", "created_at", "updated_at"],
    "notifications": ["id", "user_id", "title", "body", "kind", "is_read", "created_at", "updated_at"],
    "leave_requests": ["id", "student_id", "from_date", "to_date", "reason", "status", "decided_by", "created_at", "updated_at"],
    # ---- v6 ----
    "tests": ["id", "class_id", "subject_id", "title", "duration_min", "is_published", "created_by", "created_at", "updated_at"],
    "test_questions": ["id", "test_id", "sort_no", "question", "opt_a", "opt_b", "opt_c", "opt_d", "marks", "created_at", "updated_at"],
    "test_answers": ["id", "correct", "created_at", "updated_at"],          # staff only (RLS) - students never receive correct answers
    "test_attempts": ["id", "test_id", "student_id", "score", "total", "answers", "submitted_at", "created_at", "updated_at"],
    "marks": ["id", "student_id", "subject_id", "exam_name", "exam_date", "obtained", "max_marks", "entered_by", "created_at", "updated_at"],
    "notes": ["id", "class_id", "subject_id", "title", "body", "link", "file_path", "file_name", "created_by", "created_at", "updated_at"],
    "fees": ["id", "student_id", "title", "amount", "due_date", "status", "paid_on", "created_by", "created_at", "updated_at"],
    "payments": ["id", "fee_id", "student_id", "amount", "utr", "status", "created_at", "updated_at"],
    "parent_contacts": ["id", "parent_name", "parent_mobile", "created_at", "updated_at"],
    "settings": ["id", "value", "created_at", "updated_at"],
}
INT_COLS = {"is_active", "is_read", "is_published", "sort_no", "duration_min"}
REAL_COLS = {"marks", "score", "total", "obtained", "max_marks", "amount"}
SYS_COLS = ("created_at", "updated_at")


def wcols(t):
    return [c for c in SCHEMA[t] if c not in SYS_COLS]


class Db:
    def __init__(self, path):
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        for t, cols in SCHEMA.items():
            defs = ["id TEXT PRIMARY KEY"] + ["%s %s" % (c, "INTEGER" if c in INT_COLS else "REAL" if c in REAL_COLS else "TEXT") for c in cols if c != "id"]
            self.con.execute("CREATE TABLE IF NOT EXISTS %s(%s)" % (t, ",".join(defs)))
            have = {r[1] for r in self.con.execute("PRAGMA table_info(%s)" % t)}
            for c in cols:
                if c not in have:
                    self.con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (t, c, "INTEGER" if c in INT_COLS else "REAL" if c in REAL_COLS else "TEXT"))
        self.con.executescript("""
        CREATE UNIQUE INDEX IF NOT EXISTS u_classes ON classes(kind,branch,year,semester,section);
        CREATE UNIQUE INDEX IF NOT EXISTS u_sess ON attendance_sessions(class_id,subject_id,date,batch);
        CREATE UNIQUE INDEX IF NOT EXISTS u_rec ON attendance_records(session_id,student_id);
        CREATE UNIQUE INDEX IF NOT EXISTS u_csub ON class_subjects(class_id,subject_id);
        CREATE UNIQUE INDEX IF NOT EXISTS u_ssub ON student_subjects(student_id,subject_id);
        CREATE UNIQUE INDEX IF NOT EXISTS u_tatt ON test_attempts(test_id,student_id);
        CREATE INDEX IF NOT EXISTS i_tq ON test_questions(test_id,sort_no);
        CREATE INDEX IF NOT EXISTS i_fee_stu ON fees(student_id,status);
        CREATE INDEX IF NOT EXISTS i_pay_stu ON payments(student_id,status);
        CREATE INDEX IF NOT EXISTS i_marks_stu ON marks(student_id,exam_date);
        CREATE INDEX IF NOT EXISTS i_stu_class ON students(class_id,batch);
        CREATE INDEX IF NOT EXISTS i_rec_stu ON attendance_records(student_id,status);
        CREATE INDEX IF NOT EXISTS i_sess_date ON attendance_sessions(date);
        CREATE INDEX IF NOT EXISTS i_notif ON notifications(user_id,created_at);
        CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
        CREATE TABLE IF NOT EXISTS avatars(id TEXT PRIMARY KEY, b64 TEXT);
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target TEXT, payload TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS sync_errors(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, what TEXT, err TEXT);
        """)
        self.con.commit()

    def q(self, sql, a=()):
        with self.lock:
            c = self.con.execute(sql, a)
            self.con.commit()
            return c.fetchall()

    def rows(self, sql, a=()):
        with self.lock:
            c = self.con.execute(sql, a)
            cols = [d[0] for d in c.description] if c.description else []
            r = c.fetchall()
        return [dict(zip(cols, x)) for x in r]

    def one(self, sql, a=()):
        r = self.rows(sql, a)
        return r[0] if r else None

    def kget(self, k, d=""):
        r = self.q("SELECT v FROM kv WHERE k=?", (k,))
        return r[0][0] if r else d

    def kset(self, k, v):
        self.q("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, str(v)))

    def kdel(self, k):
        self.q("DELETE FROM kv WHERE k=?", (k,))

    @staticmethod
    def _v(v):
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (dict, list)):
            return json.dumps(v)
        return v

    def put(self, t, rows):
        """Insert or replace rows unconditionally."""
        if not rows:
            return
        cols = SCHEMA[t]
        with self.lock:
            self.con.executemany("INSERT OR REPLACE INTO %s(%s) VALUES(%s)" % (t, ",".join(cols), ",".join("?" * len(cols))),
                                 [tuple(self._v(r.get(c)) for c in cols) for r in rows])
            self.con.commit()

    def put_new(self, t, rows):
        """Insert/replace only rows whose updated_at differs from local copy. Returns number of changed rows."""
        if not rows:
            return 0
        have, ids = {}, [r["id"] for r in rows]
        with self.lock:
            for i in range(0, len(ids), 400):
                ch = ids[i:i + 400]
                for rid, ua in self.con.execute("SELECT id,updated_at FROM %s WHERE id IN (%s)" % (t, ",".join("?" * len(ch))), ch):
                    have[rid] = ua
        todo = [r for r in rows if have.get(r["id"]) != r.get("updated_at")]
        self.put(t, todo)
        return len(todo)

    def delete_ids(self, t, ids):
        ids = list(ids)
        with self.lock:
            for i in range(0, len(ids), 400):
                ch = ids[i:i + 400]
                self.con.execute("DELETE FROM %s WHERE id IN (%s)" % (t, ",".join("?" * len(ch))), ch)
            self.con.commit()

    def wipe(self):
        with self.lock:
            for t in SCHEMA:
                self.con.execute("DELETE FROM " + t)
            self.con.execute("DELETE FROM avatars")
            self.con.execute("DELETE FROM outbox")
            self.con.execute("DELETE FROM sync_errors")
            self.con.execute("DELETE FROM kv WHERE k LIKE 'cur:%'")
            self.con.commit()

    def enqueue(self, kind, target, payload):
        self.q("INSERT INTO outbox(kind,target,payload,created) VALUES(?,?,?,?)", (kind, target, json.dumps(payload), now_iso()))

    def pending(self):
        return self.q("SELECT COUNT(*) FROM outbox")[0][0]


# ---------- Supabase REST/Auth client (no SDK, plain urllib) ----------
def make_ctx():
    """TLS context WITH certificate verification. Android Python often has no CA bundle, so try certifi, then system CAs."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    ctx = ssl.create_default_context()
    for p in ("/system/etc/security/cacerts", "/apex/com.android.conscrypt/cacerts"):
        try:
            if os.path.isdir(p):
                ctx.load_verify_locations(capath=p)
                break
        except Exception:
            pass
    return ctx


CTX = make_ctx()


class Api:
    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()
        self.sess = None
        try:
            s = db.kget("session")
            self.sess = json.loads(s) if s else None
        except Exception:
            self.sess = None

    # ----- low level -----
    def _req(self, method, path, body=None, token=None, headers=None, timeout=20):
        h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        h.update(headers or {})
        data = None if body is None else json.dumps(body).encode("utf-8")
        for attempt in range(3):
            try:
                return self._send(method, path, data, h, timeout)
            except urllib.error.HTTPError:
                raise
            except urllib.error.URLError as e:
                if attempt < 2 and isinstance(e.reason, (ConnectionRefusedError, socket.gaierror)):
                    time.sleep(1.0 + attempt)
                    continue
                raise NetError(str(e))
            except (OSError, socket.timeout, ssl.SSLError) as e:
                raise NetError(str(e))

    def _send(self, method, path, data, h, timeout):
        req = urllib.request.Request(SUPABASE_URL + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                txt = r.read().decode("utf-8")
                return (json.loads(txt) if txt else None), r.headers
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(raw)
            except Exception:
                j = {}
            if not isinstance(j, dict):
                j = {}
            m = j.get("message") or j.get("msg") or j.get("error_description") or j.get("error") or raw[:200]
            raise ApiError(e.code, str(m), str(j.get("code") or j.get("error_code") or ""))
        except ValueError as e:
            raise ApiError(0, "Bad response from server: %s" % e)

    # ----- session -----
    def save(self, s):
        self.sess = s
        if s:
            self.db.kset("session", json.dumps(s))
        else:
            self.db.kdel("session")

    def store(self, d):
        u = d.get("user") or {}
        self.save({"access_token": d["access_token"], "refresh_token": d.get("refresh_token", ""),
                   "expires_at": time.time() + int(d.get("expires_in", 3600)), "user_id": u.get("id", ""), "email": u.get("email", "")})

    def refresh(self):
        s = self.sess
        if not s or not s.get("refresh_token"):
            self.save(None)
            raise ApiError(401, "Session expired. Please login again.", "session_expired")
        try:
            d, _ = self._req("POST", "/auth/v1/token?grant_type=refresh_token", {"refresh_token": s["refresh_token"]})
        except ApiError as e:
            if e.status in (400, 401, 403):
                self.save(None)
                raise ApiError(401, "Session expired. Please login again.", "session_expired")
            raise
        self.store(d)

    def token(self):
        with self.lock:
            if not self.sess:
                raise ApiError(401, "Please login first.", "session_expired")
            if self.sess["expires_at"] - time.time() < 90:
                self.refresh()
            return self.sess["access_token"]

    def rest(self, method, path, body=None, headers=None):
        """Authenticated request to /rest/v1/... Returns (data, response_headers)."""
        for attempt in (0, 1):
            tok = self.token()
            try:
                return self._req(method, path, body, tok, headers)
            except ApiError as e:
                if e.status == 401 and attempt == 0:
                    with self.lock:
                        self.refresh()
                    continue
                if e.status == 401:
                    self.save(None)
                    raise ApiError(401, "Session expired. Please login again.", "session_expired")
                raise

    def rpc(self, fn, args):
        return self.rest("POST", "/rest/v1/rpc/" + fn, args)[0]

    def raw(self, method, path, data=None, ctype=None, timeout=120):
        """Binary request (Supabase Storage). Returns the response bytes."""
        h = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + self.token()}
        if ctype:
            h["Content-Type"] = ctype
        req = urllib.request.Request(SUPABASE_URL + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(txt)
            except Exception:
                j = {}
            m = (j.get("message") or j.get("error") or txt[:200]) if isinstance(j, dict) else txt[:200]
            raise ApiError(e.code, str(m), str(j.get("statusCode") or "") if isinstance(j, dict) else "")
        except (urllib.error.URLError, OSError, socket.timeout, ssl.SSLError) as e:
            raise NetError(str(e))

    def storage_put(self, bucket, path, data, ctype="application/pdf"):
        self.raw("POST", "/storage/v1/object/%s/%s" % (bucket, urllib.parse.quote(path)), data, ctype)

    def storage_get(self, bucket, path):
        return self.raw("GET", "/storage/v1/object/authenticated/%s/%s" % (bucket, urllib.parse.quote(path)))

    def storage_del(self, bucket, path):
        self.raw("DELETE", "/storage/v1/object/%s/%s" % (bucket, urllib.parse.quote(path)), timeout=30)

    def rpc_anon(self, fn, args):
        return self._req("POST", "/rest/v1/rpc/" + fn, args)[0]

    # ----- auth -----
    def login(self, email, pw):
        d, _ = self._req("POST", "/auth/v1/token?grant_type=password", {"email": email.strip().lower(), "password": pw})
        self.store(d)
        return d

    def signup(self, email, pw, meta):
        d, _ = self._req("POST", "/auth/v1/signup", {"email": email.strip().lower(), "password": pw, "data": meta})
        return d or {}

    def recover(self, email):
        self._req("POST", "/auth/v1/recover", {"email": email.strip().lower()})

    def verify_recovery(self, email, token):
        d, _ = self._req("POST", "/auth/v1/verify", {"type": "recovery", "email": email.strip().lower(), "token": token.strip()})
        self.store(d)

    def set_password(self, pw):
        self.rest_auth("PUT", "/auth/v1/user", {"password": pw})

    def rest_auth(self, method, path, body):
        tok = self.token()
        return self._req(method, path, body, tok)

    def logout(self):
        try:
            if self.sess:
                self._req("POST", "/auth/v1/logout", None, self.sess["access_token"], timeout=6)
        except Exception:
            pass
        self.save(None)


# ===================== SmartHazri v4 helpers (kept, extended for Supabase) =====================
NONE_T = '(none)'
SQ = ("SELECT s.id, p.full_name, p.first_name, p.last_name, p.email, p.mobile, p.is_active, s.enrollment AS roll, s.batch, "
      "s.college_name, s.mentor_id, s.class_id, c.kind AS inst, c.branch, c.year, c.semester AS sem, c.section AS sec, c.branch AS cls "
      "FROM students s JOIN profiles p ON p.id=s.id JOIN classes c ON c.id=s.class_id")
PULL_ORDER = ["classes", "subjects", "profiles", "students", "teachers", "class_subjects", "student_subjects",
              "attendance_sessions", "attendance_records", "notifications", "leave_requests",
              "tests", "test_questions", "test_answers", "test_attempts", "marks", "notes", "fees", "payments", "parent_contacts", "settings"]


def log(e=None, where=""):
    try:
        path = os.path.join(App.get_running_app().user_data_dir, "error.log")
        if os.path.exists(path) and os.path.getsize(path) > 120000:
            os.remove(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n%s\n" % (now_iso(), where, "".join(traceback.format_exception(type(e), e, e.__traceback__)) if e else traceback.format_exc()))
    except Exception:
        pass


class Guard(ExceptionHandler):
    """Last line of defence: an unexpected error shows a message instead of closing the app."""

    def handle_exception(self, inst):
        try:
            app = App.get_running_app()
            log(inst, "guard")
            app.toast('Something went wrong: %s' % str(inst)[:80], NO)
        except Exception:
            pass
        return ExceptionManager.PASS


def fullname(u):
    return (u.get("full_name") or ("%s %s" % (u.get("first_name", ""), u.get("last_name", ""))).strip() or "?")


def bval(d):
    return d.get("branch_o", "").strip().upper() if d.get("branch") == "Other" else d.get("branch", "")


def cname(d):
    c = str(d.get("cls") or "")
    return c if c.startswith("Class") else "Class " + c


def glabel(d):
    s = "%s | %s Year" % (bval(d), d.get("year"))
    if d.get("sem") not in (None, "", "-"):
        s += " | Sem %s" % d.get("sem")
    if d.get("sec") not in (None, "", "-", "All"):
        s += " | Sec %s" % d.get("sec")
    b = d.get("batch")
    return s + ("" if not b or b == "All" else " | " + b)


def gwhere(d):
    """SQL filter on SQ (aliases s, c) for the class selected in state d. 'All' = no filter."""
    w, a = ["c.kind=?"], [d.get("inst", "college")]

    def add(col, v):
        if v and v != "All":
            w.append(col + "=?")
            a.append(v)

    if d.get("inst", "college") == "college":
        add("c.branch", bval(d))
        add("c.year", d.get("year"))
        add("c.semester", d.get("sem"))
        add("c.section", d.get("sec"))
        add("s.batch", d.get("batch"))
    else:
        add("c.branch", None if d.get("cls") == "All" else cname(d))
        add("c.section", d.get("sec"))
    return " AND ".join(w), a


def new_state():
    return dict(inst="college", branch="CSE", branch_o="", year="1st", sem="1", sec="-", batch="All", cls="1")


def all_state():
    return dict(new_state(), branch="All", year="All", sem="All", sec="All", batch="All", cls="All")


def reg_state():
    return dict(new_state(), role="student", photo_src="", email="", pw="", pw2="", name="", surname="", mobile="", roll="",
                college_name="", subject="", dept="", empid="", tcode="")


def class_fields(st, sel, rebuild):
    """Branch / Year / Semester (college only). Semester choices follow the chosen year.
    sel="all": an 'All' choice is added to every list."""
    ws = []

    def add(label, key, values, allow, cb=None):
        ws.append(lbl(label, 12, MU))
        ws.append(spin(st, key, (["All"] if allow else []) + list(values), cb))

    st["inst"] = "college"
    a_all = sel == "all"
    add("Branch", "branch", BRANCHES, a_all, rebuild)
    if st["branch"] == "Other":
        ws.append(tin(st, "branch_o", 'Enter your branch (e.g. CIVIL)'))
    add("Year", "year", YEARS, a_all, rebuild)
    add("Semester", "sem", SEM_BY_YEAR.get(st.get("year"), SEMS), a_all)
    return ws


def fld(c, st, label, key, **k):
    c.add_widget(lbl(label, 12, MU))
    c.add_widget(tin(st, key, label, **k))


# ===================== SmartHazri v6 additions =====================
# Tests (online), Marks, Notes, Fees + UPI QR, WhatsApp to parents, new dashboards.
APP_NAME = "Code Nexus"
KINDS_WA = ["Monthly report", 'Attendance only', 'Fees due only', 'Absent today']


def num(x):
    try:
        x = float(x)
    except Exception:
        return "0"
    return str(int(round(x))) if abs(x - round(x)) < 0.005 else ("%.2f" % x).rstrip("0").rstrip(".")


def money(x):
    return "Rs. " + num(x)


def pcs(a, b):
    try:
        return float(a) * 100.0 / float(b) if b else 0.0
    except Exception:
        return 0.0


def wa_number(m):
    d = re.sub(r"\D", "", m or "")
    if len(d) == 10:
        d = "91" + d
    elif len(d) == 11 and d.startswith("0"):
        d = "91" + d[1:]
    return d


def open_url(url):
    """Open a link / upi:// / wa.me link with the phone's apps. Returns True if something was launched."""
    try:
        from jnius import autoclass
        Intent, Uri = autoclass("android.content.Intent"), autoclass("android.net.Uri")
        act = autoclass("org.kivy.android.PythonActivity").mActivity
        act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        return True
    except Exception:
        pass
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


def wa_send(number, text):
    url = "https://wa.me/%s?text=%s" % (wa_number(number), urllib.parse.quote(text))
    if not open_url(url):
        msg('Could not open WhatsApp', 'WhatsApp/browser was not found on this phone.')


def upi_uri(pa, pn, amount, note):
    return "upi://pay?pa=%s&pn=%s&am=%.2f&cu=INR&tn=%s" % (urllib.parse.quote(pa, safe="@._-"), urllib.parse.quote(pn or "Code Nexus"),
                                                          float(amount), urllib.parse.quote(note or "Fees"))


def qr_matrix(text):
    try:
        import qrcode
        q = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
        q.add_data(text)
        q.make(fit=True)
        return [[bool(v) for v in r] for r in q.get_matrix()]
    except Exception as e:
        log(e, "qr")
        return []


class QRView(Widget):
    matrix = ListProperty([])

    def __init__(self, **k):
        super().__init__(**k)
        self.bind(pos=self.draw, size=self.draw, matrix=self.draw)
        Clock.schedule_once(self.draw, 0)

    def draw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(pos=self.pos, size=self.size)
            n = len(self.matrix)
            if n:
                s = max(1, int(min(self.width, self.height) / n))
                ox, oy = self.x + (self.width - s * n) / 2, self.y + (self.height - s * n) / 2
                Color(0, 0, 0, 1)
                for r, line in enumerate(self.matrix):
                    for c_, v in enumerate(line):
                        if v:
                            Rectangle(pos=(ox + c_ * s, oy + (n - 1 - r) * s), size=(s, s))


def opt_btn(text, cb, on=False):
    b = RBtn(text=text, bg=list(AC if on else GR), color=WHITE if on else TX, bold=False, halign="left", valign="middle")
    b.bind(width=lambda i, v: setattr(i, "text_size", (max(v - dp(24), 10), None)))
    b.bind(texture_size=lambda i, s: setattr(i, "height", max(dp(44), s[1] + dp(18))))
    b.bind(on_release=lambda *_: cb())
    return b


def area(st, key, hint, h=110):
    t = TextInput(hint_text=hint, text=st.get(key, ""), multiline=True, size_hint_y=None, height=dp(h), padding=[dp(12), dp(12)],
                  font_size=sp(14), write_tab=False, background_normal="", background_active="", background_color=list(IN),
                  foreground_color=TX, cursor_color=AC, hint_text_color=MU)
    t.bind(text=lambda i, v: st.__setitem__(key, v))
    return t


def fin(st, key, hint):
    t = inp(hint, st.get(key, ""))
    t.input_filter = "float"
    t.bind(text=lambda i, v: st.__setitem__(key, v))
    return t


def b64_texture(b64):
    try:
        from kivy.core.image import Image as CoreImage
        raw = base64.b64decode(b64)
        return CoreImage(io.BytesIO(raw), ext="jpg" if raw[:3] == b"\xff\xd8\xff" else "png").texture
    except Exception as e:
        log(e, "b64tex")
        return None


def month_name(ym):
    try:
        return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%B %Y")
    except Exception:
        return ym or "?"


class Extras:
    tk = None          # test in progress (student)
    tk_lbl = None
    tk_ev = None
    pdf = None         # PDF notes being viewed (student / teacher preview)
    _sec = False

    # ---------- small helpers ----------
    def S(self, name, make):
        if name not in self.__dict__:
            self.__dict__[name] = make()
        return self.__dict__[name]

    def sub_of(self, fn):
        def page(g):
            self.back_card(g)
            fn(g)
        return page

    def seg(self, g, st, key, opts, badges=None):
        """A row of toggle buttons. Only the selected section is drawn below it, so the screen stays focused."""
        r = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for o in opts:
            on = st[key] == o
            n = (badges or {}).get(o, 0)
            b = RBtn(text=o + (" (%d)" % n if n else ""), bg=list(AC if on else GR), color=WHITE if on else TX, size_hint_y=None, height=dp(42), font_size=sp(12))
            b.bind(on_release=lambda *_, o=o: (st.__setitem__(key, o), self.refresh()))
            r.add_widget(b)
        g.add_widget(r)
        return st[key]

    def set_secure(self, on):
        """Android FLAG_SECURE: blocks screenshots / screen recording and hides the app in the recent-apps preview."""
        if on == self._sec:
            return
        self._sec = on
        try:
            from jnius import autoclass
            from android.runnable import run_on_ui_thread
            LP = autoclass("android.view.WindowManager$LayoutParams")
            act = autoclass("org.kivy.android.PythonActivity").mActivity

            @run_on_ui_thread
            def f():
                w = act.getWindow()
                (w.addFlags if on else w.clearFlags)(LP.FLAG_SECURE)
            f()
        except Exception:
            pass

    def qr_b64(self, src):
        try:
            try:
                from PIL import Image as PI
                im = PI.open(src).convert("RGB")
                im.thumbnail((800, 800))
                bio = io.BytesIO()
                im.save(bio, "PNG", optimize=True)
                raw = bio.getvalue()
            except ImportError:
                raw = open(src, "rb").read()
            if len(raw) > 600000:
                return ""
            return base64.b64encode(raw).decode()
        except Exception as e:
            log(e, "qr")
            return ""

    def go_back(self):
        self.sub = None
        self.refresh()

    def setting(self, k, d=""):
        r = self.d.one("SELECT value FROM settings WHERE id=?", (k,))
        return r["value"] if r and r["value"] is not None else d

    def set_setting(self, k, v):
        ts = now_iso()
        self.d.put("settings", [dict(id=k, value=v, created_at=ts, updated_at=ts)])
        self.d.enqueue("upsert", "settings", {"id": k, "value": v})

    def payload(self, table, r):
        d = {k: r.get(k) for k in wcols(table)}
        if "is_published" in d:
            d["is_published"] = bool(d["is_published"])
        return d

    def push_rows(self, table, rows, kind="upsert"):
        self.d.put(table, rows)
        for i in range(0, len(rows), 100):
            self.d.enqueue(kind, table, [self.payload(table, r) for r in rows[i:i + 100]])

    def notify(self, uids, title, body):
        rows = [{"id": str(uuid.uuid4()), "user_id": u, "title": title, "body": body, "kind": "message", "is_read": False} for u in uids]
        for i in range(0, len(rows), 100):
            self.d.enqueue("insert", "notifications", rows[i:i + 100])

    def sub_labels(self, cls):
        return {"%s - %s" % (s["code"], s["name"]): s["id"] for s in self.subjects_for(cls["id"] if cls else None)}

    def parent(self, sid):
        return self.d.one("SELECT * FROM parent_contacts WHERE id=?", (sid,))

    def due_rows(self, sid):
        return self.rows("SELECT * FROM fees WHERE student_id=? AND status<>'paid' ORDER BY due_date", (sid,))

    def due_total(self, sid):
        return sum(float(r["amount"] or 0) for r in self.due_rows(sid))

    def new_tests(self):
        yr = self.me.get("year")
        if not yr:
            return []
        return self.rows("SELECT t.* FROM tests t LEFT JOIN classes tc ON tc.id=t.class_id WHERE t.is_published=1 AND (tc.id IS NULL OR tc.year=?) "
                         "AND t.id NOT IN (SELECT test_id FROM test_attempts WHERE student_id=?) ORDER BY t.created_at DESC", (yr, self.uid()))

    def pending_pay(self):
        return self.db("SELECT COUNT(*) FROM payments WHERE status='pending'")[0][0]

    def tab_badge(self, name, unread):
        if name == "More":
            return unread + (self.pending_leaves() if self.staff() else 0)
        if name == "Fees":
            return self.pending_pay() if self.staff() else len(self.due_rows(self.uid()))
        if name == "Tests" and not self.staff():
            return len(self.new_tests())
        return 0

    # ---------- menus ----------
    def t_more(self, g):
        self.hero(g, self.me, 'Welcome', fullname(self.me), "Menu")
        c = Card()
        c.add_widget(lbl("Menu", 17, bold=True))
        n = self.pending_leaves()
        for text, fn, kind in (("Report (attendance)", self.t_report, "ghost"), ("Marks entry (offline test)", self.t_marks, "ghost"),
                               ("Notes / Study material", self.t_notes, "ghost"), ('WhatsApp to Parents', self.t_wa, "ok"),
                               ("Setup (class / notice)", self.t_setup, "ghost"), ("Profile / Password / Settings", self.profile, "ghost")):
            c.add_widget(btn(text, lambda fn=fn: self.open_sub(self.sub_of(fn)), kind))
        c.add_widget(btn("Leave requests%s" % (" (%d pending)" % n if n else ""), lambda: self.open_sub(self.t_leaves), "warn" if n else "ghost"))
        g.add_widget(c)
        self.notif_card(g)

    def s_more(self, g):
        self.hero(g, self.me, "Welcome", fullname(self.me), "Menu")
        c = Card()
        c.add_widget(lbl("Menu", 17, bold=True))
        for text, fn in (('My Results / Monthly Record', self.s_results), ("Attendance History", self.s_history),
                         ('Apply for Leave', self.s_leave), ("Profile / Parent number / Password", self.profile)):
            c.add_widget(btn(text, lambda fn=fn: self.open_sub(self.sub_of(fn)), "ghost"))
        g.add_widget(c)
        self.notif_card(g)

    def s_extra_home(self, g):
        nt, due = len(self.new_tests()), self.due_total(self.uid())
        if not nt and not due:
            return
        c = Card()
        if nt:
            c.add_widget(row(lbl('%d new test available' % nt, 15, AC, True), small('View', lambda: self.go(1), "ghost", 76), h=38))
        if due:
            c.add_widget(row(lbl("Fees due: %s" % money(due), 15, NO, True), small("Pay", lambda: self.go(3), "warn", 76), h=38))
        g.add_widget(c)

    def t_extra_home(self, g):
        n = self.pending_pay()
        if not n:
            return
        c = Card(bg=[.95, .91, .99, 1])
        c.add_widget(lbl('%d fee payment(s) waiting for verification' % n, 15, AC, True))
        c.add_widget(btn('Open Fees tab', lambda: self.go(4)))
        g.add_widget(c)

    # ---------- parent contact + WhatsApp ----------
    def parent_card(self, g, sid):
        pc = self.parent(sid) or {}
        st = self.S("pcs", dict)
        if st.get("sid") != sid:
            st.clear()
            st.update(sid=sid, name=pc.get("parent_name") or "", mobile=pc.get("parent_mobile") or "")
        c = Card()
        c.add_widget(lbl("Parent's WhatsApp number", 16, bold=True))
        c.add_widget(lbl('Attendance, fees and marks reports will be sent to this number on WhatsApp.', 12, MU))
        fld(c, st, "Parent's name", "name")
        fld(c, st, "Parent's WhatsApp number (10 digits)", "mobile", num=True)
        c.add_widget(btn('Save parent number', lambda: self.save_parent(sid)))
        g.add_widget(c)

    def save_parent(self, sid):
        st = self.pcs
        m = st["mobile"].strip()
        if not valid_mobile(m):
            return msg('Attention', 'Enter a valid 10-digit WhatsApp number.')
        ts = now_iso()
        self.d.put("parent_contacts", [dict(id=sid, parent_name=st["name"].strip(), parent_mobile=m, created_at=ts, updated_at=ts)])
        self.d.enqueue("upsert", "parent_contacts", {"id": sid, "parent_name": st["name"].strip(), "parent_mobile": m})
        self.sync_now()
        msg("Done", 'Parent number saved.')
        self.refresh()

    def greet(self, s):
        pc = self.parent(s["id"])
        n = (pc["parent_name"] or "").strip() if pc else ""
        return 'Hello%s,' % (" " + n if n else "")

    def txt_att(self, s, d1, d2):
        p, a, l, t, pc = self.stat(s["id"], None, d1, d2)
        low = '\nAttendance is below %d%%, please take note.' % self.thr if t and pc < self.thr else ""
        return 'Attendance (%s to %s):\nPresent: %d | Absent: %d | Leave: %d (Total %d)\nPercentage: %s%s' % (d1, d2, p, a, l, t, pstr(pc, t), low)

    def txt_fee(self, s):
        rs = self.due_rows(s["id"])
        if not rs:
            return 'Fees: nothing is due.'
        lines = ["%d) %s - %s (last date %s)" % (i + 1, r["title"], money(r["amount"]), r["due_date"] or "-") for i, r in enumerate(rs)]
        upi = self.setting("upi_id")
        return "Fees due:\n%s\nTotal due: %s%s" % ("\n".join(lines), money(sum(float(r["amount"] or 0) for r in rs)), ("\nUPI: " + upi) if upi else "")

    def txt_marks(self, s, d1, d2):
        lines = []
        for t, sc, tt, d in self.db("SELECT t.title, a.score, a.total, substr(a.submitted_at,1,10) FROM test_attempts a JOIN tests t ON t.id=a.test_id "
                                    "WHERE a.student_id=? AND substr(a.submitted_at,1,10) BETWEEN ? AND ? ORDER BY 4", (s["id"], d1, d2)):
            lines.append("%s: %s/%s (%d%%)" % (t, num(sc), num(tt), pcs(sc, tt)))
        for e, ob, mx, d, sj in self.db("SELECT exam_name, obtained, max_marks, exam_date, subject_id FROM marks WHERE student_id=? AND exam_date BETWEEN ? AND ? ORDER BY 4",
                                        (s["id"], d1, d2)):
            lines.append("%s: %s/%s (%d%%)" % (e, num(ob), num(mx), pcs(ob, mx)))
        return ("Tests / Marks:\n" + "\n".join(lines)) if lines else 'Tests / Marks: no tests in this period.'

    def txt_absent(self, s, day):
        r = self.db("SELECT 1 FROM attendance_records r JOIN attendance_sessions x ON x.id=r.session_id "
                    "WHERE r.student_id=? AND x.date=? AND r.status='A' LIMIT 1", (s["id"], day))
        return ('Absent on %s.' % day) if r else ""

    def build_msg(self, s, kind, d1, d2):
        head = "%s\n*%s* (%s)\n" % (self.greet(s), fullname(s), glabel(s))
        if kind == 'Attendance only':
            body = self.txt_att(s, d1, d2)
        elif kind == 'Fees due only':
            body = self.txt_fee(s)
        elif kind == 'Absent today':
            body = self.txt_absent(s, d2)
            if not body:
                return ""
        else:
            body = "\n\n".join((self.txt_att(s, d1, d2), self.txt_marks(s, d1, d2), self.txt_fee(s)))
        return head + body + "\n\n- " + APP_NAME

    def wa_items(self, studs, kind, d1, d2):
        out = []
        for s in studs:
            pc = self.parent(s["id"])
            text = self.build_msg(s, kind, d1, d2)
            if text:
                out.append((fullname(s), wa_number(pc["parent_mobile"]) if pc and pc["parent_mobile"] else "", text))
        return out

    def wa_one(self, s, kind="Monthly report"):
        d1, d2 = today()[:8] + "01", today()
        it = self.wa_items([s], kind, d1, d2)
        if not it or not it[0][1]:
            return msg('No number', "Save the parent's WhatsApp number first.")
        wa_send(it[0][1], it[0][2])

    def wa_queue(self, items):
        items = [x for x in items if x[1]]
        if not items:
            return msg('No numbers', 'No student has a parent WhatsApp number saved.')
        st = {"i": 0}
        b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        info_l = lbl("", 14)
        b.add_widget(info_l)
        p = pop('Send on WhatsApp', b, 330)

        def paint():
            if st["i"] >= len(items):
                p.dismiss()
                return msg('Done', 'All messages are done.')
            n, num_, text = items[st["i"]]
            info_l.text = "%d / %d\nParent of: %s\n+%s\n\n%s" % (st["i"] + 1, len(items), n, num_, text[:110] + ("..." if len(text) > 110 else ""))

        def send():
            n, num_, text = items[st["i"]]
            st["i"] += 1
            wa_send(num_, text)
            paint()

        def skip():
            st["i"] += 1
            paint()
        b.add_widget(btn('Open WhatsApp', send, "ok"))
        b.add_widget(row(btn("Skip", skip, "muted"), btn('Close', p.dismiss, "ghost")))
        paint()
        p.open()

    def t_wa(self, g):
        wa = self.S("wa", lambda: dict(all_state(), kind=KINDS_WA[0], d1=today()[:8] + "01", d2=today()))
        c = Card()
        c.add_widget(lbl('WhatsApp Reports to Parents', 17, bold=True))
        c.add_widget(lbl('The message is ready for you. WhatsApp will open and you only need to tap Send. (First add the parent number in Students > View.)', 12, MU))
        g.add_widget(c)
        self.selector(g, 'Show list', self.refresh, st=wa, sel="all",
                      extra=lambda: [lbl('Which report?', 12, MU), spin(wa, "kind", KINDS_WA, self.refresh),
                                     lbl('Attendance / marks period', 12, MU), row(tin(wa, "d1", 'From (YYYY-MM-DD)'), tin(wa, "d2", 'To (YYYY-MM-DD)'))])
        if not (vd(wa["d1"]) and vd(wa["d2"])):
            return msg('Attention', 'Write dates in YYYY-MM-DD format.')
        studs = self.students(wa)
        items = self.wa_items(studs, wa["kind"], wa["d1"], wa["d2"])
        have = [x for x in items if x[1]]
        c = Card()
        c.add_widget(lbl('%d students  |  parent number saved for %d' % (len(items), len(have)), 14, AC, True))
        if have:
            c.add_widget(btn('Send to all, one by one (%d)' % len(have), lambda: self.wa_queue(items), "ok"))
        g.add_widget(c)
        by = {fullname(s): s for s in studs}
        for n, number, text in items[:60]:
            c = Card()
            c.add_widget(lbl(n, 15, TX, True))
            c.add_widget(lbl(text.split("\n", 2)[-1][:140], 12, MU))
            if number:
                c.add_widget(btn('Send on WhatsApp (+%s)' % number, lambda nm=number, tx=text: wa_send(nm, tx), "ok"))
            else:
                c.add_widget(lbl('No parent number saved.', 12, NO, True))
                s = by.get(n)
                if s:
                    c.add_widget(btn('Add number', lambda sid=s["id"]: self.view_student(sid), "ghost"))
            g.add_widget(c)

    def after_att_wa(self, day):
        absent = [s for s in self.studs if self.att["pend"].get(s["id"]) == "A"]
        items = [x for x in self.wa_items(absent, 'Absent today', day, day) if x[1]]
        if items:
            ask('WhatsApp to parents?', 'Send a WhatsApp message to the parents of %d absent student(s)?' % len(items), lambda: self.wa_queue(items), 'Yes', "ok")

    # ---------- student detail extras (teacher view) ----------
    def student_extra(self, g, sid, s):
        c = Card()
        c.add_widget(lbl('Marks, Tests and Fees', 16, bold=True))
        due = self.due_total(sid)
        c.add_widget(lbl(("Fees due: " + money(due)) if due else 'Fees: nothing due', 14, NO if due else OK, True))
        c.add_widget(btn('View Marks / Monthly Record', lambda: self.open_sub(self.results_page(sid, lambda: self.view_student(sid))), "ghost"))
        c.add_widget(btn('Monthly report to parent (WhatsApp)', lambda: self.wa_one(s, "Monthly report"), "ok"))
        if due:
            c.add_widget(btn('Fees reminder to parent (WhatsApp)', lambda: self.wa_one(s, 'Fees due only'), "warn"))
        g.add_widget(c)
        self.parent_card(g, sid)

    # ---------- results + monthly record ----------
    def month_rows(self, sid):
        out = {}

        def m(k):
            return out.setdefault(k, {"P": 0, "A": 0, "L": 0, "ex": []})
        for k, st, n in self.db("SELECT substr(s.date,1,7), r.status, COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                                "WHERE r.student_id=? GROUP BY 1,2", (sid,)):
            m(k)[st] = n
        for k, sc, tt in self.db("SELECT substr(submitted_at,1,7), score, total FROM test_attempts WHERE student_id=?", (sid,)):
            m(k)["ex"].append(pcs(sc, tt))
        for k, ob, mx in self.db("SELECT substr(exam_date,1,7), obtained, max_marks FROM marks WHERE student_id=?", (sid,)):
            m(k)["ex"].append(pcs(ob, mx))
        return sorted(out.items(), reverse=True)

    def s_results(self, g):
        self.results_body(g, self.uid())

    def results_page(self, sid, back):
        def page(g):
            g.add_widget(btn('< Back', back, "ghost", size_hint_y=None, height=dp(40)))
            self.results_body(g, sid)
        return page

    def results_body(self, g, sid):
        c = Card()
        c.add_widget(lbl("Monthly record", 17, bold=True))
        ms = self.month_rows(sid)
        if not ms:
            c.add_widget(lbl('No records yet.', 13, MU))
        g.add_widget(c)
        for k, v in ms[:12]:
            t = v["P"] + v["A"] + v["L"]
            pc = pcs(v["P"], t) if self.lm == "total" else pcs(v["P"], v["P"] + v["A"])
            c = Card()
            c.add_widget(lbl(month_name(k), 16, AC, True))
            c.add_widget(row(lbl("Attendance: %s" % (("%.1f%%" % pc) if t else "-"), 14, (NO if pc < self.thr else OK) if t else MU, True),
                             lbl("P %d | A %d | L %d" % (v["P"], v["A"], v["L"]), 12, MU, False, "right"), h=28))
            if v["ex"]:
                c.add_widget(lbl("Tests/Exams: %d  |  Average: %.1f%%" % (len(v["ex"]), sum(v["ex"]) / len(v["ex"])), 14, TX, True))
            else:
                c.add_widget(lbl('Tests/Exams: none this month', 13, MU))
            g.add_widget(c)
        c = Card()
        c.add_widget(lbl("Online tests", 16, bold=True))
        rs = self.rows("SELECT a.*, t.title, t.subject_id FROM test_attempts a JOIN tests t ON t.id=a.test_id WHERE a.student_id=? ORDER BY a.submitted_at DESC LIMIT 40", (sid,))
        if not rs:
            c.add_widget(lbl('No online tests taken.', 13, MU))
        for r in rs:
            c.add_widget(row(lbl("%s  (%s)" % (r["title"], (r["submitted_at"] or "")[:10]), 13, TX, True),
                             lbl("%s/%s" % (num(r["score"]), num(r["total"])), 14, OK if pcs(r["score"], r["total"]) >= 40 else NO, True, "right", 80), h=30))
        g.add_widget(c)
        c = Card()
        c.add_widget(lbl('Marks (entered by teacher)', 16, bold=True))
        rs = self.rows("SELECT * FROM marks WHERE student_id=? ORDER BY exam_date DESC LIMIT 60", (sid,))
        if not rs:
            c.add_widget(lbl('No marks entered yet.', 13, MU))
        for r in rs:
            c.add_widget(row(lbl("%s | %s" % (r["exam_name"], r["exam_date"]), 12, TX, True),
                             lbl("%s/%s" % (num(r["obtained"]), num(r["max_marks"])), 14, OK if pcs(r["obtained"], r["max_marks"]) >= 40 else NO, True, "right", 80), h=34))
        g.add_widget(c)

    # ---------- STUDENT: tests ----------
    def s_tests(self, g):
        uid = self.uid()
        if self.tk:
            c = Card(bg=[1, .96, .88, 1])
            c.add_widget(lbl('Test in progress: %s' % self.tk["test"]["title"], 15, LV, True))
            c.add_widget(btn('Back to the test', lambda: self.open_sub(self.test_page), "warn"))
            g.add_widget(c)
        c = Card()
        c.add_widget(lbl("Online Tests", 17, bold=True))
        c.add_widget(lbl('You can take a test only once. The timer does not stop once started. Keep your internet on.', 12, MU))
        g.add_widget(c)
        yr = self.me.get("year")
        ts = self.rows("SELECT t.*, (SELECT COUNT(*) FROM test_questions q WHERE q.test_id=t.id) AS nq, "
                       "(SELECT COALESCE(SUM(marks),0) FROM test_questions q WHERE q.test_id=t.id) AS tm FROM tests t "
                       "LEFT JOIN classes tc ON tc.id=t.class_id WHERE t.is_published=1 AND (tc.id IS NULL OR tc.year=?) "
                       "ORDER BY t.created_at DESC", (yr,)) if yr else []
        att = {r["test_id"]: r for r in self.rows("SELECT * FROM test_attempts WHERE student_id=?", (uid,))}
        if not ts:
            c = Card()
            c.add_widget(lbl('No tests available right now.', 14, MU))
            g.add_widget(c)
        for t in ts:
            c = Card()
            c.add_widget(lbl(t["title"], 16, TX, True))
            c.add_widget(lbl("%d questions  |  %s marks  |  %s min" % (t["nq"], num(t["tm"]), t["duration_min"] or "-"), 12, MU))
            a = att.get(t["id"])
            if a:
                p_ = pcs(a["score"], a["total"])
                c.add_widget(lbl("Score: %s / %s  (%.1f%%)" % (num(a["score"]), num(a["total"]), p_), 15, OK if p_ >= 40 else NO, True))
            elif self.d.kget("tkq:" + t["id"]):
                c.add_widget(lbl('Submitted. The result will show once you are online.', 13, LV, True))
            elif self.tk and self.tk["test"]["id"] == t["id"]:
                c.add_widget(lbl('In progress...', 13, LV, True))
            elif not t["nq"]:
                c.add_widget(lbl('Questions have not been added yet.', 13, MU))
            else:
                c.add_widget(btn('Start test', lambda tid=t["id"]: self.start_test(tid), "ok"))
            g.add_widget(c)
        c = Card()
        c.add_widget(btn('My Results / Monthly Record', lambda: self.open_sub(self.sub_of(self.s_results)), "ghost"))
        g.add_widget(c)

    def start_test(self, tid):
        t = self.d.one("SELECT * FROM tests WHERE id=?", (tid,))
        qs = self.rows("SELECT * FROM test_questions WHERE test_id=? ORDER BY sort_no, created_at", (tid,))
        if not t or not qs:
            return msg('Test not found', 'Please try again in a moment (after sync).')
        if self.tk:
            return msg('A test is already in progress', 'Submit it first.')
        if self.d.one("SELECT 1 FROM test_attempts WHERE test_id=? AND student_id=?", (tid, self.uid())):
            return msg('Already done', 'You have already taken this test.')

        def go():
            self.tk = dict(test=t, qs=qs, ans={}, end=time.time() + max(1, t["duration_min"] or 30) * 60, busy=False)
            self.tk_ev = Clock.schedule_interval(self.tk_tick, 1)
            self.open_sub(self.test_page)
        ask('Start the test?', '%s\n%d questions, %s minutes. Once started the timer will not stop and you cannot retake the test.' % (t["title"], len(qs), t["duration_min"] or 30), go, "Start", "ok")

    def tk_end(self):
        if self.tk_ev:
            self.tk_ev.cancel()
        self.tk, self.tk_ev, self.tk_lbl = None, None, None

    def tk_tick(self, *_):
        tk = self.tk
        if not tk or not self.me:
            self.tk_end()
            return False
        left = int(tk["end"] - time.time())
        if left <= 0:
            if not tk["busy"]:
                self.tk_submit(True)
            return False
        if self.tk_lbl is not None:
            self.tk_lbl.text = "Time left: %02d:%02d" % (left // 60, left % 60)
        return True

    def test_page(self, g):
        tk = self.tk
        if not tk:
            g.add_widget(btn('< Back', self.go_back, "ghost", size_hint_y=None, height=dp(40)))
            c = Card()
            c.add_widget(lbl('No test is in progress.', 14, MU))
            g.add_widget(c)
            return
        t = tk["test"]
        c = Card()
        c.add_widget(lbl(t["title"], 18, TX, True))
        c.add_widget(lbl("%d questions  |  %s marks" % (len(tk["qs"]), num(sum(q["marks"] or 0 for q in tk["qs"]))), 12, MU))
        self.tk_lbl = lbl("", 20, NO, True, "center")
        c.add_widget(self.tk_lbl)
        g.add_widget(c)
        self.tk_tick()
        self.tk_btns = {}
        for i, q in enumerate(tk["qs"]):
            c = Card()
            c.add_widget(lbl("Q%d. %s   [%s]" % (i + 1, q["question"], num(q["marks"])), 15, TX, True))
            bs = {}
            for k in "ABCD":
                txt = q["opt_" + k.lower()]
                if txt:
                    bs[k] = opt_btn("%s.  %s" % (k, txt), lambda qid=q["id"], k=k: self.tk_pick(qid, k), tk["ans"].get(q["id"]) == k)
                    c.add_widget(bs[k])
            self.tk_btns[q["id"]] = bs
            g.add_widget(c)
        g.add_widget(btn('Submit', lambda: self.tk_submit(False), "ok"))
        g.add_widget(btn('< Come back later (timer keeps running)', self.go_back, "ghost"))

    def tk_pick(self, qid, k):
        if not self.tk:
            return
        self.tk["ans"][qid] = k
        for kk, b in self.tk_btns.get(qid, {}).items():
            b.bg = list(AC if kk == k else GR)
            b.color = WHITE if kk == k else TX

    def tk_submit(self, auto=False):
        tk = self.tk
        if not tk or tk["busy"]:
            return
        miss = sum(1 for q in tk["qs"] if q["id"] not in tk["ans"])
        if miss and not auto:
            return ask('Submit test?', '%d question(s) unanswered. You cannot change answers after submitting.' % miss, lambda: self.tk_submit(True), "Submit", "ok")
        tk["busy"] = True
        t = tk["test"]
        payload = dict(p_test=t["id"], p_answers=dict(tk["ans"]))

        def ok(r):
            self.tk_end()
            r = r or {}
            ts = now_iso()
            if r.get("id"):
                self.d.put("test_attempts", [dict(id=r["id"], test_id=t["id"], student_id=self.uid(), score=r.get("score"), total=r.get("total"),
                                                  answers=payload["p_answers"], submitted_at=ts, created_at=ts, updated_at=ts)])
            self.sub = None
            self.paint_nav()
            self.refresh()
            msg('Test submitted', 'Your score: %s / %s  (%.1f%%)' % (num(r.get("score")), num(r.get("total")), pcs(r.get("score"), r.get("total"))))

        def err(e):
            self.tk_end()
            if isinstance(e, NetError) or (isinstance(e, ApiError) and e.status >= 500):
                self.d.enqueue("rpc", "submit_test", payload)
                self.d.kset("tkq:" + t["id"], "1")
                self.sub = None
                self.refresh()
                return msg('No internet', 'Your answers are saved on the phone and will be submitted automatically when internet returns.')
            self.sub = None
            self.refresh()
            msg('Not submitted', friendly(e))
        self.net(lambda: self.api.rpc("submit_test", payload), ok, 'Submitting test...', err=err)

    # ---------- TEACHER: tests ----------
    def t_tests(self, g):
        tq = self.S("tq", lambda: dict(new_state(), title="", dur="30", view="My tests"))
        if self.seg(g, tq, "view", ["My tests", "New test"]) == "New test":
            c = Card()
            c.add_widget(lbl("Create a new online test", 17, bold=True))
            c.add_widget(lbl("Choose the year. Every student of that year (all branches) will get this test.", 12, MU))
            c.add_widget(lbl("Year", 12, MU))
            c.add_widget(spin(tq, "year", YEARS))
            c.add_widget(tin(tq, "title", "Test name (e.g. Unit Test 1)"))
            c.add_widget(tin(tq, "dur", "Time (minutes)", num=True))
            c.add_widget(btn("Create test and add questions", self.make_test))
            g.add_widget(c)
            return
        rs = self.rows("SELECT t.*, c.year, (SELECT COUNT(*) FROM test_questions q WHERE q.test_id=t.id) AS nq, "
                       "(SELECT COUNT(*) FROM test_attempts a WHERE a.test_id=t.id) AS na FROM tests t JOIN classes c ON c.id=t.class_id "
                       "ORDER BY t.created_at DESC LIMIT 50")
        if not rs:
            c = Card()
            c.add_widget(lbl("No tests yet. Tap 'New test' to create one.", 14, MU))
            g.add_widget(c)
        for t in rs:
            c = Card()
            c.add_widget(row(lbl(t["title"], 15, TX, True), lbl("LIVE" if t["is_published"] else "DRAFT", 12, OK if t["is_published"] else LV, True, "right", 56), h=28))
            c.add_widget(lbl("%s Year" % t["year"], 12, MU))
            c.add_widget(lbl("%d questions  |  %d students attempted  |  %s min" % (t["nq"], t["na"], t["duration_min"] or "-"), 12, AC, True))
            c.add_widget(btn("Open / Edit / Results", lambda tid=t["id"]: self.open_sub(self.test_editor(tid)), "ghost"))
            g.add_widget(c)

    def make_test(self):
        tq = self.tq
        if not tq["title"].strip():
            return msg('Attention', 'Enter the test name.')
        self.ensure_default_subject()
        cid = self.ensure_class(dict(new_state(), branch="All", year=tq["year"], sem="-", sec="-"))   # "year class": marks the year of the test
        ts = now_iso()
        t = dict(id=str(uuid.uuid4()), class_id=cid, subject_id=DEFAULT_SUB, title=tq["title"].strip(), duration_min=int(tq["dur"] or 30) or 30,
                 is_published=0, created_by=self.uid(), created_at=ts, updated_at=ts)
        self.push_rows("tests", [t])
        tq["title"] = ""
        tq["view"] = "My tests"
        self.sync_now()
        self.open_sub(self.test_editor(t["id"]))

    def test_editor(self, tid):
        def page(g):
            self.back_card(g)
            t = self.d.one("SELECT * FROM tests WHERE id=?", (tid,))
            if not t:
                c = Card()
                c.add_widget(lbl('Test not found.', 14, MU))
                return g.add_widget(c)
            yc = self.d.one("SELECT year FROM classes WHERE id=?", (t["class_id"],))
            year = yc["year"] if yc else "-"
            qf = self.S("qf", lambda: dict(q="", a="", b="", c="", d="", corr="A", marks="1", bulk="", mode="One question"))
            qs = self.rows("SELECT q.*, a.correct FROM test_questions q LEFT JOIN test_answers a ON a.id=q.id WHERE q.test_id=? ORDER BY q.sort_no, q.created_at", (tid,))
            c = Card()
            c.add_widget(lbl(t["title"], 18, TX, True))
            c.add_widget(lbl("%s Year  |  %s min  |  %d questions  |  %s marks" % (year, t["duration_min"], len(qs), num(sum(q["marks"] or 0 for q in qs))), 12, MU))
            c.add_widget(lbl("Status: " + ('LIVE (visible to students)' if t["is_published"] else 'DRAFT (not visible to students)'), 13, OK if t["is_published"] else LV, True))
            c.add_widget(btn('Unpublish' if t["is_published"] else 'Publish (send to students)', lambda: self.toggle_test(t), "warn" if t["is_published"] else "ok"))
            c.add_widget(btn('Delete test', lambda: self.del_test(t), "danger"))
            g.add_widget(c)
            if self.seg(g, qf, "mode", ["One question", "Bulk (many questions)"]) == "One question":
                c = Card()
                c.add_widget(lbl('Add a new question', 16, bold=True))
                c.add_widget(area(qf, "q", 'Write the question', 80))
                for k in "abcd":
                    c.add_widget(tin(qf, k, "Option %s" % k.upper()))
                c.add_widget(lbl('Correct answer', 12, MU))
                c.add_widget(spin(qf, "corr", ["A", "B", "C", "D"]))
                c.add_widget(fin(qf, "marks", 'Marks (e.g. 1)'))
                c.add_widget(btn('+ Add question', lambda: self.add_q(tid)))
                g.add_widget(c)
            else:
                c = Card()
                c.add_widget(lbl('Add many questions at once', 16, bold=True))
                c.add_widget(lbl('One question per line. Separate the parts with the | sign:\nquestion | A | B | C | D | correct (A/B/C/D) | marks (optional)', 12, MU))
                c.add_widget(lbl('Example:\n2+2=? | 3 | 4 | 5 | 6 | B | 1\nCapital of India? | Delhi | Mumbai | Pune | Goa | A | 2', 12, AC))
                c.add_widget(area(qf, "bulk", 'Paste all your questions here (one per line)', 240))
                c.add_widget(btn('Load questions from a .txt file', lambda: self.pick_file('Choose .txt file', ["*.txt", "*.TXT"], self.bulk_from_file), "ghost"))
                c.add_widget(btn('Add all questions', lambda: self.bulk_add(tid), "ok"))
                g.add_widget(c)
            for i, q in enumerate(qs):
                c = Card()
                c.add_widget(lbl("Q%d. %s  [%s]" % (i + 1, q["question"], num(q["marks"])), 14, TX, True))
                for k in "abcd":
                    if q["opt_" + k]:
                        c.add_widget(lbl("%s. %s" % (k.upper(), q["opt_" + k]), 13, OK if (q["correct"] or "").lower() == k else MU, (q["correct"] or "").lower() == k))
                c.add_widget(small('Remove', lambda x=q["id"]: self.del_q(x), "plaindanger", 80, height=dp(34)))
                g.add_widget(c)
            at = self.rows("SELECT a.*, p.full_name, s.enrollment AS roll FROM test_attempts a JOIN profiles p ON p.id=a.student_id JOIN students s ON s.id=a.student_id "
                           "WHERE a.test_id=? ORDER BY a.score DESC", (tid,))
            tot = self.db("SELECT COUNT(*) FROM students s JOIN classes c ON c.id=s.class_id WHERE c.year=?", (year,))[0][0]
            c = Card()
            c.add_widget(lbl('Results (%d / %d students attempted)' % (len(at), tot), 16, bold=True))
            if not at:
                c.add_widget(lbl('Nobody has taken this test yet.', 13, MU))
            for a in at:
                c.add_widget(row(lbl("%s  %s" % (a["roll"], a["full_name"]), 13, TX, True),
                                 lbl("%s/%s (%d%%)" % (num(a["score"]), num(a["total"]), pcs(a["score"], a["total"])), 13, OK if pcs(a["score"], a["total"]) >= 40 else NO, True, "right", 120), h=30))
            if at:
                items = []
                for a in at:
                    s = self.d.one(SQ + " WHERE s.id=?", (a["student_id"],))
                    pc = self.parent(a["student_id"])
                    if s:
                        items.append((fullname(s), wa_number(pc["parent_mobile"]) if pc and pc["parent_mobile"] else "",
                                      "%s\n*%s*\nTest: %s\nScore: %s / %s (%d%%)\n\n- %s" % (self.greet(s), fullname(s), t["title"], num(a["score"]), num(a["total"]),
                                                                                         pcs(a["score"], a["total"]), APP_NAME)))
                c.add_widget(btn('Send results to parents on WhatsApp', lambda: self.wa_queue(items), "ok"))
            g.add_widget(c)
        return page

    def bulk_from_file(self, path):
        try:
            with open(path, "rb") as fh:
                txt = fh.read().decode("utf-8-sig", "replace")
        except Exception as e:
            log(e, "bulkfile")
            return msg("Cannot read file", "Choose the .txt file again.")
        qf = self.qf
        qf["bulk"] = (qf["bulk"].rstrip() + "\n" if qf["bulk"].strip() else "") + txt.strip()
        self.refresh()

    def put_question(self, tid, q, opts, corr, marks):
        ts = now_iso()
        n = (self.db("SELECT COALESCE(MAX(sort_no),0) FROM test_questions WHERE test_id=?", (tid,))[0][0] or 0) + 1
        r = dict(id=str(uuid.uuid4()), test_id=tid, sort_no=n, question=q, opt_a=opts[0], opt_b=opts[1], opt_c=opts[2], opt_d=opts[3], marks=marks, created_at=ts, updated_at=ts)
        a = dict(id=r["id"], correct=corr, created_at=ts, updated_at=ts)
        self.push_rows("test_questions", [r])
        self.push_rows("test_answers", [a])

    def add_q(self, tid):
        qf = self.qf
        opts = [qf["a"].strip(), qf["b"].strip(), qf["c"].strip(), qf["d"].strip()]
        try:
            mk = float(qf["marks"] or 1)
        except Exception:
            mk = 0
        if not qf["q"].strip() or sum(1 for o in opts if o) < 2 or mk <= 0:
            return msg('Attention', 'Enter the question, at least 2 options and valid marks.')
        if not opts["ABCD".index(qf["corr"])]:
            return msg('Attention', 'The option marked correct is empty.')
        self.put_question(tid, qf["q"].strip(), opts, qf["corr"], mk)
        qf.update(q="", a="", b="", c="", d="")
        self.sync_now()
        self.refresh()

    def bulk_add(self, tid):
        qf, n, bad = self.qf, 0, []
        for i, ln in enumerate(qf["bulk"].splitlines(), 1):
            if not ln.strip():
                continue
            p = [x.strip() for x in ln.split("|")]
            corr = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(p[5], p[5].upper()) if len(p) > 5 else ""
            try:
                mk = float(p[6]) if len(p) > 6 and p[6] else 1.0
            except Exception:
                mk = 0
            if len(p) < 6 or not p[0] or corr not in ("A", "B", "C", "D") or not p["ABCD".index(corr) + 1] or mk <= 0:
                bad.append(i)
                continue
            self.put_question(tid, p[0], p[1:5], corr, mk)
            n += 1
        if n:
            qf["bulk"] = ""
            self.sync_now()
        self.refresh()
        msg('Done' if not bad else 'Some lines were invalid', '%d question(s) added.%s' % (n, ('\nInvalid lines: ' + ", ".join(map(str, bad[:15]))) if bad else ""))

    def del_q(self, qid):
        self.d.delete_ids("test_answers", [qid])
        self.d.delete_ids("test_questions", [qid])
        self.d.enqueue("delete", "test_questions", {"q": "id=eq." + qid})
        self.sync_now()
        self.refresh()

    def toggle_test(self, t):
        on = not t["is_published"]
        if on and not self.db("SELECT COUNT(*) FROM test_questions WHERE test_id=?", (t["id"],))[0][0]:
            return msg('No questions', 'Add at least 1 question before publishing.')
        self.db("UPDATE tests SET is_published=?,updated_at=? WHERE id=?", (int(on), now_iso(), t["id"]))
        self.d.enqueue("patch", "tests", {"q": "id=eq." + t["id"], "values": {"is_published": on}})
        if on:
            yc = self.d.one("SELECT year FROM classes WHERE id=?", (t["class_id"],))
            ids = [r[0] for r in self.db("SELECT s.id FROM students s JOIN classes c ON c.id=s.class_id WHERE c.year=?", (yc["year"],))] if yc else []
            self.notify(ids, 'New test: ' + t["title"], 'A new test is available. Open the Tests tab to take it.')
        self.sync_now()
        self.refresh()

    def del_test(self, t):
        def go():
            qids = [r[0] for r in self.db("SELECT id FROM test_questions WHERE test_id=?", (t["id"],))]
            self.d.delete_ids("test_answers", qids)
            self.d.delete_ids("test_questions", qids)
            self.d.delete_ids("test_attempts", [r[0] for r in self.db("SELECT id FROM test_attempts WHERE test_id=?", (t["id"],))])
            self.d.delete_ids("tests", [t["id"]])
            self.d.enqueue("delete", "tests", {"q": "id=eq." + t["id"]})
            self.sync_now()
            self.go_back()
        ask("Test delete?", 'The test, its questions and all student results will be deleted.', go, "Delete")

    # ---------- TEACHER: marks entry (offline / paper tests) ----------
    def t_marks(self, g):
        mk = self.S("mk6", lambda: dict(all_state(), exam="", date=today(), max="", load=False, vals={}))
        c = Card()
        c.add_widget(lbl("Marks entry", 17, bold=True))
        c.add_widget(lbl('Enter marks for paper tests / unit tests / monthly tests here. Students and parents will see them.', 12, MU))
        g.add_widget(c)
        self.selector(g, 'Load students', self.mk_load, st=mk, sel="all",
                      extra=lambda: [tin(mk, "exam", 'Exam name (e.g. Unit Test 1)'),
                                     row(tin(mk, "date", "Date YYYY-MM-DD"), fin(mk, "max", "Max marks"))])
        if not mk["load"]:
            return
        studs = self.students(mk)
        c = Card()
        c.add_widget(lbl("%s  |  Max %s" % (mk["exam"], mk["max"]), 14, AC, True))
        g.add_widget(c)
        for s in studs[:120]:
            r = row(lbl("%s  %s" % (s["roll"], fullname(s)), 13, TX, True), h=46)
            t = inp("Marks", mk["vals"].get(s["id"], ""))
            t.input_filter = "float"
            t.size_hint_x = None
            t.width = dp(90)
            t.bind(text=lambda i, v, sid=s["id"]: mk["vals"].__setitem__(sid, v))
            r.add_widget(t)
            g.add_widget(r)
        g.add_widget(btn('Save marks', lambda: self.mk_save(studs), "ok"))

    def mk_load(self):
        mk = self.mk6
        if not mk["exam"].strip() or not vd(mk["date"]):
            return msg('Attention', 'Enter an exam name and a valid date.')
        mk["vals"] = {}
        for s in self.students(mk):
            r = self.d.one("SELECT obtained FROM marks WHERE id=?", (self.mk_id(s["id"], DEFAULT_SUB, mk["exam"]),))
            if r:
                mk["vals"][s["id"]] = num(r["obtained"])
        mk["load"] = True
        self.refresh()

    def mk_id(self, sid, sub, exam):
        return str(uuid.uuid5(NS, "mk|%s|%s|%s" % (sid, sub, exam.strip().lower())))

    def mk_save(self, studs):
        mk = self.mk6
        try:
            mx = float(mk["max"])
        except Exception:
            mx = 0
        if mx <= 0 or not mk["exam"].strip() or not vd(mk["date"]):
            return msg('Attention', 'Enter a valid exam name, date and max marks.')
        self.ensure_default_subject()
        ts, rows, bad = now_iso(), [], 0
        for s in studs:
            v = (mk["vals"].get(s["id"]) or "").strip()
            if not v:
                continue
            try:
                ob = float(v)
            except Exception:
                ob = -1
            if ob < 0 or ob > mx:
                bad += 1
                continue
            rows.append(dict(id=self.mk_id(s["id"], DEFAULT_SUB, mk["exam"]), student_id=s["id"], subject_id=DEFAULT_SUB, exam_name=mk["exam"].strip(), exam_date=mk["date"],
                             obtained=ob, max_marks=mx, entered_by=self.uid(), created_at=ts, updated_at=ts))
        if bad:
            return msg('Invalid marks', '%d student(s) have marks above the max marks or invalid marks. Fix them and save again.' % bad)
        if not rows:
            return msg('Nothing entered', 'No marks were entered for any student.')
        self.push_rows("marks", rows)
        self.sync_now()
        msg('Saved', 'Marks saved for %d student(s).' % len(rows))

    # ---------- notes ----------
    def t_notes(self, g):
        nn = self.S("nn", lambda: dict(new_state(), title="", link="", file="", view="Uploaded"))
        if self.seg(g, nn, "view", ["Uploaded", "Upload new"]) == "Upload new":
            c = Card()
            c.add_widget(lbl("Upload PDF notes", 17, bold=True))
            c.add_widget(lbl("Students can only read the PDF inside this app. They cannot download it or take a screenshot of it.", 12, MU))
            for w in class_fields(nn, False, self.refresh):
                c.add_widget(w)
            c.add_widget(tin(nn, "title", "Chapter / Topic name"))
            c.add_widget(lbl((("Selected: " + os.path.basename(nn["file"])) if nn["file"] else "No PDF selected"), 13, OK if nn["file"] else MU, True))
            c.add_widget(btn("Choose PDF file", lambda: self.pick_file("Choose PDF", ["*.pdf", "*.PDF"], lambda p: (nn.__setitem__("file", p), self.refresh())), "ghost"))
            c.add_widget(tin(nn, "link", "Video link (YouTube / Drive) - optional"))
            c.add_widget(btn("Upload and publish", self.add_note, "ok"))
            g.add_widget(c)
            return
        rs = self.rows("SELECT n.*, c.kind, c.branch, c.year, c.semester, c.section FROM notes n JOIN classes c ON c.id=n.class_id ORDER BY n.created_at DESC LIMIT 60")
        if not rs:
            c = Card()
            c.add_widget(lbl("No notes uploaded yet. Tap 'Upload new'.", 14, MU))
            g.add_widget(c)
        for n in rs:
            c = Card()
            c.add_widget(lbl(n["title"], 15, TX, True))
            c.add_widget(lbl(class_label(dict(n, semester=n["semester"])), 12, MU))
            if n["file_name"]:
                c.add_widget(lbl("PDF: %s" % n["file_name"], 12, AC, True))
            if n["link"]:
                c.add_widget(lbl(n["link"], 12, AC))
            bs = []
            if n["file_path"]:
                bs.append(btn("Preview", lambda x=n: self.open_pdf(x), "ghost"))
            bs.append(btn("Remove", lambda x=n: self.del_note(x), "danger"))
            c.add_widget(row(*bs))
            g.add_widget(c)

    def add_note(self):
        nn = self.nn
        link, path = nn["link"].strip(), nn["file"]
        if not nn["title"].strip() or not (path or link):
            return msg("Attention", "Enter a topic name and select a PDF (or add a video link).")
        if link and not link.lower().startswith(("http://", "https://")):
            return msg("Attention", "The link must start with http:// or https://")
        if nn["branch"] == "Other" and not nn["branch_o"].strip():
            return msg("Attention", "Enter your branch name.")
        data = b""
        if path:
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except Exception:
                return msg("Cannot read file", "Choose the PDF again and allow storage permission.")
            if not data.startswith(b"%PDF"):
                return msg("Not a PDF", "Please choose a valid PDF file.")
            if len(data) > 15 * 1024 * 1024:
                return msg("File too large", "The PDF must be under 15 MB.")
        self.ensure_default_subject()
        cid = self.ensure_class(nn)
        obj = "%s/%s.pdf" % (cid, uuid.uuid4()) if data else ""

        def publish(_=None):
            ts = now_iso()
            r = dict(id=str(uuid.uuid4()), class_id=cid, subject_id=DEFAULT_SUB, title=nn["title"].strip(), body="", link=link, file_path=obj,
                     file_name=os.path.basename(path) if path else "", created_by=self.uid(), created_at=ts, updated_at=ts)
            self.push_rows("notes", [r])
            self.notify([x[0] for x in self.db("SELECT id FROM students WHERE class_id=?", (cid,))], "New notes: " + r["title"], "New notes have been uploaded.")
            nn.update(title="", link="", file="", view="Uploaded")
            self.sync_now()
            self.refresh()
            msg("Published", "Notes published. Students of this class can read them in the Notes tab.")
        if data:
            self.net(lambda: self.api.storage_put("notes", obj, data), publish, "Uploading PDF...")
        else:
            publish()

    def del_note(self, n):
        def go():
            self.d.delete_ids("notes", [n["id"]])
            self.d.enqueue("delete", "notes", {"q": "id=eq." + n["id"]})
            if n["file_path"]:
                self.net(lambda: self.api.storage_del("notes", n["file_path"]), lambda r: None, "", err=lambda e: log(e, "notefile"))
            self.sync_now()
            self.refresh()
        ask("Remove notes?", "These notes will be removed for all students.", go, "Remove")

    def s_notes(self, g):
        cid = self.me.get("class_id")
        rs = self.rows("SELECT * FROM notes WHERE class_id=? ORDER BY created_at DESC", (cid,)) if cid else []
        if not rs:
            c = Card()
            c.add_widget(lbl("No notes uploaded yet.", 14, MU))
            g.add_widget(c)
        for r in rs:
            c = Card()
            c.add_widget(lbl(r["title"], 16, TX, True))
            c.add_widget(lbl((r["created_at"] or "")[:10], 12, MU))
            if r["file_path"]:
                c.add_widget(btn("Read notes (PDF)", lambda x=r: self.open_pdf(x), "ok"))
            if r["link"]:
                c.add_widget(btn("Open video / link", lambda u=r["link"]: open_url(u) or msg("Could not open the link", u), "ghost"))
            g.add_widget(c)

    # ---------- protected PDF viewer (in-app only, screenshots blocked) ----------
    def open_pdf(self, n):
        try:
            import jnius  # noqa: F401  (only exists inside the Android app)
        except Exception:
            return msg("Android only", "PDF notes can be read inside the Android app only.")
        cache = os.path.join(self.user_data_dir, "pdfcache")
        os.makedirs(cache, exist_ok=True)
        path = os.path.join(cache, n["id"] + ".tmp")

        def done(data):
            with open(path, "wb") as fh:
                fh.write(data)
            self.pdf_start(path, n)
        self.net(lambda: self.api.storage_get("notes", n["file_path"]), done, "Opening notes...")

    def pdf_start(self, path, n):
        self.pdf_close()
        try:
            from jnius import autoclass
            File, PFD, PR = autoclass("java.io.File"), autoclass("android.os.ParcelFileDescriptor"), autoclass("android.graphics.pdf.PdfRenderer")
            fd = PFD.open(File(path), PFD.MODE_READ_ONLY)
            r = PR(fd)
        except Exception as e:
            log(e, "pdf")
            try:
                os.remove(path)
            except Exception:
                pass
            return msg("Cannot open", "This PDF could not be opened on this phone.")
        self.pdf = dict(path=path, fd=fd, r=r, n=r.getPageCount(), i=0, note=n)
        self.open_sub(self.pdf_page)

    def pdf_close(self):
        p, self.pdf = self.pdf, None
        if not p:
            return
        for k in ("r", "fd"):
            try:
                p[k].close()
            except Exception:
                pass
        try:
            os.remove(p["path"])
        except Exception:
            pass

    def pdf_render(self, i):
        from jnius import autoclass
        Bitmap, Config = autoclass("android.graphics.Bitmap"), autoclass("android.graphics.Bitmap$Config")
        CF, BAOS = autoclass("android.graphics.Bitmap$CompressFormat"), autoclass("java.io.ByteArrayOutputStream")
        Color, Page = autoclass("android.graphics.Color"), autoclass("android.graphics.pdf.PdfRenderer$Page")
        pg = self.pdf["r"].openPage(i)
        try:
            w = int(max(700, min(1600, Window.width * 1.4)))
            h = max(1, int(w * pg.getHeight() / max(1, pg.getWidth())))
            bmp = Bitmap.createBitmap(w, h, Config.ARGB_8888)
            bmp.eraseColor(Color.WHITE)
            pg.render(bmp, None, None, Page.RENDER_MODE_FOR_DISPLAY)
        finally:
            pg.close()
        bos = BAOS()
        bmp.compress(CF.JPEG, 88, bos)
        data = bytes(bytearray(b & 0xFF for b in bos.toByteArray()))
        bmp.recycle()
        return data, w, h

    def pdf_flip(self, d):
        p = self.pdf
        if p:
            p["i"] = max(0, min(p["n"] - 1, p["i"] + d))
            self.refresh()

    def pdf_page(self, g):
        p = self.pdf
        if not p:
            return g.add_widget(btn("< Back", self.go_back, "ghost", size_hint_y=None, height=dp(40)))
        c = Card()
        c.add_widget(lbl(p["note"]["title"], 16, TX, True))
        c.add_widget(row(btn("< Close", self.go_back, "muted"), btn("< Prev", lambda: self.pdf_flip(-1), "ghost"),
                         lbl("%d / %d" % (p["i"] + 1, p["n"]), 14, AC, True, "center"), btn("Next >", lambda: self.pdf_flip(1), "ghost")))
        g.add_widget(c)
        try:
            data, w, h = self.pdf_render(p["i"])
            tex = b64_texture(base64.b64encode(data).decode())
            g.add_widget(Image(texture=tex, size_hint=(1, None), height=(Window.width - dp(16)) * h / w))
        except Exception as e:
            log(e, "pdfpage")
            c = Card()
            c.add_widget(lbl("This page could not be shown.", 14, NO, True))
            g.add_widget(c)
        g.add_widget(row(btn("< Prev", lambda: self.pdf_flip(-1), "ghost"), btn("Next >", lambda: self.pdf_flip(1), "ghost")))

    def t_fees(self, g):
        fs = self.S("fs", lambda: dict(all_state(), title="", amount="", due=today(), flt="Due", upi="", upn="", loaded=False, view="Due list"))
        if not fs["loaded"]:
            fs.update(upi=self.setting("upi_id"), upn=self.setting("upi_name"), loaded=True)
        view = self.seg(g, fs, "view", ["Due list", "Verify", "Add fees", "UPI & QR"], {"Verify": self.pending_pay()})
        if view == "Verify":
            pend = self.rows("SELECT y.*, f.title, p.full_name FROM payments y JOIN fees f ON f.id=y.fee_id JOIN profiles p ON p.id=y.student_id WHERE y.status='pending' ORDER BY y.created_at")
            c = Card()
            c.add_widget(lbl("Waiting for verification (%d)" % len(pend), 16, AC, True))
            c.add_widget(lbl("Check the payment in your UPI/bank app. If the UTR matches, tap Verify.", 12, MU))
            g.add_widget(c)
            for y in pend:
                c = Card()
                c.add_widget(lbl("%s  -  %s" % (y["full_name"], y["title"]), 15, TX, True))
                c.add_widget(lbl("%s   |   UTR: %s   |   %s" % (money(y["amount"]), y["utr"], (y["created_at"] or "")[:10]), 13, AC, True))
                c.add_widget(row(btn("Verify (received)", lambda i=y["id"]: self.pay_decide(i, True), "ok"), btn("Reject", lambda i=y["id"]: self.pay_decide(i, False), "danger")))
                g.add_widget(c)
            return
        if view == "Add fees":
            self.selector(g, "Add fees for this class", self.make_fees, st=fs, sel="all",
                          extra=lambda: [lbl("New fees (for all students of the class/filter selected above)", 12, MU), tin(fs, "title", "Fee name (e.g. October Fees)"),
                                         fin(fs, "amount", "Amount (Rs.)"), tin(fs, "due", "Last date YYYY-MM-DD")])
            return
        if view == "UPI & QR":
            qr = self.setting("upi_qr")
            c = Card()
            c.add_widget(lbl("Payment QR code", 17, bold=True))
            c.add_widget(lbl("Upload your UPI QR image once. Every student will see it on the payment screen.", 12, MU))
            tex = b64_texture(qr) if qr else None
            if tex:
                c.add_widget(Image(texture=tex, size_hint=(1, None), height=min(dp(300), (Window.width - dp(60)) * tex.height / max(1, tex.width))))
            else:
                c.add_widget(lbl("No QR uploaded yet.", 13, MU))
            c.add_widget(btn("Change QR image" if tex else "Upload QR image", self.pick_qr, "ok"))
            if tex:
                c.add_widget(btn("Remove QR", self.rm_qr, "danger"))
            g.add_widget(c)
            c = Card()
            c.add_widget(lbl("UPI ID (optional)", 16, bold=True))
            c.add_widget(lbl("Needed for the 'Open UPI app' button and for an auto-made QR with the amount filled in.", 12, MU))
            c.add_widget(tin(fs, "upi", "UPI ID (e.g. club@okaxis)"))
            c.add_widget(tin(fs, "upn", "Name (club / teacher)"))
            c.add_widget(btn("Save UPI", self.save_upi))
            g.add_widget(c)
            return
        tot, got = self.db("SELECT COALESCE(SUM(amount),0), COALESCE(SUM(CASE WHEN status='paid' THEN amount ELSE 0 END),0) FROM fees")[0]
        c = Card()
        c.add_widget(row(lbl("Total\n" + money(tot), 13, TX, True), lbl("Received\n" + money(got), 13, OK, True), lbl("Pending\n" + money(tot - got), 13, NO, True), h=48))
        c.add_widget(spin(fs, "flt", ["Due", "Paid", "All"], self.refresh))
        g.add_widget(c)
        w, a = gwhere(fs)
        sql = ("SELECT f.*, p.full_name, s.enrollment AS roll FROM fees f JOIN students s ON s.id=f.student_id JOIN profiles p ON p.id=f.student_id "
               "JOIN classes c ON c.id=s.class_id WHERE " + w)
        if fs["flt"] == "Due":
            sql += " AND f.status<>'paid'"
        elif fs["flt"] == "Paid":
            sql += " AND f.status='paid'"
        rs = self.rows(sql + " ORDER BY f.due_date, p.full_name LIMIT 80", a)
        if not rs:
            c = Card()
            c.add_widget(lbl("No fee records.", 13, MU))
            g.add_widget(c)
        for f in rs:
            paid = f["status"] == "paid"
            c = Card()
            c.add_widget(row(lbl("%s  %s" % (f["roll"], f["full_name"]), 14, TX, True), lbl("PAID" if paid else "DUE", 13, OK if paid else NO, True, "right", 56), h=28))
            c.add_widget(lbl("%s  |  %s  |  last date %s" % (f["title"], money(f["amount"]), f["due_date"] or "-"), 12, MU))
            if not paid:
                s = self.d.one(SQ + " WHERE s.id=?", (f["student_id"],))
                c.add_widget(row(btn("Cash received", lambda i=f["id"]: self.fee_cash(i), "ok"),
                                 btn("WhatsApp reminder", lambda x=s: self.wa_one(x, "Fees due only"), "warn") if s else Widget()))
            else:
                c.add_widget(lbl("Paid on %s" % (f["paid_on"] or "-"), 12, OK))
            g.add_widget(c)

    def save_upi(self):
        fs = self.fs
        u = fs["upi"].strip()
        if u and not re.fullmatch(r"[\w.\-]{2,}@[A-Za-z]{2,}", u):
            return msg("Attention", "Enter a valid UPI ID (e.g. name@okaxis).")
        if not u and not self.setting("upi_qr"):
            return msg("Attention", "Enter a UPI ID or upload a QR image.")
        self.set_setting("upi_id", u)
        self.set_setting("upi_name", fs["upn"].strip())
        self.sync_now()
        msg("Done", "UPI details saved.")

    def pick_qr(self):
        self.pick_file("Choose QR image", ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"], self.save_qr)

    def save_qr(self, src):
        b = self.qr_b64(src)
        if not b:
            return msg("Could not save", "Choose a clear QR screenshot/photo (JPG or PNG, under 600 KB).")
        self.set_setting("upi_qr", b)
        self.sync_now()
        self.refresh()
        msg("Done", "QR saved. Students will now see it when they pay fees.")

    def rm_qr(self):
        def go():
            self.set_setting("upi_qr", "")
            self.sync_now()
            self.refresh()
        ask("Remove QR?", "Students will no longer see this QR code.", go, "Remove")

    def make_fees(self):
        fs = self.fs
        title = fs["title"].strip()
        try:
            amt = float(fs["amount"])
        except Exception:
            amt = 0
        if not title or amt <= 0 or not vd(fs["due"]):
            return msg('Attention', 'Enter a valid fee name, amount and last date (YYYY-MM-DD).')
        studs = self.students(fs)
        if not studs:
            return msg('No students', 'No students match this filter.')

        def go():
            ts, new = now_iso(), []
            for s in studs:
                fid = str(uuid.uuid5(NS, "fee|%s|%s" % (s["id"], title.lower())))
                if not self.d.one("SELECT 1 FROM fees WHERE id=?", (fid,)):
                    new.append(dict(id=fid, student_id=s["id"], title=title, amount=amt, due_date=fs["due"], status="due", paid_on=None, created_by=self.uid(), created_at=ts, updated_at=ts))
            self.push_rows("fees", new, "insert")
            self.notify([r["student_id"] for r in new], 'New fees: ' + title, '%s - last date %s. Open the Fees tab to pay via UPI.' % (money(amt), fs["due"]))
            fs["title"] = fs["amount"] = ""
            self.sync_now()
            self.refresh()
            msg('Done', 'Fees added for %d student(s) (%d already had it).' % (len(new), len(studs) - len(new)))
        ask('Add fees?', '%s - %s\nThis will be added for %d student(s).' % (title, money(amt), len(studs)), go, 'Yes, add', "ok")

    def fee_cash(self, fid):
        def go():
            ts = today()
            self.db("UPDATE fees SET status='paid',paid_on=?,updated_at=? WHERE id=?", (ts, now_iso(), fid))
            self.d.enqueue("patch", "fees", {"q": "id=eq." + fid, "values": {"status": "paid", "paid_on": ts}})
            self.sync_now()
            self.refresh()
        ask('Cash received?', 'Mark this fee as PAID?', go, 'Yes', "ok")

    def pay_decide(self, pid, ok):
        y = self.d.one("SELECT y.*, f.title FROM payments y JOIN fees f ON f.id=y.fee_id WHERE y.id=?", (pid,))
        if not y:
            return
        st = "verified" if ok else "rejected"
        self.db("UPDATE payments SET status=?,updated_at=? WHERE id=?", (st, now_iso(), pid))
        self.d.enqueue("patch", "payments", {"q": "id=eq." + pid, "values": {"status": st}})
        if ok:
            self.db("UPDATE fees SET status='paid',paid_on=?,updated_at=? WHERE id=?", (today(), now_iso(), y["fee_id"]))
            self.d.enqueue("patch", "fees", {"q": "id=eq." + y["fee_id"], "values": {"status": "paid", "paid_on": today()}})
        self.notify([y["student_id"]], "Payment %s" % ('received' if ok else 'rejected'),
                    ('Your %s payment of %s is verified. Thank you!' % (y["title"], money(y["amount"]))) if ok else
                    'Your %s payment could not be verified (the UTR may be wrong). Try again or meet the teacher.' % y["title"])
        self.sync_now()
        self.refresh()
        self.paint_nav()
        if ok:
            s = self.d.one(SQ + " WHERE s.id=?", (y["student_id"],))
            pc = self.parent(y["student_id"])
            if s and pc and pc["parent_mobile"]:
                txt = '%s\n*%s*: payment for %s (%s) has been received. Thank you!\n\n- %s' % (self.greet(s), fullname(s), y["title"], money(y["amount"]), APP_NAME)
                ask('Receipt to parent?', 'Send the payment receipt to the parent on WhatsApp?', lambda: wa_send(pc["parent_mobile"], txt), 'Send', "ok")

    # ---------- FEES: student ----------
    def s_fees(self, g):
        uid = self.uid()
        fees = self.rows("SELECT * FROM fees WHERE student_id=? ORDER BY CASE status WHEN 'paid' THEN 1 ELSE 0 END, due_date", (uid,))
        pays = self.rows("SELECT * FROM payments WHERE student_id=? ORDER BY created_at DESC", (uid,))
        pend = {y["fee_id"] for y in pays if y["status"] == "pending"}
        rej = {y["fee_id"] for y in pays if y["status"] == "rejected"}
        due = sum(float(f["amount"] or 0) for f in fees if f["status"] != "paid")
        c = Card(bg=[1, .93, .93, 1] if due else [.92, .98, .93, 1])
        c.add_widget(lbl('Total fees pending: %s' % money(due) if due else 'No fees pending', 18, NO if due else OK, True))
        g.add_widget(c)
        if not fees:
            c = Card()
            c.add_widget(lbl('No fees assigned yet.', 14, MU))
            g.add_widget(c)
        for f in fees:
            paid = f["status"] == "paid"
            late = (not paid) and f["due_date"] and f["due_date"] < today()
            c = Card()
            tag, col = ("PAID", OK) if paid else ('UNDER VERIFICATION', LV) if f["id"] in pend else ("OVERDUE", NO) if late else ("DUE", LV)
            c.add_widget(row(lbl(f["title"], 16, TX, True), lbl(tag, 12, col, True, "right", 110), h=30))
            c.add_widget(lbl("%s  |  last date %s" % (money(f["amount"]), f["due_date"] or "-"), 13, MU))
            if paid:
                c.add_widget(lbl("Paid on %s" % (f["paid_on"] or "-"), 12, OK))
            elif f["id"] in pend:
                c.add_widget(lbl('Your teacher is verifying your payment.', 12, LV))
            else:
                if f["id"] in rej:
                    c.add_widget(lbl('Your last payment could not be verified. Pay again and enter the correct UTR.', 12, NO, True))
                c.add_widget(btn('Pay now (UPI / QR)', lambda x=f: self.open_sub(self.pay_page(x["id"])), "ok"))
            g.add_widget(c)
        if pays:
            c = Card()
            c.add_widget(lbl("Payment history", 16, bold=True))
            for y in pays[:15]:
                c.add_widget(lbl("%s  |  %s  |  UTR %s  |  %s" % ((y["created_at"] or "")[:10], money(y["amount"]), y["utr"], y["status"].upper()), 12, MU))
            g.add_widget(c)

    def pay_page(self, fid):
        def page(g):
            self.back_card(g)
            f = self.d.one("SELECT * FROM fees WHERE id=?", (fid,))
            if not f:
                return g.add_widget(Card())
            upi, name, qr = self.setting("upi_id"), self.setting("upi_name"), self.setting("upi_qr")
            c = Card()
            c.add_widget(lbl(f["title"], 18, TX, True))
            c.add_widget(lbl("Amount: %s" % money(f["amount"]), 20, AC, True))
            g.add_widget(c)
            if not upi and not qr:
                c = Card()
                c.add_widget(lbl("The teacher has not set up UPI yet. Please contact the teacher.", 14, NO, True))
                return g.add_widget(c)
            c = Card()
            c.add_widget(lbl("Step 1: Scan the QR code with any UPI app and pay %s" % money(f["amount"]), 14, TX, True))
            tex = b64_texture(qr) if qr else None
            if tex:
                h = min(dp(320), (Window.width - dp(60)) * tex.height / max(1, tex.width))
                c.add_widget(Image(texture=tex, size_hint=(1, None), height=h))
            elif upi:
                m = qr_matrix(upi_uri(upi, name, f["amount"], "%s %s" % (f["title"], fullname(self.me))))
                if m:
                    box = BoxLayout(size_hint_y=None, height=dp(260))
                    box.add_widget(Widget())
                    box.add_widget(QRView(size_hint=(None, None), size=(dp(250), dp(250)), matrix=m))
                    box.add_widget(Widget())
                    c.add_widget(box)
            if upi:
                c.add_widget(lbl("UPI ID: %s%s" % (upi, ("  (%s)" % name) if name else ""), 13, MU, True, "center"))
                uri = upi_uri(upi, name, f["amount"], "%s %s" % (f["title"], fullname(self.me)))
                c.add_widget(btn("Open UPI app (GPay / PhonePe / Paytm)", lambda: open_url(uri) or msg("UPI app not found", "Scan the QR or pay using the UPI ID: " + upi), "ok"))
            g.add_widget(c)
            st = self.S("payst", dict)
            c = Card()
            c.add_widget(lbl("Step 2: After paying, enter the UTR / Transaction ID", 14, TX, True))
            c.add_widget(lbl("On the payment successful screen of your UPI app you will find a 12-digit UTR / Ref No.", 12, MU))
            c.add_widget(tin(st, "utr", "UTR / Transaction ID"))
            c.add_widget(btn("I have paid", lambda: self.submit_payment(f)))
            g.add_widget(c)
        return page

    def submit_payment(self, f):
        utr = re.sub(r"\s", "", self.payst.get("utr", ""))
        if len(utr) < 6:
            return msg('Attention', 'Enter a valid UTR / Transaction ID (at least 6 characters).')
        ts = now_iso()
        r = dict(id=str(uuid.uuid4()), fee_id=f["id"], student_id=self.uid(), amount=f["amount"], utr=utr, status="pending", created_at=ts, updated_at=ts)
        self.push_rows("payments", [r], "insert")
        self.payst["utr"] = ""
        self.sync_now()
        self.sub = None
        self.refresh()
        self.paint_nav()
        msg('Sent', 'Your payment details were sent to the teacher. The fee will show PAID once verified.')


Extras.pdf_page._secure = True     # no screenshots / screen recording while reading notes
Extras.test_page._secure = True    # ...and during an online test

class CodeNexus(Extras, App):
    title = "Code Nexus"

    # ---------- setup ----------
    def build(self):
        Window.clearcolor = BG
        if LOGO:
            self.icon = LOGO
        Window.softinput_mode = "below_target"
        Builder.load_string(KV)
        calendar.setfirstweekday(calendar.SUNDAY)
        ExceptionManager.add_handler(Guard())
        self.d = Db(os.path.join(self.user_data_dir, "smarthazri_cloud.db"))
        self.api = Api(self.d)
        self.lm = self.d.kget("lm", "total")
        self.thr = int(self.d.kget("thr", "75") or 75)
        self.every = int(self.d.kget("every", "30") or 30)
        self.status, self.sync_msg, self.syncing, self.recon = "offline", "", False, set()
        self.me, self.tab, self.sub, self.hz, self.rep, self.chip = None, 0, None, False, False, None
        self.grp, self.sf, self.ns, self.ed = new_state(), all_state(), reg_state(), None
        self.rf = dict(d1=today()[:8] + "01", d2=today(), q="")
        self.mk = dict(date=today(), subject="")
        self.hf = dict(subject="All", d1="", d2="", st="All")
        self.show_add, self.q, self.tex, self.last_unread = False, "", {}, -1
        self.att = None
        t0 = dt.date.today()
        self.cm = (t0.year, t0.month)
        self.root_fl = FloatLayout()
        self.main = BoxLayout(orientation="vertical")
        self.root_fl.add_widget(self.main)
        self.loader = Loader()
        Window.bind(on_keyboard=self.on_key)
        u = self.load_me() if (self.api.sess and configured()) else None
        if u:
            self.portal()
        else:
            self.login_screen()
        self.timer = Clock.schedule_interval(self.tick, self.every)
        Clock.schedule_once(self.tick, 1.5)
        return self.root_fl

    def on_pause(self):
        return True

    def on_resume(self):
        Clock.schedule_once(self.tick, .5)

    def on_stop(self):
        try:
            if self.d.kget("remember", "1") == "0":
                self.api.save(None)
        except Exception:
            pass

    def on_key(self, w, key, *a):
        if key == 27:
            if self.sub:
                self.sub = None
                self.refresh()
                return True
            if self.me and self.tab != 0:
                self.go(0)
                return True
        return False

    # ---------- small data helpers ----------
    def rows(self, sql, a=()):
        return self.d.rows(sql, a)

    def db(self, sql, a=()):
        return self.d.q(sql, a)

    def uid(self):
        return self.me["id"] if self.me else ""

    def staff(self):
        return bool(self.me) and self.me["role"] in ("teacher", "admin")

    def load_me(self):
        uid = self.api.sess["user_id"] if self.api.sess else ""
        p = self.d.one("SELECT * FROM profiles WHERE id=?", (uid,)) if uid else None
        if not p:
            return None
        extra = self.d.one(SQ + " WHERE s.id=?", (uid,)) if p["role"] == "student" else self.d.one("SELECT * FROM teachers WHERE id=?", (uid,))
        self.me = dict(extra or {}, **p)
        return self.me

    def stat(self, sid, sub=None, d1=None, d2=None):
        sql = "SELECT r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?"
        a = [sid]
        if sub and sub != "All":
            sql += " AND s.subject_id=?"
            a.append(sub)
        if d1:
            sql += " AND s.date>=?"
            a.append(d1)
        if d2:
            sql += " AND s.date<=?"
            a.append(d2)
        r = dict(self.db(sql + " GROUP BY r.status", a))
        return self.mkstat(r.get("P", 0), r.get("A", 0), r.get("L", 0))

    def mkstat(self, p, a, l):
        t, pc = calc(p, a, l, self.lm)
        return p, a, l, t, pc

    def students(self, d, q="", active=None):
        w, a = gwhere(d)
        sql = SQ + " WHERE p.role='student' AND " + w
        if q.strip():
            x = "%" + q.strip().lower() + "%"
            sql += " AND (lower(p.full_name) LIKE ? OR lower(s.enrollment) LIKE ? OR lower(p.email) LIKE ? OR p.mobile LIKE ?)"
            a += [x, x, x, x]
        rows = self.rows(sql + " ORDER BY length(s.enrollment), s.enrollment, p.full_name", a)
        rows.sort(key=lambda s: (branch_key(s["branch"]), year_rank(s["year"])))      # CSE, AI/ML, DS, EC, EX; 1st..4th year
        return rows

    def find_class(self, d):
        if d.get("inst", "college") == "college":
            k = ("college", bval(d), d["year"], d["sem"], d["sec"])
        else:
            k = ("school", cname(d), "-", "-", d["sec"] if d["sec"] != "All" else "-")
        return self.d.one("SELECT * FROM classes WHERE kind=? AND branch=? AND year=? AND semester=? AND section=?", k)

    def ensure_class(self, d):
        c = self.find_class(d)
        if c:
            return c["id"]
        col = d.get("inst", "college") == "college"
        c = dict(id=str(uuid.uuid4()), kind="college" if col else "school", branch=bval(d) if col else cname(d),
                 year=d["year"] if col else "-", semester=d["sem"] if col else "-", section=d["sec"] if d["sec"] != "All" else "-",
                 created_at=now_iso(), updated_at=now_iso())
        self.d.put("classes", [c])
        self.d.enqueue("upsert", "classes", {k: c[k] for k in wcols("classes")})
        return c["id"]

    def subjects_for(self, class_id):
        r = []
        if class_id:
            r = self.rows("SELECT s.* FROM class_subjects cs JOIN subjects s ON s.id=cs.subject_id WHERE cs.class_id=? ORDER BY s.name", (class_id,))
        return r or self.rows("SELECT * FROM subjects ORDER BY name")

    def sname(self, sid):
        if sid == DEFAULT_SUB:
            return "Attendance"
        r = self.d.one("SELECT code,name FROM subjects WHERE id=?", (sid,))
        return ("%s - %s" % (r["code"], r["name"])) if r else "?"

    def ensure_default_subject(self):
        """The app has no subjects. One hidden default subject keeps the old database structure working."""
        if not self.d.one("SELECT 1 FROM subjects WHERE id=?", (DEFAULT_SUB,)):
            r = dict(id=DEFAULT_SUB, code="CN", name="Code Nexus", created_at=now_iso(), updated_at=now_iso())
            self.d.put("subjects", [r])
            self.d.enqueue("upsert", "subjects", {k: r[k] for k in wcols("subjects")})

    def pending_leaves(self):
        return self.db("SELECT COUNT(*) FROM leave_requests WHERE status='pending'")[0][0]

    def unread(self):
        return self.db("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (self.uid(),))[0][0]

    # ---------- threads, loader, toast ----------
    def bg(self, fn, done):
        def run():
            try:
                r, e = fn(), None
            except Exception as ex:
                r, e = None, ex
            Clock.schedule_once(lambda d: done(r, e))
        threading.Thread(target=run, daemon=True).start()

    def loading(self, on, text="Please wait..."):
        if on:
            self.loader.text = text
            if not self.loader.parent:
                self.root_fl.add_widget(self.loader)
                self.loader.start()
        elif self.loader.parent:
            self.loader.stop()
            self.root_fl.remove_widget(self.loader)

    def net(self, fn, ok, text="Please wait...", err=None):
        """Run fn() in a background thread with a loading indicator; ok(result) on success, friendly message on error."""
        if text:
            self.loading(True, text)

        def done(r, e):
            self.loading(False)
            if e:
                log(e, "net")
                if isinstance(e, ApiError) and e.code == "session_expired":
                    return self.session_lost()
                return err(e) if err else msg("Error", friendly(e))
            try:
                ok(r)
            except Exception as ex:
                log(ex, "net-ok")
                msg("Error", 'Something went wrong: %s' % ex)
        self.bg(fn, done)

    def toast(self, text, col=None):
        c = Cell(text=text, bg=list(col or TX), color=WHITE, size_hint=(.92, None), pos_hint={"center_x": .5}, y=dp(74),
                 padding=[dp(12), dp(8)], font_size=sp(13), halign="center", valign="middle")
        c.bind(width=lambda i, v: setattr(i, "text_size", (v - dp(24), None)))
        c.bind(texture_size=lambda i, s: setattr(i, "height", s[1] + dp(16)))
        self.root_fl.add_widget(c)
        Clock.schedule_once(lambda d: Animation(opacity=0, d=.5).start(c), 3)
        Clock.schedule_once(lambda d: self.root_fl.remove_widget(c) if c.parent else None, 3.6)

    # ---------- background sync (Supabase) ----------
    def set_status(self, s):
        self.status = s
        if self.chip:
            lab, col = {"online": ("Online", OK), "offline": ("Offline", MU), "syncing": ("Syncing...", AC),
                        "synced": ("Synced", OK), "failed": ("Sync Failed", NO)}[s]
            self.chip.text, self.chip.bg = lab, list(col)

    def tick(self, *_):
        self.sync_now()

    def sync_now(self):
        if self.syncing or not self.api.sess or not configured():
            return
        self.syncing = True
        self.set_status("syncing")
        self.bg(self.sync_job, self.sync_done)

    def sync_job(self):
        sent, errs = self.flush_outbox()
        if self.recon and not self.d.pending():
            for t in list(self.recon):
                self.reconcile(t)
                self.recon.discard(t)
        ch = self.pull_all()
        me = self.d.one("SELECT is_active FROM profiles WHERE id=?", (self.api.sess["user_id"],)) if self.api.sess else None
        if self.api.sess and not self.d.one("SELECT 1 FROM avatars WHERE id=?", (self.api.sess["user_id"],)):
            self.fetch_avatar(self.api.sess["user_id"])
        return dict(sent=sent, errs=errs, changed=ch, disabled=bool(me) and not me["is_active"])

    def sync_done(self, r, e):
        self.syncing = False
        if e:
            if isinstance(e, NetError):
                self.set_status("offline")
                self.sync_msg = 'Offline - will sync automatically when internet returns.'
            elif isinstance(e, ApiError) and e.code == "session_expired":
                return self.session_lost()
            else:
                log(e, "sync")
                self.set_status("failed")
                self.sync_msg = "Sync fail: " + friendly(e)
            return
        if r["disabled"]:
            return self.force_logout('Your account has been disabled. Please contact the teacher.')
        if r["errs"]:
            self.set_status("failed")
            self.toast('%d change(s) were rejected by the cloud (see Profile > Sync).' % r["errs"], NO)
        else:
            self.set_status("synced")
        self.sync_msg = "Last sync: " + dt.datetime.now().strftime("%I:%M:%S %p")
        if r["changed"] or r["sent"]:
            self.after_sync()


    def any_popup(self):
        return any(isinstance(w, Popup) for w in Window.children)

    def after_sync(self):
        if not self.me:
            return
        self.load_me()
        self.paint_nav()
        n = self.unread()
        if self.last_unread >= 0 and n > self.last_unread:
            r = self.d.one("SELECT title,body FROM notifications WHERE user_id=? AND is_read=0 ORDER BY created_at DESC LIMIT 1", (self.uid(),))
            if r:
                self.toast("%s: %s" % (r["title"], r["body"]), AC)
        self.last_unread = n
        if self.tab == 0 and not self.sub and not self.any_popup():
            self.refresh()

    def flush_outbox(self):
        sent = errs = 0
        while True:
            ops = self.rows("SELECT * FROM outbox ORDER BY id LIMIT 50")
            if not ops:
                break
            for op in ops:
                try:
                    self.run_op(op["kind"], op["target"], json.loads(op["payload"]))
                except ApiError as e:
                    if e.code == "session_expired":
                        raise
                    if e.status >= 500 or e.status in (408, 425, 429):
                        raise NetError(e.msg)
                    errs += 1
                    self.db("INSERT INTO sync_errors(at,what,err) VALUES(?,?,?)", (now_iso(), "%s %s" % (op["kind"], op["target"]), friendly(e)))
                    self.recon.add("attendance_sessions" if op["target"] == "save_attendance" else op["target"])
                    if op["target"] == "save_attendance":
                        self.recon.add("attendance_records")
                self.db("DELETE FROM outbox WHERE id=?", (op["id"],))
                sent += 1
        return sent, errs

    def run_op(self, kind, tgt, p):
        r = self.api.rest
        if kind == "upsert":
            r("POST", "/rest/v1/%s?on_conflict=id" % tgt, p, {"Prefer": "resolution=merge-duplicates,return=minimal"})
        elif kind == "insert":
            r("POST", "/rest/v1/%s?on_conflict=id" % tgt, p, {"Prefer": "resolution=ignore-duplicates,return=minimal"})
        elif kind == "patch":
            r("PATCH", "/rest/v1/%s?%s" % (tgt, p["q"]), p["values"], {"Prefer": "return=minimal"})
        elif kind == "delete":
            r("DELETE", "/rest/v1/%s?%s" % (tgt, p["q"]))
        elif kind == "rpc":
            self.api.rpc(tgt, p)

    @staticmethod
    def cursor(hdr):
        try:
            t = email.utils.parsedate_to_datetime(hdr.get("Date"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            t = dt.datetime.now(dt.timezone.utc)
        return (t - dt.timedelta(minutes=10)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def fetch_pages(self, path, first_hdr=None):
        out, off, hdr0 = [], 0, None
        while True:
            data, hdr = self.api.rest("GET", path + ("&" if "?" in path else "?") + "limit=1000&offset=%d" % off)
            hdr0 = hdr0 or hdr
            out += data or []
            if not data or len(data) < 1000:
                return out, hdr0
            off += 1000

    def pull_all(self):
        changed = 0
        cur = self.d.kget("cur:tomb")
        if cur:
            try:
                age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(cur)
                if age.days > 150 and not self.d.pending():
                    self.d.wipe()
                    cur = ""
            except Exception:
                pass
        if cur:
            rows, hdr = self.fetch_pages("/rest/v1/tombstones?select=table_name,row_id&order=id.asc&deleted_at=gte." + urllib.parse.quote(cur, safe=""))
        else:
            rows, hdr = [], self.api.rest("GET", "/rest/v1/tombstones?select=id&limit=1")[1]
        if cur:
            by = {}
            for r in rows:
                by.setdefault(r["table_name"], []).append(r["row_id"])
            for t, ids in by.items():
                if t in SCHEMA:
                    self.d.delete_ids(t, ids)
                    changed += len(ids)
                if t == "profiles":
                    self.d.delete_ids("avatars", ids)
        self.d.kset("cur:tomb", self.cursor(hdr))
        for t in PULL_ORDER:
            cur = self.d.kget("cur:" + t)
            path = "/rest/v1/%s?select=%s&order=updated_at.asc,id.asc" % (t, ",".join(SCHEMA[t]))
            if cur:
                path += "&updated_at=gte." + urllib.parse.quote(cur, safe="")
            rows, hdr = self.fetch_pages(path)
            changed += self.d.put_new(t, rows)
            self.d.kset("cur:" + t, self.cursor(hdr))
        return changed

    def reconcile(self, t):
        """After a rejected upload: make the local copy of table t equal to the server again."""
        if t not in SCHEMA:
            return
        rows, _ = self.fetch_pages("/rest/v1/%s?select=%s&order=id.asc" % (t, ",".join(SCHEMA[t])))
        self.d.put(t, rows)
        keep = {r["id"] for r in rows}
        self.d.delete_ids(t, [r[0] for r in self.db("SELECT id FROM %s" % t) if r[0] not in keep])

    def fetch_avatar(self, uid):
        try:
            r, _ = self.api.rest("GET", "/rest/v1/profiles?id=eq.%s&select=avatar" % uid)
            self.db("INSERT OR REPLACE INTO avatars VALUES(?,?)", (uid, (r[0].get("avatar") if r else "") or ""))
        except (NetError, ApiError):
            pass

    # ---------- page scaffolding (same as v4) ----------
    def new_page(self):
        sv = ScrollView(bar_width=dp(3))
        g = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=[dp(12), dp(10), dp(12), dp(16)])
        g.bind(minimum_height=g.setter("height"))
        sv.add_widget(g)
        return sv, g

    def fade(self, g):
        for i, w in enumerate(reversed(g.children)):
            w.opacity = 0
            Clock.schedule_once(lambda d, w=w: Animation(opacity=1, d=.4, t="out_quad").start(w), min(i, 10) * .06)

    def show(self, fn, anim=True):
        sec = bool(getattr(fn, "_secure", False))
        self.set_secure(sec)
        if not sec and self.pdf:
            self.pdf_close()
        self.holder.clear_widgets()
        sv, g = self.new_page()
        try:
            fn(g)
        except Exception as e:
            log(e, "page")
            g.clear_widgets()
            c = Card()
            c.add_widget(lbl('This page could not be opened', 16, NO, True))
            c.add_widget(lbl(str(e)[:160], 12, MU))
            c.add_widget(btn('Go to Home', lambda: self.go(0)))
            g.add_widget(c)
        self.holder.add_widget(sv)
        if anim:
            self.fade(g)

    def refresh(self):
        if self.me:
            self.show(self.sub or self.tabs[self.tab][1], anim=False)

    def open_sub(self, fn):
        self.sub = fn
        self.show(fn)

    def back_card(self, g, text='< Back'):
        g.add_widget(btn(text, lambda: (setattr(self, "sub", None), self.refresh()), "ghost", size_hint_y=None, height=dp(40)))

    # ---------- portal / navigation ----------
    def portal(self):
        self.main.clear_widgets()
        T = self.staff()
        self.tabs = ([("Home", self.t_home), ("Attendance", self.t_mark), ("Students", self.t_students), ("Tests", self.t_tests),
                      ("Fees", self.t_fees), ("More", self.t_more)] if T else
                     [("Home", self.s_home), ("Tests", self.s_tests), ("Notes", self.s_notes), ("Fees", self.s_fees), ("More", self.s_more)])
        self.tab, self.sub, self.hz, self.rep = 0, None, False, False
        self.att = None
        h = Panel(orientation="horizontal", bg=AC, rad=0, size_hint_y=None, height=dp(62), padding=[dp(12), dp(8)], spacing=dp(10))
        if LOGO:
            h.add_widget(Image(source=LOGO, size_hint=(None, None), size=(dp(46), dp(46)), pos_hint={"center_y": .5}))
        t = Label(text="Code Nexus", font_size=sp(20), bold=True, color=WHITE, halign="left", valign="middle")
        t.bind(size=lambda i, v: setattr(i, "text_size", v))
        h.add_widget(t)
        self.chip = RBtn(text="Offline", bg=list(MU), size_hint=(None, None), size=(dp(92), dp(28)), font_size=sp(11),
                         pos_hint={"center_y": .5}, on_release=lambda *_: self.chip_tap())
        h.add_widget(self.chip)
        h.add_widget(RBtn(text="Logout", bg=[1, 1, 1, .2], size_hint_x=None, width=dp(74), on_release=lambda *_: self.logout()))
        self.main.add_widget(h)
        self.main.add_widget(Panel(bg=GOLD, rad=0, size_hint_y=None, height=dp(3)))
        self.holder = BoxLayout()
        self.main.add_widget(self.holder)
        nav = Panel(orientation="horizontal", bg=WHITE, rad=0, size_hint_y=None, height=dp(54))
        self.nbtn = []
        for i, (name, fn) in enumerate(self.tabs):
            b = RBtn(text=name, bg=WHITE, height=dp(54), font_size=sp(11 if len(self.tabs) > 5 else 14), on_release=lambda *_, i=i: self.go(i))
            self.nbtn.append(b)
            nav.add_widget(b)
        self.main.add_widget(nav)
        self.set_status(self.status)
        self.paint_nav()
        self.show(self.tabs[self.tab][1])

    def chip_tap(self):
        self.sync_now()
        self.toast(self.sync_msg or 'Sync started...', AC)

    def paint_nav(self):
        n = self.unread()
        for i, b in enumerate(self.nbtn):
            name = self.tabs[i][0]
            badge = self.tab_badge(name, n)
            b.text = name + (" (%d)" % badge if badge else "")
            b.color = AC if i == self.tab else MU

    def go(self, i):
        self.tab, self.sub = i, None
        self.paint_nav()
        self.show(self.tabs[i][1])

    def hero(self, g, u, top, name, sub=""):
        p = Panel(orientation="horizontal", bg=AC, size_hint_y=None, height=dp(116), padding=dp(14), spacing=dp(12))
        p.add_widget(self.avatar(u, 80))
        c = BoxLayout(orientation="vertical", spacing=dp(2))
        c.add_widget(lbl(top, 13, HERO_SUB))
        c.add_widget(lbl(name, 20, WHITE, True))
        if sub:
            c.add_widget(lbl(sub, 12, HERO_SUB))
        p.add_widget(c)
        g.add_widget(p)

    def selector(self, g, label, cb, st=None, sel="batch", extra=None):
        st = st if st is not None else self.grp
        c = Card()
        c.add_widget(lbl('Choose class', 17, bold=True))
        for w in class_fields(st, sel, self.refresh):
            c.add_widget(w)
        for w in (extra() if extra else []):
            c.add_widget(w)
        c.add_widget(btn(label, cb))
        g.add_widget(c)

    # ---------- login / session ----------
    def after_auth(self):
        """Runs in a thread right after Supabase Auth succeeded (session already stored)."""
        uid = self.api.sess["user_id"]
        if self.d.kget("last_user", "") not in ("", uid):
            self.d.wipe()                      # different person on this phone: never mix their data
        self.d.kset("last_user", uid)
        p = self.bootstrap_me(uid)           # own profile first, so login never depends on the big sync
        if not p:
            self.api.save(None)
            raise ApiError(400, 'No profile found for this account. Contact the admin.', "no_profile")
        if not p["is_active"]:
            self.api.save(None)
            raise ApiError(400, 'Your account is disabled. Please contact the teacher.', "disabled")
        self.boot_err = ""
        try:
            self.sync_job()
        except NetError as e:
            self.boot_err = str(e)
        except ApiError as e:
            if e.code == "session_expired":
                raise
            log(e, "first-sync")
            self.boot_err = friendly(e)
        return uid

    def bootstrap_me(self, uid):
        """Download only the logged-in user's own rows (profile + student/teacher row + class) into the local cache."""
        def one(t, val):
            r, _ = self.api.rest("GET", "/rest/v1/%s?id=eq.%s&select=%s" % (t, val, ",".join(SCHEMA[t])))
            self.d.put(t, r or [])
            return r[0] if r else None
        p = one("profiles", uid)
        if p:
            if p["role"] == "student":
                st = one("students", uid)
                if st:
                    one("classes", st["class_id"])
            else:
                one("teachers", uid)
        return p

    def finish_login(self, _=None):
        if not self.load_me():
            return msg("Error", 'Could not load profile. Please try again.')
        self.last_unread = -1
        err = getattr(self, "boot_err", "")
        if err:
            self.status, self.sync_msg = "failed", 'First sync was incomplete: %s' % err[:140]
        else:
            self.status, self.sync_msg = "synced", "Last sync: " + dt.datetime.now().strftime("%I:%M:%S %p")
        self.portal()
        if err:
            self.toast('Data did not load completely; it will retry automatically shortly.', LV)
        ph = getattr(self, "pend_photo", "")
        if ph:
            self.pend_photo = ""
            self.new_photo(ph, quiet=True)
        self.last_unread = self.unread()
        Clock.schedule_once(self.tick, .5)

    def session_lost(self):
        self.api.save(None)
        self.force_logout('Session expired. Please login again.')

    def force_logout(self, text):
        self.me, self.sub = None, None
        self.login_screen()
        msg("Login", text)

    def logout(self):
        n = self.d.pending()
        txt = 'You will need to login again after logout.'
        if n:
            txt += '\n\n%d change(s) have not been uploaded to the cloud yet. They will be lost if you logout.' % n
        ask("Logout", txt, self.do_logout)

    def do_logout(self):
        self.tk_end()
        self.pdf_close()
        self.set_secure(False)
        def work():
            try:
                if self.d.pending():
                    self.flush_outbox()
            except Exception:
                pass
            self.api.logout()
            self.d.wipe()
            self.d.kdel("last_user")

        def ok(_):
            self.me, self.sub, self.tex = None, None, {}
            self.login_screen()
        self.net(work, ok, 'Logging out...', err=lambda e: ok(None))

    def login_screen(self):
        self.chip = None
        self.main.clear_widgets()
        sv, g = self.new_page()
        if not hasattr(self, "lg"):
            self.lg = dict(u="", p="")
        if LOGO:
            lb = BoxLayout(size_hint_y=None, height=dp(150))
            lb.add_widget(Widget())
            lb.add_widget(Image(source=LOGO, size_hint=(None, None), size=(dp(140), dp(140)), pos_hint={"center_y": .5}))
            lb.add_widget(Widget())
            g.add_widget(lb)
        g.add_widget(lbl("Code Nexus", 34, AC, True, "center"))
        g.add_widget(lbl("Attendance System  |  JIT Borawan", 14, MU, False, "center"))
        if not configured():
            w = Card(bg=[1, .93, .93, 1])
            w.add_widget(lbl('Supabase key is not set. Put your sb_publishable_ key in SUPABASE_KEY at the top of main.py.', 13, NO, True))
            g.add_widget(w)
        c = Card()
        c.add_widget(lbl("Login", 18, bold=True))
        u = tin(self.lg, "u", 'Email or Enrollment No. / Employee ID')
        p = tin(self.lg, "p", "Password", password=True)
        c.add_widget(u)
        c.add_widget(row(p, small("Show", lambda: setattr(p, "password", not p.password), "ghost", 62)))
        rm = btn("", lambda: flip(), "ghost", size_hint_y=None, height=dp(40))

        def paint_rm():
            rm.text = 'Remember login: ' + ("ON" if self.d.kget("remember", "1") == "1" else "OFF")

        def flip():
            self.d.kset("remember", "0" if self.d.kget("remember", "1") == "1" else "1")
            paint_rm()
        paint_rm()
        c.add_widget(rm)
        c.add_widget(btn("Login", self.do_login))
        c.add_widget(btn('Create new account (Register)', self.start_register, "ghost"))
        c.add_widget(btn('Forgot password?', self.forgot, "plain"))
        c.add_widget(btn("Connection check", self.conn_test, "plain"))
        g.add_widget(c)
        self.main.add_widget(sv)
        self.fade(g)

    def conn_test(self):
        def work():
            return self.api._req("GET", "/auth/v1/health", timeout=15)[0]

        def ok(d):
            msg("Connection OK", 'Connected to Supabase.\n%s' % json.dumps(d)[:150])

        def err(e):
            msg("Connection fail", "%s\n\nType: %s\nDetail: %s" % (friendly(e), type(e).__name__, str(e)[:300]))
        self.net(work, ok, 'Checking...', err=err)

    def do_login(self):
        ident, pw = self.lg["u"].strip(), self.lg["p"]
        if not configured():
            return msg('Setup pending', 'Put SUPABASE_KEY (sb_publishable_...) in main.py.')
        if not ident or not pw:
            return msg('Attention', 'Enter both email/enrollment and password.')

        def work():
            self.syncing = True
            try:
                em = ident if "@" in ident else self.api.rpc_anon("login_email", {"p_identifier": ident})
                if not em:
                    raise ApiError(400, "Invalid login credentials", "invalid_credentials")
                self.api.login(em, pw)
                return self.after_auth()
            finally:
                self.syncing = False
        self.lg["p"] = ""
        self.net(work, self.finish_login, 'Logging in...')

    # ---------- forgot / reset password (Supabase Auth e-mail code) ----------
    def forgot(self):
        b = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        e = inp("Registered email")
        b.add_widget(lbl('Enter your registered email. A 6-digit reset code will be sent to it.', 13, MU))
        b.add_widget(e)
        p = pop("Password reset", b, 330)

        def send():
            em = e.text.strip().lower()
            if not valid_email(em):
                return msg('Attention', 'Enter a valid email.')

            def work():
                self.api.recover(em)
            self.net(work, lambda _: stage2(em), 'Sending code...')

        def stage2(em):
            b.clear_widgets()
            c, n1, n2 = inp('6-digit code from email'), inp('New password (6+ characters)', password=True), inp('Confirm password', password=True)
            b.add_widget(lbl('Check your email (also spam). Enter the code here and set a new password.', 13, MU))
            for w in (c, n1, n2):
                b.add_widget(w)

            def go():
                if len(c.text.strip()) < 6:
                    return msg('Attention', 'Enter the code from the email.')
                if len(n1.text) < 6 or n1.text != n2.text:
                    return msg('Attention', 'Password must be 6+ characters and both entries must match.')

                def work2():
                    self.syncing = True
                    try:
                        self.api.verify_recovery(em, c.text)
                        self.api.set_password(n1.text)
                    finally:
                        self.api.save(None)
                        self.syncing = False
                self.net(work2, lambda _: (p.dismiss(), msg("Done", 'Password changed. Now login with the new password.')), 'Changing password...')
            b.add_widget(btn('Change password', go))
            b.add_widget(btn("Cancel", p.dismiss, "muted"))
            p.height = dp(440)

        b.add_widget(btn('Send code', send))
        b.add_widget(btn("Cancel", p.dismiss, "muted"))
        p.open()

    # ---------- register ----------
    def start_register(self):
        self.rg = reg_state()
        self.register_screen(True)

    def register_screen(self, anim=False):
        st = self.rg
        self.main.clear_widgets()
        sv, g = self.new_page()
        g.add_widget(lbl('New Account', 26, AC, True, "center"))
        c = Card()
        c.add_widget(lbl('I am a', 12, MU))
        tb = {k: RBtn(text=t, bg=list(AC if st["role"] == k else GR), color=WHITE if st["role"] == k else MU,
                      on_release=lambda *_, k=k: (st.__setitem__("role", k), self.register_screen())) for k, t in (("student", "Student"), ("teacher", "Teacher"))}
        c.add_widget(row(tb["student"], tb["teacher"]))
        c.add_widget(row(self.avatar({"photo_src": st["photo_src"], "full_name": st["name"] or "?"}, 84),
                         btn('Choose profile photo', lambda: self.pick_photo(lambda p: (st.__setitem__("photo_src", p), self.register_screen())), "muted", pos_hint={"center_y": .5}), h=90))

        def f(label, key, hint="", **k):
            c.add_widget(lbl(label, 12, MU))
            c.add_widget(tin(st, key, hint or label, **k))

        f('First name', "name")
        f("Surname (Last name)", "surname")
        f('Email (for login and password reset)', "email", "name@example.com")
        f("Mobile number (10 digit)", "mobile", num=True)
        if st["role"] == "teacher":
            f("Department", "dept")
            f("Employee ID (optional)", "empid")
            f('Teacher access code (get it from the admin)', "tcode", password=True)
        else:
            f("Enrollment / Roll number", "roll")
            f('College name', "college_name")
            for w in class_fields(st, False, self.register_screen):
                c.add_widget(w)
        f("Password (6+ akshar)", "pw", password=True)
        f('Re-enter password', "pw2", password=True)
        c.add_widget(btn('Register', self.do_register))
        c.add_widget(btn('Back to Login', self.login_screen, "muted"))
        g.add_widget(c)
        self.main.add_widget(sv)
        if anim:
            self.fade(g)

    def check_form(self, st, t, add):
        """Returns an error text or '' if the form is valid."""
        if not st["name"].strip() or not st["surname"].strip():
            return 'First name and surname are required.'
        if not valid_email(st["email"].strip()):
            return 'Enter a valid email (e.g. name@gmail.com).'
        if not add and not valid_mobile(st["mobile"].strip()):
            return 'Mobile number must be 10 digits.'
        if len(st["pw"]) < 6 or st["pw"] != st["pw2"]:
            return 'Password must be 6+ characters and both entries must match.'
        if t:
            if not st["tcode"].strip():
                return 'Teacher access code is required.'
        else:
            if not valid_enroll(st["roll"].strip()):
                return 'Enrollment number must be 3-30 characters (letters, numbers, - _ / .).'
            if st["inst"] == "college" and st["branch"] == "Other" and not st["branch_o"].strip():
                return 'Enter your branch name.'
        return ""

    def do_register(self, st=None, add=False):
        st = st or self.rg
        t = st["role"] == "teacher"
        bad = self.check_form(st, t, add)
        if bad:
            return msg('Attention', bad)
        if not configured():
            return msg('Setup pending', 'Put SUPABASE_KEY (sb_publishable_...) in main.py.')
        em, col = st["email"].strip().lower(), st["inst"] == "college"
        meta = dict(first_name=st["name"].strip(), last_name=st["surname"].strip(), mobile=st["mobile"].strip())
        if t:
            meta.update(teacher_code=st["tcode"].strip(), employee_id=st["empid"].strip(), department=st["dept"].strip(), subject_note=st["subject"].strip())
        else:
            meta.update(enrollment=st["roll"].strip(), kind=st["inst"], college_name=st["college_name"].strip(),
                        branch=bval(st) if col else cname(st), year=st["year"] if col else "-", semester=st["sem"] if col else "-",
                        section=st["sec"] if st["sec"] != "All" else "-", batch=st["batch"] if col and st["batch"] != "All" else "")

        def work():
            r = self.api.rpc_anon("check_available", {"p_email": em, "p_enrollment": None if t else meta["enrollment"]})
            if r and r.get("email_taken"):
                raise ApiError(400, 'This email is already registered.', "email_exists")
            if r and r.get("enrollment_taken"):
                raise ApiError(400, 'This enrollment number is already registered.', "dup_enroll")
            d = self.api.signup(em, st["pw"], meta)
            if add:
                return d
            if d.get("access_token"):
                self.syncing = True
                try:
                    self.api.store(d)
                    self.after_auth()
                finally:
                    self.syncing = False
            return d

        def ok(d):
            if add:
                nid = (d.get("user") or {}).get("id") or d.get("id")
                if nid:
                    self.d.enqueue("patch", "students", {"q": "id=eq." + nid, "values": {"mentor_id": self.uid()}})
                keep = {k: st[k] for k in ("inst", "branch", "branch_o", "year", "sem", "sec", "batch", "cls", "college_name")}
                self.ns = dict(reg_state(), **keep)
                self.show_add = False
                self.sub = None
                self.sync_now()
                msg("Done", 'Student added. They can login with their email/enrollment and password.')
                return self.refresh()
            if d.get("access_token"):
                self.pend_photo = st["photo_src"]
                return self.finish_login()
            self.login_screen()
            msg('Account created', 'A confirmation link was sent to your email. Confirm it and then login.')

        def err(e):
            if t and isinstance(e, ApiError) and "database error" in (e.msg or "").lower():
                return msg('Registration failed', 'The teacher access code is wrong or this email is already registered.')
            msg('Registration failed', friendly(e))
        self.net(work, ok, 'Creating account...', err=err)

    # ---------- photo ----------
    def avatar(self, u, size=80):
        kw = dict(size_hint=(None, None), size=(dp(size), dp(size)), pos_hint={"center_y": .5})
        src = u.get("photo_src") or ""
        if src and os.path.exists(src):
            return Image(source=src, **kw)
        uid = u.get("id")
        r = self.d.one("SELECT b64 FROM avatars WHERE id=?", (uid,)) if uid else None
        if r and r["b64"]:
            key = (uid, len(r["b64"]))
            try:
                if key not in self.tex:
                    from kivy.core.image import Image as CoreImage
                    self.tex[key] = CoreImage(io.BytesIO(base64.b64decode(r["b64"])), ext="jpg").texture
                return Image(texture=self.tex[key], **kw)
            except Exception as e:
                log(e, "avatar")
        return Initials(text=initials(fullname(u)), **kw)

    def pick_file(self, title, filters, done):
        """Opens the phone's own file manager (full file names, folders, Recent, Downloads, Drive...). Falls back to a simple list on other platforms."""
        fl = [f.lower() for f in filters]
        mime = "application/pdf" if any("pdf" in f for f in fl) else "text/*" if any("txt" in f for f in fl) else "image/*"
        if not self.pick_native(mime, done):
            self.pick_browser(title, filters, done)

    def pick_native(self, mime, done):
        try:
            from jnius import autoclass
            from android import activity as aact
        except Exception:
            return False
        try:
            Intent = autoclass("android.content.Intent")
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            it = Intent(Intent.ACTION_OPEN_DOCUMENT)
            it.addCategory(Intent.CATEGORY_OPENABLE)
            it.setType(mime)
            code = 7431

            def on_result(req, res, data):
                if req != code:
                    return
                aact.unbind(on_activity_result=on_result)
                if res != -1 or data is None:      # -1 = RESULT_OK; anything else = cancelled
                    return
                try:
                    path = self.copy_picked(act, data.getData())
                except Exception as e:
                    log(e, "pick")
                    return Clock.schedule_once(lambda dt: msg("Could not read file", "Please choose the file again."), 0)
                Clock.schedule_once(lambda dt: done(path), 0)
            aact.bind(on_activity_result=on_result)
            act.startActivityForResult(it, code)
            return True
        except Exception as e:
            log(e, "pick-native")
            return False

    def copy_picked(self, act, uri):
        """Copy the chosen file into the app's private folder, keeping its real name, and return the path."""
        import shutil
        res = act.getContentResolver()
        name = ""
        cur = res.query(uri, None, None, None, None)
        try:
            if cur is not None and cur.moveToFirst():
                ix = cur.getColumnIndex("_display_name")
                if ix >= 0:
                    name = cur.getString(ix) or ""
        finally:
            if cur is not None:
                cur.close()
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "file"
        folder = os.path.join(self.user_data_dir, "picked")
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        pfd = res.openFileDescriptor(uri, "r")
        with os.fdopen(pfd.detachFd(), "rb") as s, open(path, "wb") as d:
            shutil.copyfileobj(s, d, 1 << 16)
        return path

    def pick_browser(self, title, filters, done):
        from kivy.uix.filechooser import FileChooserListView
        start = "/storage/emulated/0" if os.path.isdir("/storage/emulated/0") else os.path.expanduser("~")
        fc = FileChooserListView(path=start, filters=list(filters))
        b = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(6))
        b.add_widget(fc)
        p = pop(title, b, w=.96)
        p.size_hint = (.96, .9)

        def ok():
            if fc.selection:
                p.dismiss()
                done(fc.selection[0])
            else:
                msg("Attention", "Please select a file first.")
        b.add_widget(row(btn("Cancel", p.dismiss, "muted"), btn("Select", ok)))
        p.open()

    def pick_photo(self, done):
        self.pick_file("Choose photo", ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG"], done)

    def photo_b64(self, src):
        try:
            try:
                from PIL import Image as PI
                im = PI.open(src).convert("RGB")
                im.thumbnail((256, 256))
                bio = io.BytesIO()
                im.save(bio, "JPEG", quality=80)
                raw = bio.getvalue()
            except ImportError:
                raw = open(src, "rb").read()
                if len(raw) > 120000:
                    return ""
            return base64.b64encode(raw).decode()
        except Exception as e:
            log(e, "photo")
            return ""

    def new_photo(self, src, quiet=False):
        b = self.photo_b64(src)
        if not b:
            return None if quiet else msg("Error", 'Could not save the photo (choose a small JPG/PNG).')
        self.db("INSERT OR REPLACE INTO avatars VALUES(?,?)", (self.uid(), b))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + self.uid(), "values": {"avatar": b}})
        self.sync_now()
        if not quiet:
            self.refresh()

    # ---------- notifications ----------
    def notif_card(self, g):
        rs = self.rows("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 6", (self.uid(),))
        if not rs:
            return
        c = Card()
        c.add_widget(lbl("Notifications", 16, bold=True))
        for r in rs:
            c.add_widget(lbl(("* " if not r["is_read"] else "") + r["title"], 14, TX if r["is_read"] else AC, True))
            c.add_widget(lbl("%s  (%s)" % (r["body"], (r["created_at"] or "")[:10]), 12, MU))
        if any(not r["is_read"] for r in rs):
            c.add_widget(btn('Mark all as read', self.read_all, "ghost"))
        g.add_widget(c)

    def read_all(self):
        self.db("UPDATE notifications SET is_read=1 WHERE user_id=?", (self.uid(),))
        self.d.enqueue("patch", "notifications", {"q": "user_id=eq.%s&is_read=eq.false" % self.uid(), "values": {"is_read": True}})
        self.sync_now()
        self.paint_nav()
        self.refresh()

    # ---------- shared month calendar ----------
    def mv(self, n):
        y, m = self.cm
        m += n
        if m < 1:
            m, y = 12, y - 1
        if m > 12:
            m, y = 1, y + 1
        self.cm = (y, m)
        self.refresh()

    def cal_card(self, g, title, colfn, click=None, legend=""):
        y, m = self.cm
        c = Card()
        if title:
            c.add_widget(lbl(title, 16, bold=True))
        c.add_widget(row(small("<", lambda: self.mv(-1)), lbl("%s %d" % (calendar.month_name[m], y), 17, TX, True, "center"), small(">", lambda: self.mv(1))))
        weeks = calendar.monthcalendar(y, m)
        grid = GridLayout(cols=7, size_hint_y=None, height=dp(38) * (len(weeks) + 1), spacing=dp(4))
        for dn in "SMTWTFS":
            grid.add_widget(Label(text=dn, color=MU, bold=True))
        for wk in weeks:
            for d in wk:
                if not d:
                    grid.add_widget(Widget())
                    continue
                k = "%04d-%02d-%02d" % (y, m, d)
                col = colfn(k)
                kw = dict(text=str(d), bg=list(col or [.93, .94, .97, 1]), color=WHITE if col else TX, font_size=sp(13))
                grid.add_widget(DayCell(on_release=lambda *_, k=k: click(k), **kw) if click else Cell(**kw))
        c.add_widget(grid)
        if legend:
            c.add_widget(lbl(legend, 12, MU, align="center"))
        g.add_widget(c)

    # ---------- student: home ----------
    def s_home(self, g):
        u = self.me
        uid = u["id"]
        p, a, l, t, pc = self.stat(uid)
        self.hero(g, u, "Welcome", fullname(u), "Enrollment %s  |  %s" % (u.get("roll", ""), glabel(u)))
        col = NO if pc < self.thr and t else OK
        c = Card(orientation="horizontal", spacing=dp(14))
        ring = Ring(size_hint=(None, None), size=(dp(120), dp(120)), col=list(col))
        Clock.schedule_once(lambda d: Animation(value=pc, d=1.1, t="out_cubic").start(ring), .3)
        c.add_widget(ring)
        inf = BoxLayout(orientation="vertical", spacing=dp(2))
        inf.add_widget(lbl("Present: %d" % p, 15, OK, True))
        inf.add_widget(lbl("Absent: %d" % a, 15, NO, True))
        inf.add_widget(lbl("Leave: %d" % l, 15, LV, True))
        inf.add_widget(lbl("Total classes: %d" % t, 13, MU))
        inf.add_widget(lbl("Percentage: %s" % pstr(pc, t), 13, col, True))
        c.add_widget(inf)
        g.add_widget(c)
        if pc < self.thr and t and self.thr < 100:
            need = max(1, -(-(self.thr * t - 100 * p) // (100 - self.thr)))
            w = Card(bg=[1, .93, .93, 1])
            w.add_widget(lbl('Attendance is below %d%%! Attend %d classes in a row to reach %d%%.' % (self.thr, need, self.thr), 14, NO, True))
            g.add_widget(w)
        td = self.rows("SELECT s.subject_id, r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                       "WHERE r.student_id=? AND s.date=?", (uid, today()))
        c = Card()
        c.add_widget(lbl("Today's attendance", 16, bold=True))
        if not td:
            c.add_widget(lbl('No attendance has been marked yet today.', 13, MU))
        for r in td:
            c.add_widget(row(lbl(self.sname(r["subject_id"]), 14, TX, True), lbl(ST_TXT[r["status"]], 14, ST_COL[r["status"]], True, "right", 80), h=28))
        g.add_widget(c)
        self.subject_card(g, uid)
        dd = {}
        for d, s in self.db("SELECT s.date, r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?", (uid,)):
            dd.setdefault(d, set()).add(s)
        ld = set()
        for fd, td_ in self.db("SELECT from_date,to_date FROM leave_requests WHERE student_id=? AND status='approved'", (uid,)):
            d, e = dt.date.fromisoformat(fd), dt.date.fromisoformat(td_)
            while d <= e and len(ld) < 800:
                ld.add(d.isoformat())
                d += dt.timedelta(days=1)

        def colfn(k):
            s = dd.get(k)
            s = ("A" if "A" in s else "P" if "P" in s else "L") if s else ("L" if k in ld else None)
            return ST_COL.get(s)
        self.cal_card(g, "", colfn, None, 'Green = Present   Red = Absent   Orange = Leave')

    def subject_card(self, g, uid):
        per = {}
        for sid, s, n in self.db("SELECT s.subject_id,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                                 "WHERE r.student_id=? GROUP BY s.subject_id,r.status", (uid,)):
            per.setdefault(sid, {})[s] = n
        if not per or set(per) <= {DEFAULT_SUB}:      # no subjects in Code Nexus: nothing to split
            return
        c = Card()
        c.add_widget(lbl("Subject-wise attendance", 16, bold=True))
        for sid, v in per.items():
            tp, ta, tl, tt, ppc = self.mkstat(v.get("P", 0), v.get("A", 0), v.get("L", 0))
            c.add_widget(row(lbl(self.sname(sid), 14, TX, True), lbl("%d%%" % ppc, 14, NO if ppc < self.thr else OK, True, "right", 56), h=28))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (tp, ta, tl, tt), 12, MU))
            b = Bar(size_hint_y=None, height=dp(8), col=list(NO if ppc < self.thr else OK))
            grow(b, ppc)
            c.add_widget(b)
        g.add_widget(c)

    # ---------- student: history / subjects / leave ----------
    def s_history(self, g):
        uid, hf = self.uid(), self.hf
        c = Card()
        c.add_widget(lbl("Attendance History", 17, bold=True))
        c.add_widget(lbl("Status", 12, MU))
        c.add_widget(spin(hf, "st", ["All", "Present", "Absent", "Leave"], self.refresh))
        c.add_widget(row(tin(hf, "d1", 'From (YYYY-MM-DD)'), tin(hf, "d2", 'To (YYYY-MM-DD)')))
        c.add_widget(btn('Apply filter', self.refresh))
        g.add_widget(c)
        d1, d2 = (hf["d1"] if vd(hf["d1"]) else None), (hf["d2"] if vd(hf["d2"]) else None)
        p, a, l, t, pc = self.stat(uid, None, d1, d2)
        c = Card()
        c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (p, a, l, t), 13, MU, True))
        col = NO if pc < self.thr and t else OK
        c.add_widget(lbl("Percentage: %s" % pstr(pc, t), 16, col, True))
        b = Bar(size_hint_y=None, height=dp(10), col=list(col))
        grow(b, pc)
        c.add_widget(b)
        g.add_widget(c)
        sql = "SELECT s.date,r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE r.student_id=?"
        args = [uid]
        for cond, v in ((" AND s.date>=?", d1), (" AND s.date<=?", d2), (" AND r.status=?", {"Present": "P", "Absent": "A", "Leave": "L"}.get(hf["st"]))):
            if v:
                sql += cond
                args.append(v)
        rs = self.rows(sql + " ORDER BY s.date DESC LIMIT 150", args)
        if not rs:
            c = Card()
            c.add_widget(lbl('No records found.', 14, MU))
            g.add_widget(c)
        for r in rs:
            c = Card()
            c.add_widget(row(lbl(dt.date.fromisoformat(r["date"]).strftime("%d %b %Y, %a"), 14, TX, True),
                             lbl(ST_TXT[r["status"]], 14, ST_COL[r["status"]], True, "right", 80), h=28))
            g.add_widget(c)

    def s_leave(self, g):
        c = Card()
        c.add_widget(lbl('Apply for leave', 16, bold=True))
        f, t, r = inp('From (YYYY-MM-DD)', today()), inp('To (YYYY-MM-DD)', today()), inp("Reason")
        for w in (f, t, r):
            c.add_widget(w)

        def send():
            if not (vd(f.text) and vd(t.text)) or t.text < f.text or not r.text.strip():
                return msg('Attention', 'Fill in valid dates (YYYY-MM-DD) and a reason.')
            row_ = dict(id=str(uuid.uuid4()), student_id=self.uid(), from_date=f.text, to_date=t.text, reason=r.text.strip(),
                        status="pending", decided_by=None, created_at=now_iso(), updated_at=now_iso())
            self.d.put("leave_requests", [row_])
            self.d.enqueue("insert", "leave_requests", {k: row_[k] for k in wcols("leave_requests")})
            self.sync_now()
            msg("Done", 'Request sent (it will be sent automatically later if you are offline).')
            self.refresh()
        c.add_widget(btn('Send request', send))
        g.add_widget(c)
        for x in self.rows("SELECT * FROM leave_requests WHERE student_id=? ORDER BY created_at DESC", (self.uid(),)):
            c = Card()
            c.add_widget(row(lbl("%s  to  %s" % (x["from_date"], x["to_date"]), 14, TX, True),
                             lbl(x["status"].upper(), 13, {"pending": LV, "approved": OK, "rejected": NO}[x["status"]], True, "right", 100), h=30))
            c.add_widget(lbl(x["reason"], 13, MU))
            g.add_widget(c)

    # ---------- profile (teacher + student) ----------
    def profile(self, g):
        u = self.me
        c = Card()
        c.add_widget(row(self.avatar(u, 90), btn('Change photo', lambda: self.pick_photo(self.new_photo), "muted", pos_hint={"center_y": .5}), h=96))
        c.add_widget(lbl(fullname(u), 20, TX, True))
        lines = ["Email: " + (u.get("email") or "-"), "Mobile: " + (u.get("mobile") or "-")]
        if self.staff():
            lines += ["Role: " + u["role"].title(), "Department: " + (u.get("department") or "-"),
                      "Employee ID: " + (u.get("employee_id") or "-")]
        else:
            m = self.d.one("SELECT full_name FROM profiles WHERE id=?", (u.get("mentor_id"),)) if u.get("mentor_id") else None
            lines += ["Enrollment: " + (u.get("roll") or "-"), "College: " + (u.get("college_name") or "-"), "Class: " + glabel(u),
                      "Mentor: " + (m["full_name"] if m else "-")]
            p, a, l, t, pc = self.stat(u["id"])
            lines.append("Attendance: %s  (P %d / A %d / L %d)" % (pstr(pc, t), p, a, l))
        for x in lines:
            c.add_widget(lbl(x, 14, MU))
        g.add_widget(c)
        # edit profile
        pe = self.__dict__.setdefault("pe", {})
        if pe.get("uid") != u["id"]:
            pe.clear()
            pe.update(uid=u["id"], first=u.get("first_name", ""), last=u.get("last_name", ""), mobile=u.get("mobile", ""))
        c = Card()
        c.add_widget(lbl('Edit profile', 16, bold=True))
        fld(c, pe, 'First name', "first")
        fld(c, pe, "Surname", "last")
        fld(c, pe, "Mobile number", "mobile", num=True)
        c.add_widget(btn("Save profile", self.save_profile))
        g.add_widget(c)
        if not self.staff():
            self.parent_card(g, u["id"])
        # change password
        pw = self.__dict__.setdefault("pwst", dict(o="", n="", n2=""))
        c = Card()
        c.add_widget(lbl('Change password', 16, bold=True))
        for k, h in (("o", 'Old password'), ("n", 'New password (6+ characters)'), ("n2", 'Confirm new password')):
            c.add_widget(tin(pw, k, h, password=True))
        c.add_widget(btn("Update", self.change_pw))
        g.add_widget(c)
        self.settings_card(g)
        self.sync_card(g)

    def save_profile(self):
        pe, u = self.pe, self.me
        if not pe["first"].strip() or not pe["last"].strip() or not valid_mobile(pe["mobile"].strip()):
            return msg('Attention', 'Enter a valid name, surname and 10-digit mobile number.')
        full = ("%s %s" % (pe["first"].strip(), pe["last"].strip())).strip()
        vals = dict(first_name=pe["first"].strip(), last_name=pe["last"].strip(), full_name=full, mobile=pe["mobile"].strip())
        self.db("UPDATE profiles SET first_name=?,last_name=?,full_name=?,mobile=?,updated_at=? WHERE id=?",
                (vals["first_name"], vals["last_name"], full, vals["mobile"], now_iso(), u["id"]))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + u["id"], "values": vals})
        self.sync_now()
        self.load_me()
        msg("Done", 'Profile saved.')
        self.refresh()

    def change_pw(self):
        pw = self.pwst
        if not pw["o"]:
            return msg('Attention', 'Enter your old password.')
        if len(pw["n"]) < 6 or pw["n"] != pw["n2"]:
            return msg('Attention', 'New password must be 6+ characters and both entries must match.')
        o, n, em = pw["o"], pw["n"], self.me["email"]

        def work():
            self.api.login(em, o)
            self.api.set_password(n)

        def ok(_):
            pw.update(o="", n="", n2="")
            msg("Done", 'Password changed.')
            self.refresh()
        self.net(work, ok, 'Changing password...')

    def settings_card(self, g):
        modes = {"total": 'Leave counts in the total (P / (P+A+L))', "excluded": 'Leave not counted (old way: P / (P+A))'}
        st = self.__dict__.setdefault("setst", {})
        st["lm"] = modes[self.lm]
        st["thr"] = str(self.thr)
        st["every"] = "%d sec" % self.every
        c = Card()
        c.add_widget(lbl("Settings", 16, bold=True))
        c.add_widget(lbl('How attendance percentage is calculated', 12, MU))
        c.add_widget(spin(st, "lm", list(modes.values()), lambda: (self.d.kset("lm", [k for k, v in modes.items() if v == st["lm"]][0]),
                                                                  setattr(self, "lm", [k for k, v in modes.items() if v == st["lm"]][0]))))
        c.add_widget(lbl("Low attendance warning (%)", 12, MU))
        c.add_widget(spin(st, "thr", ["60", "65", "70", "75", "80", "85"], lambda: (self.d.kset("thr", st["thr"]), setattr(self, "thr", int(st["thr"])))))
        c.add_widget(lbl("Auto sync interval", 12, MU))
        c.add_widget(spin(st, "every", ["15 sec", "30 sec", "60 sec", "300 sec"], lambda: self.set_every(int(st["every"].split()[0]))))
        g.add_widget(c)

    def set_every(self, n):
        if n == self.every:
            return
        self.every = n
        self.d.kset("every", n)
        self.timer.cancel()
        self.timer = Clock.schedule_interval(self.tick, n)

    def sync_card(self, g):
        n = self.d.pending()
        col = {"online": OK, "synced": OK, "syncing": AC, "offline": MU, "failed": NO}[self.status]
        c = Card()
        c.add_widget(lbl("Cloud Sync (Supabase)", 16, bold=True))
        c.add_widget(lbl('Status: %s   |   Pending uploads: %d' % ({"online": "Online", "synced": "Synced", "syncing": "Syncing...", "offline": "Offline", "failed": "Sync Failed"}[self.status], n), 13, col, True))
        c.add_widget(lbl(self.sync_msg or 'Not synced yet', 12, MU))
        errs = self.rows("SELECT * FROM sync_errors ORDER BY id DESC LIMIT 3")
        for e in errs:
            c.add_widget(lbl("! %s: %s" % (e["what"], e["err"]), 12, NO))
        c.add_widget(btn('Sync now', lambda: (self.sync_now(), self.toast('Sync started...', AC))))
        if errs:
            c.add_widget(btn('Clear errors', lambda: (self.db("DELETE FROM sync_errors"), self.refresh()), "ghost"))
        c.add_widget(btn('View error log', self.show_log, "plain"))
        c.add_widget(lbl("Code Nexus v%s   |   Server: %s" % (APP_VERSION, SUPABASE_URL.split("//")[-1].split(".")[0]), 11, MU, align="center"))
        g.add_widget(c)

    def show_log(self):
        try:
            with open(os.path.join(self.user_data_dir, "error.log"), encoding="utf-8") as f:
                t = f.read()[-3500:]
        except Exception:
            t = ""
        info("Error log", t or 'No errors.')

    # ---------- teacher: home ----------
    def state_from_class(self, c, batch=""):
        st = new_state()
        st["inst"], st["sec"], st["batch"] = c["kind"], c["section"], batch or "All"
        if c["kind"] == "college":
            if c["branch"] in BRANCHES:
                st["branch"] = c["branch"]
            else:
                st["branch"], st["branch_o"] = "Other", c["branch"]
            st["year"], st["sem"] = c["year"], c["semester"]
        else:
            st["cls"] = str(c["branch"]).replace("Class ", "", 1)
        return st

    def avg_all(self):
        m = {}
        for sid, s, n in self.db("SELECT student_id,status,COUNT(*) FROM attendance_records GROUP BY student_id,status"):
            m.setdefault(sid, {})[s] = n
        pcs = [x[4] for x in (self.mkstat(v.get("P", 0), v.get("A", 0), v.get("L", 0)) for v in m.values()) if x[3]]
        return sum(pcs) / len(pcs) if pcs else 0

    def t_home(self, g):
        u = self.me
        self.hero(g, u, 'Welcome', fullname(u), "Code Nexus teacher")
        r = dict(self.db("SELECT r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE s.date=? GROUP BY r.status", (today(),)))
        ns = self.db("SELECT COUNT(*) FROM students")[0][0]
        ses = self.db("SELECT COUNT(*) FROM attendance_sessions WHERE date=?", (today(),))[0][0]
        grid = GridLayout(cols=2, size_hint_y=None, height=dp(270), spacing=dp(10))
        for v, t, col in ((ns, "Registered students", TX), (ses, 'Classes taken today', AC), (r.get("P", 0), 'Present today', OK),
                          (r.get("A", 0), 'Absent today', NO), (r.get("L", 0), 'On leave today', LV), ("%.1f%%" % self.avg_all(), "Average attendance", AC)):
            p = Panel(orientation="vertical", padding=dp(14), spacing=dp(2))
            p.add_widget(lbl(v, 28, col, True))
            p.add_widget(lbl(t, 13, MU))
            grid.add_widget(p)
        g.add_widget(grid)
        rs = self.rows("SELECT s.id AS sid,s.date,s.subject_id,s.batch,c.kind,c.branch,c.year,c.semester,c.section FROM attendance_sessions s JOIN classes c ON c.id=s.class_id "
                       "ORDER BY s.date DESC, s.updated_at DESC LIMIT 6")
        c = Card()
        c.add_widget(lbl("Recent attendance", 16, bold=True))
        if not rs:
            c.add_widget(lbl('No attendance taken yet. Start from the Attendance tab.', 13, MU))
        for x in rs:
            cnt = dict(self.db("SELECT status,COUNT(*) FROM attendance_records WHERE session_id=? GROUP BY status", (x["sid"],)))
            c.add_widget(row(lbl("%s  |  %s" % (dt.date.fromisoformat(x["date"]).strftime("%d %b"), self.sname(x["subject_id"])), 14, TX, True),
                             small("Edit", lambda sid=x["sid"]: self.open_session(sid), "ghost", 60), h=34))
            c.add_widget(lbl(class_label(dict(x, semester=x["semester"]), x["batch"]), 12, MU))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d" % (cnt.get("P", 0), cnt.get("A", 0), cnt.get("L", 0)), 12, AC, True))
        g.add_widget(c)
        self.t_cal(g)

    def open_session(self, sid):
        s = self.d.one("SELECT * FROM attendance_sessions WHERE id=?", (sid,))
        c = self.d.one("SELECT * FROM classes WHERE id=?", (s["class_id"],)) if s else None
        if not c:
            return
        self.att_init(s["date"])
        self.att["manual"] = True
        k = branch_key(c["branch"])[0]
        self.att["br"] = BRANCH_ORDER[k] if k < len(BRANCH_ORDER) else "Other"
        self.att["yr"] = c["year"] if c["year"] in YEARS else "All"
        self.tab, self.sub = 1, None
        self.paint_nav()
        self.show(self.t_mark, anim=False)

    def t_cal(self, g):
        y, m = self.cm
        pre = "%04d-%02d-" % (y, m)
        agg = {}
        for d, s, n in self.db("SELECT s.date,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                               "WHERE s.date LIKE ? GROUP BY s.date,r.status", (pre + "%",)):
            agg.setdefault(d, {})[s] = n

        def colfn(k):
            v = agg.get(k)
            if not v:
                return None
            t = v.get("P", 0) + v.get("A", 0)
            pc = v.get("P", 0) * 100 / t if t else 50
            return OK if pc >= 75 else LV if pc >= 50 else NO
        self.cal_card(g, "Attendance Calendar", colfn, self.day_info,
                      'Green: 75%+ present   Orange: 50-75%   Red: below 50%   Grey: no attendance taken.\nTap a day to see its details.')

    def day_info(self, k):
        ss = self.rows("SELECT s.id AS sid,s.subject_id,s.batch,c.kind,c.branch,c.year,c.semester,c.section FROM attendance_sessions s JOIN classes c ON c.id=s.class_id WHERE s.date=? ORDER BY c.branch,c.year,c.section", (k,))
        title = dt.date.fromisoformat(k).strftime("%d %B %Y, %A")
        if not ss:
            return msg(title, 'No attendance was taken on this day.')
        out = []
        for x in ss:
            rs = self.rows("SELECT r.status,p.full_name,s.enrollment FROM attendance_records r JOIN profiles p ON p.id=r.student_id JOIN students s ON s.id=r.student_id WHERE r.session_id=?", (x["sid"],))
            n = lambda z: sum(1 for r in rs if r["status"] == z)
            out.append("%s\n%s\nPresent %d | Absent %d | Leave %d" % (self.sname(x["subject_id"]), class_label(x, x["batch"]), n("P"), n("A"), n("L")))
            ab = ["%s (%s)" % (r["full_name"], r["enrollment"]) for r in rs if r["status"] == "A"]
            if ab:
                out.append("Absent: " + ", ".join(ab))
            out.append("")
        info(title, "\n".join(out))

    # ---------- teacher: attendance (Hazri) ----------
    def paint(self, btns, cur):
        for v, b in btns.items():
            on = v == cur
            b.bg = list(ST_COL[v] if on else GR)
            b.color = WHITE if on else MU

    def att_students(self):
        return self.students(all_state())

    def att_init(self, day=None):
        day = day or today()
        base = dict(self.db("SELECT r.student_id, r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                            "WHERE s.date=? AND s.subject_id=?", (day, DEFAULT_SUB)))
        lv = {x[0] for x in self.db("SELECT student_id FROM leave_requests WHERE status='approved' AND from_date<=? AND to_date>=?", (day, day))}
        self.att = dict(day=day, br="CSE", yr="All", pend={}, base=base, lv=lv, saved=bool(base), manual=False)

    def att_today(self):
        self.att_init()
        self.refresh()

    @staticmethod
    def in_branch(s, br):
        if br == "All":
            return True
        k = branch_key(s["branch"])[0]
        return k == len(BRANCH_ORDER) if br == "Other" else k == branch_key(br)[0]

    def upd(self):
        a = self.att
        n = sum(1 for s in self.studs if a["pend"].get(s["id"]))
        self.cnt.text = "Showing %d  |  Marked: %d / %d  |  %s" % (len(self.vis), n, len(self.studs), 'Saved' if a["saved"] else 'NOT saved yet')
        self.cnt.color = OK if a["saved"] else LV

    def setm(self, sid, v):
        a = self.att
        a["pend"][sid] = v
        a["saved"] = False
        self.paint(self.mw[sid], v)
        self.upd()

    def markall(self, v):
        for s in self.vis:
            self.setm(s["id"], v)

    # ---------- daily attendance text file (phone storage / today attendance) ----------
    def day_text(self, day):
        """Text for one day: all students of that day, grouped CSE > AI/ML > DS > EC > EX and 1st > 4th year."""
        rs = self.rows("SELECT DISTINCT r.student_id, r.status, p.full_name, p.first_name, p.last_name, s.enrollment AS roll, c.branch, c.year FROM attendance_records r "
                       "JOIN attendance_sessions x ON x.id=r.session_id JOIN profiles p ON p.id=r.student_id JOIN students s ON s.id=r.student_id "
                       "JOIN classes c ON c.id=s.class_id WHERE x.date=?", (day,))
        if not rs:
            return ""
        rs.sort(key=lambda r: (branch_key(r["branch"]), year_rank(r["year"]), len(r["roll"] or ""), r["roll"] or "", fullname(r)))
        n = lambda z: sum(1 for r in rs if r["status"] == z)
        L = ["=" * 34, "CODE NEXUS - JIT BORAWAN", "Attendance: " + dt.date.fromisoformat(day).strftime("%d %B %Y, %A"), "=" * 34,
             "Present: %d | Absent: %d | Leave: %d | Total: %d" % (n("P"), n("A"), n("L"), len(rs))]
        last, i = None, 0
        for r in rs:
            key = (branch_key(r["branch"]), r["year"])
            if key != last:
                L += ["", "--- %s | %s Year ---" % (r["branch"], r["year"])]
                last, i = key, 0
            i += 1
            L.append("%d. %s (%s) - %s" % (i, fullname(r), r["roll"], ST_TXT.get(r["status"], r["status"])))
        L.append("")
        return "\n".join(L)

    def day_file_store(self, name, text):
        """Create / overwrite Documents/today attendance/<name> (text=None deletes it). Returns the shown path or ''."""
        rel = "Documents/" + DAY_FOLDER + "/"
        try:
            from jnius import autoclass
            if autoclass("android.os.Build$VERSION").SDK_INT >= 29:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                cr = act.getContentResolver()
                base = autoclass("android.provider.MediaStore$Files").getContentUri("external")
                uri = None
                cur = cr.query(base, ["_id"], "_display_name=? AND relative_path=?", [name, rel], None)
                try:
                    if cur is not None and cur.moveToFirst():
                        uri = autoclass("android.content.ContentUris").withAppendedId(base, cur.getLong(0))
                finally:
                    if cur is not None:
                        cur.close()
                if text is None:
                    if uri is not None:
                        cr.delete(uri, None, None)
                    return ""
                if uri is None:
                    cv = autoclass("android.content.ContentValues")()
                    cv.put("_display_name", name)
                    cv.put("mime_type", "text/plain")
                    cv.put("relative_path", rel)
                    uri = cr.insert(base, cv)
                os_ = cr.openOutputStream(uri, "wt")
                os_.write(bytearray(text.encode("utf-8")))
                os_.close()
                return rel + name
        except Exception as e:
            log(e, "dayfile-mediastore")
        for folder in ("/storage/emulated/0/Documents", os.path.join(self.user_data_dir, "exports")):
            try:
                d = os.path.join(folder, DAY_FOLDER)
                path = os.path.join(d, name)
                if text is None:
                    if os.path.exists(path):
                        os.remove(path)
                    return ""
                os.makedirs(d, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                return path
            except Exception:
                continue
        return ""

    def write_day_file(self, day):
        """Rebuild the text file of `day` from the database (one file per day). Never raises."""
        try:
            return self.day_file_store("attendance_%s.txt" % day, self.day_text(day) or None)
        except Exception as e:
            log(e, "dayfile")
            return ""

    def save_att(self):
        a, studs = self.att, self.studs
        miss = [s for s in studs if not a["pend"].get(s["id"])]
        if miss:
            def fill():
                for s in miss:
                    a["pend"][s["id"]] = "A"
                self.do_save()
            return ask('Some students are not marked', '%d student(s) are not marked yet. Mark them Absent and save?' % len(miss), fill, 'Absent and Save', "warn")
        self.do_save()

    def do_save(self):
        a, studs, day = self.att, self.studs, self.att["day"]
        self.ensure_default_subject()
        ts, by_class = now_iso(), {}
        for s in studs:
            by_class.setdefault(s["class_id"], []).append(s)
        for cid, ss in by_class.items():
            sid = sid_for(cid, DEFAULT_SUB, day, "")
            old = self.d.one("SELECT id FROM attendance_sessions WHERE class_id=? AND subject_id=? AND date=? AND batch=?", (cid, DEFAULT_SUB, day, ""))
            if old and old["id"] != sid:
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (old["id"],))])
                self.d.delete_ids("attendance_sessions", [old["id"]])
            self.d.put("attendance_sessions", [dict(id=sid, class_id=cid, subject_id=DEFAULT_SUB, date=day, batch="", marked_by=self.uid(), created_at=ts, updated_at=ts)])
            recs = [dict(id=rid_for(sid, s["id"]), session_id=sid, student_id=s["id"], status=a["pend"][s["id"]], remark="", marked_by=self.uid(),
                         created_at=ts, updated_at=ts) for s in ss]
            self.d.put("attendance_records", recs)
            self.d.enqueue("rpc", "save_attendance", dict(p_session_id=sid, p_class_id=cid, p_subject_id=DEFAULT_SUB, p_date=day, p_batch="",
                                                          p_records=[{"id": r["id"], "student_id": r["student_id"], "status": r["status"], "remark": ""} for r in recs]))
        a["saved"] = True
        a["base"] = {k: v for k, v in a["pend"].items() if v}
        self.sync_now()
        fpath = self.write_day_file(day)
        msg("Saved", 'Attendance saved (%d students).' % len(studs) +
            (('\nText file: ' + fpath) if fpath else '\n(Text file could not be saved - allow storage permission.)') +
            ("" if self.status in ("synced", "syncing", "online") else '\nIt will upload to the cloud when internet returns.'))
        self.after_att_wa(day)
        self.refresh()

    def delete_att(self):
        a = self.att

        def go():
            day = a["day"]
            ids = [r[0] for r in self.db("SELECT id FROM attendance_sessions WHERE date=? AND subject_id=?", (day, DEFAULT_SUB))]
            for sid in ids:
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (sid,))])
            self.d.delete_ids("attendance_sessions", ids)
            for i in range(0, len(ids), 40):
                self.d.enqueue("delete", "attendance_sessions", {"q": "id=in.(%s)" % ",".join(ids[i:i + 40])})
            self.sync_now()
            self.write_day_file(day)
            a.update(pend={}, base={}, saved=False)
            self.refresh()
        ask("Delete attendance?", 'All attendance saved for %s will be deleted (from the cloud too).' % a["day"], go, "Delete")

    def t_mark(self, g):
        if not self.att or (self.att["day"] != today() and not self.att["manual"]):
            self.att_init()
        a = self.att
        studs = self.att_students()
        self.studs = studs
        if not studs:
            c = Card()
            c.add_widget(lbl('No students yet. Add students from the Students tab.', 14, MU))
            g.add_widget(c)
            return
        for s in studs:
            if s["id"] not in a["pend"]:
                a["pend"][s["id"]] = a["base"].get(s["id"]) or ("L" if s["id"] in a["lv"] else None)
        has_other = any(branch_key(s["branch"])[0] == len(BRANCH_ORDER) for s in studs)
        if a["br"] == "Other" and not has_other:
            a["br"] = "All"
        vis = [s for s in studs if self.in_branch(s, a["br"]) and (a["yr"] == "All" or s["year"] == a["yr"])]
        self.vis = vis
        c = Card()
        c.add_widget(lbl('Attendance', 18, bold=True))
        c.add_widget(lbl(dt.date.fromisoformat(a["day"]).strftime("%d %B %Y, %A"), 14, MU))
        self.cnt = lbl("", 13, MU, True)
        c.add_widget(self.cnt)
        c.add_widget(row(btn('All Present', lambda: self.markall("P"), "ok"), btn('All Absent', lambda: self.markall("A"), "danger")))
        c.add_widget(lbl('The All buttons mark only the students shown below.', 11, MU))
        c.add_widget(btn("Save Attendance", self.save_att))
        if a["saved"]:
            c.add_widget(btn('Delete attendance of this day', self.delete_att, "plaindanger"))
        if a["day"] != today():
            c.add_widget(btn('Go to today', self.att_today, "muted"))
        g.add_widget(c)
        self.seg(g, a, "br", ["All"] + BRANCH_ORDER + (["Other"] if has_other else []))
        self.seg(g, a, "yr", ["All"] + YEARS)
        if not vis:
            c = Card()
            c.add_widget(lbl('No students in this branch / year.', 14, MU))
            g.add_widget(c)
        self.mw = {}
        last = None
        for s in vis:
            key = (branch_key(s["branch"]), s["year"])
            if key != last:
                n = sum(1 for x in vis if (branch_key(x["branch"]), x["year"]) == key)
                g.add_widget(lbl("%s  |  %s Year  (%d)" % (s["branch"], s["year"], n), 15, AC, True))
                last = key
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX, True), h=30))
            btns = {v: RBtn(text=ST_TXT[v], font_size=sp(13)) for v in "PAL"}
            for v, b in btns.items():
                b.bind(on_release=lambda *_, sid=s["id"], v=v: self.setm(sid, v))
            self.mw[s["id"]] = btns
            self.paint(btns, a["pend"].get(s["id"]))
            c.add_widget(row(*btns.values()))
            g.add_widget(c)
        c = Card()
        c.add_widget(btn("Save Attendance", self.save_att))
        g.add_widget(c)
        self.upd()

    # ---------- teacher: students ----------
    def student_fields(self, c, st, edit=False):
        fld(c, st, 'First name', "name")
        fld(c, st, "Surname", "surname")
        fld(c, st, "Enrollment number", "roll")
        for w in class_fields(st, False, self.refresh):
            c.add_widget(w)
        if edit:
            c.add_widget(lbl("Email: " + st.get("email", ""), 13, MU))
        else:
            fld(c, st, "Email (student's login)", "email")
            fld(c, st, "Password (6+ characters)", "pw", password=True)

    def t_add_student(self, g):
        self.back_card(g)
        c = Card()
        c.add_widget(lbl('Add new student', 18, bold=True))
        self.student_fields(c, self.ns)
        c.add_widget(btn('+ Add student', self.add_student))
        g.add_widget(c)

    def t_students(self, g):
        sf = self.sf
        sf.setdefault("q", "")
        c = Card()
        c.add_widget(lbl("Students", 18, bold=True))
        c.add_widget(btn('+ Add new student', lambda: self.open_sub(self.t_add_student)))
        g.add_widget(c)
        self.selector(g, 'Apply filter', self.refresh, st=sf, sel="all",
                      extra=lambda: [lbl('Search (name / enrollment / email)', 12, MU), tin(sf, "q", "Search...")])
        studs = self.students(sf, sf["q"])
        c = Card()
        c.add_widget(lbl("Students (%d)" % len(studs), 16, bold=True))
        if len(studs) > 60:
            c.add_widget(lbl('Showing the first 60. Use filter or search to see more.', 12, MU))
        g.add_widget(c)
        for s in studs[:60]:
            ok_ = bool(s["is_active"])
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX if ok_ else MU, True), h=30))
            c.add_widget(lbl(s["email"] or "-", 12, MU))
            c.add_widget(lbl(glabel(s) + ("" if ok_ else "   [DISABLED]"), 12, AC if ok_ else NO, True))
            c.add_widget(row(btn("View", lambda sid=s["id"]: self.view_student(sid)), btn("Edit", lambda sid=s["id"]: self.edit_student(sid), "ghost")))
            c.add_widget(row(btn("Password", lambda u=s: self.reset_pw(u), "muted"),
                             btn("Disable" if ok_ else "Enable", lambda u=s: self.toggle_active(u), "warn"),
                             btn('Remove', lambda u=s: self.rm_student(u), "danger")))
            g.add_widget(c)

    def add_student(self):
        st = self.ns
        st["pw2"], st["role"] = st["pw"], "student"
        self.do_register(st, True)

    def get_avatar_async(self, sid):
        tried = self.__dict__.setdefault("av_try", set())
        if sid in tried:
            return
        tried.add(sid)
        self.bg(lambda: self.fetch_avatar(sid), lambda r, e: self.refresh() if self.sub else None)

    def view_student(self, sid):
        def page(g):
            self.back_card(g)
            s = self.d.one(SQ + " WHERE s.id=?", (sid,))
            if not s:
                c = Card()
                c.add_widget(lbl('Student not found (may have been deleted).', 14, MU))
                g.add_widget(c)
                return
            if not self.d.one("SELECT 1 FROM avatars WHERE id=?", (sid,)):
                self.get_avatar_async(sid)
            self.hero(g, s, "Student", fullname(s), "Enrollment %s" % s["roll"])
            c = Card()
            for x in ("Email: " + (s["email"] or "-"), "Mobile: " + (s["mobile"] or "-"), "College: " + (s["college_name"] or "-"), "Class: " + glabel(s),
                      "Account: " + ("Active" if s["is_active"] else "DISABLED")):
                c.add_widget(lbl(x, 14, MU))
            g.add_widget(c)
            p, a, l, t, pc = self.stat(sid)
            col = NO if pc < self.thr and t else OK
            c = Card()
            c.add_widget(lbl("Attendance: %s" % pstr(pc, t), 17, col, True))
            c.add_widget(lbl("Present %d  |  Absent %d  |  Leave %d  |  Total %d" % (p, a, l, t), 13, MU))
            b = Bar(size_hint_y=None, height=dp(10), col=list(col))
            grow(b, pc)
            c.add_widget(b)
            g.add_widget(c)
            self.subject_card(g, sid)
            self.student_extra(g, sid, s)
            c = Card()
            c.add_widget(row(btn("Edit", lambda: self.edit_student(sid), "ghost"), btn("Password", lambda: self.reset_pw(s), "muted")))
            c.add_widget(row(btn("Disable" if s["is_active"] else "Enable", lambda: self.toggle_active(s), "warn"), btn('Remove', lambda: self.rm_student(s), "danger")))
            g.add_widget(c)
            rs = self.rows("SELECT r.id,s.date,s.subject_id,r.status FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id "
                           "WHERE r.student_id=? ORDER BY s.date DESC LIMIT 40", (sid,))
            c = Card()
            c.add_widget(lbl("Attendance history (last 40)", 16, bold=True))
            if not rs:
                c.add_widget(lbl('No records yet.', 13, MU))
            g.add_widget(c)
            for r in rs:
                c = Card()
                c.add_widget(row(lbl("%s | %s" % (r["date"], self.sname(r["subject_id"])), 13, TX, True),
                                 lbl(ST_TXT[r["status"]], 13, ST_COL[r["status"]], True, "right", 70),
                                 small("Del", lambda rid=r["id"]: self.del_rec(rid), "danger", 46, height=dp(34)), h=34))
                g.add_widget(c)
        self.open_sub(page)

    def del_rec(self, rid):
        def go():
            self.d.delete_ids("attendance_records", [rid])
            self.d.enqueue("delete", "attendance_records", {"q": "id=eq." + rid})
            self.sync_now()
            self.refresh()
        ask("Record delete?", 'This one attendance record of the student will be deleted.', go, "Delete")

    def edit_student(self, sid):
        s = self.d.one(SQ + " WHERE s.id=?", (sid,))
        if not s:
            return
        c0 = self.d.one("SELECT * FROM classes WHERE id=?", (s["class_id"],))
        st = dict(self.state_from_class(c0, s["batch"]), name=s["first_name"], surname=s["last_name"], mobile=s["mobile"] or "", roll=s["roll"],
                  college_name=s["college_name"] or "", email=s["email"], sid=sid)

        def page(g):
            self.back_card(g)
            c = Card()
            c.add_widget(lbl('Edit student', 17, bold=True))
            self.student_fields(c, st, True)
            c.add_widget(btn("Save changes", lambda: self.save_student(st)))
            g.add_widget(c)
        self.open_sub(page)

    def save_student(self, st):
        if not st["name"].strip() or not st["surname"].strip():
            return msg('Attention', 'First name and surname are required.')
        if st["mobile"].strip() and not valid_mobile(st["mobile"].strip()):
            return msg('Attention', 'Mobile number must be 10 digits.')
        if not valid_enroll(st["roll"].strip()):
            return msg('Attention', 'Enrollment number must be 3-30 characters.')
        if st["inst"] == "college" and st["branch"] == "Other" and not st["branch_o"].strip():
            return msg('Attention', 'Enter your branch name.')
        sid = st["sid"]
        if self.d.one("SELECT 1 FROM students WHERE lower(enrollment)=lower(?) AND id<>?", (st["roll"].strip(), sid)):
            return msg("Duplicate", 'This enrollment number belongs to another student.')
        cid = self.ensure_class(st)
        batch = st["batch"] if st["inst"] == "college" and st["batch"] != "All" else ""
        full = ("%s %s" % (st["name"].strip(), st["surname"].strip())).strip()
        pv = dict(first_name=st["name"].strip(), last_name=st["surname"].strip(), full_name=full, mobile=st["mobile"].strip())
        sv = dict(enrollment=st["roll"].strip(), class_id=cid, batch=batch, college_name=st["college_name"].strip())
        self.db("UPDATE profiles SET first_name=?,last_name=?,full_name=?,mobile=?,updated_at=? WHERE id=?", (pv["first_name"], pv["last_name"], full, pv["mobile"], now_iso(), sid))
        self.db("UPDATE students SET enrollment=?,class_id=?,batch=?,college_name=?,updated_at=? WHERE id=?", (sv["enrollment"], cid, batch, sv["college_name"], now_iso(), sid))
        self.d.enqueue("patch", "profiles", {"q": "id=eq." + sid, "values": pv})
        self.d.enqueue("patch", "students", {"q": "id=eq." + sid, "values": sv})
        self.sync_now()
        self.sub, self.hz = None, False
        msg("Done", 'Student updated.')
        self.refresh()

    def reset_pw(self, s):
        def done(p):
            if len(p) < 6:
                return msg('Attention', 'Password must be at least 6 characters.')
            self.net(lambda: self.api.rpc("admin_set_password", {"p_id": s["id"], "p_password": p}),
                     lambda _: msg("Done", 'A new (temporary) password has been set for %s.\nThe student should login and change it in Profile.' % fullname(s)),
                     'Changing password...')
        prompt('New password', 'New password (6+ characters)', done)

    def toggle_active(self, s):
        on = not s["is_active"]

        def go():
            def ok(_):
                self.db("UPDATE profiles SET is_active=? WHERE id=?", (1 if on else 0, s["id"]))
                self.refresh()
            self.net(lambda: self.api.rpc("admin_set_active", {"p_id": s["id"], "p_active": on}), ok, 'Updating...')
        ask("Account %s?" % ("enable" if on else "disable"),
            "%s's account will be %s." % (fullname(s), 'enabled' if on else 'disabled (they cannot login)'), go, 'Yes', "warn")

    def rm_student(self, s):
        def go():
            def ok(_):
                sid = s["id"]
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE student_id=?", (sid,))])
                self.d.delete_ids("leave_requests", [r[0] for r in self.db("SELECT id FROM leave_requests WHERE student_id=?", (sid,))])
                self.d.delete_ids("students", [sid])
                self.d.delete_ids("profiles", [sid])
                self.d.delete_ids("avatars", [sid])
                self.sub, self.hz = None, False
                self.refresh()
            self.net(lambda: self.api.rpc("admin_delete_student", {"p_id": s["id"]}), ok, 'Removing student...')
        ask('Remove student?', '%s and all their attendance will be deleted forever. This cannot be undone.' % fullname(s), go, "Delete")

    # ---------- teacher: report ----------
    def stat_map(self, sub=None, d1=None, d2=None):
        sql = "SELECT r.student_id,r.status,COUNT(*) FROM attendance_records r JOIN attendance_sessions s ON s.id=r.session_id WHERE 1=1"
        a = []
        for cond, v in ((" AND s.subject_id=?", sub), (" AND s.date>=?", d1), (" AND s.date<=?", d2)):
            if v:
                sql += cond
                a.append(v)
        m = {}
        for sid, s, n in self.db(sql + " GROUP BY r.student_id,r.status", a):
            m.setdefault(sid, {})[s] = n
        return m

    def show_rep(self):
        self.rep = True
        self.refresh()

    def report_data(self):
        rf, rs = self.rf, self.__dict__.setdefault("rs", all_state())
        d1, d2 = (rf["d1"] if vd(rf["d1"]) else None), (rf["d2"] if vd(rf["d2"]) else None)
        m = self.stat_map(None, d1, d2)
        return None, [(s, self.mkstat(m.get(s["id"], {}).get("P", 0), m.get(s["id"], {}).get("A", 0), m.get(s["id"], {}).get("L", 0)))
                      for s in self.students(rs, rf["q"])]

    def t_report(self, g):
        rf, rs = self.rf, self.__dict__.setdefault("rs", all_state())

        def extra():
            return [lbl("Date range (YYYY-MM-DD)", 12, MU), row(tin(rf, "d1", "From"), tin(rf, "d2", 'To')),
                    lbl('Student (name / enrollment / email)', 12, MU), tin(rf, "q", "Search...")]
        self.selector(g, "Report dikhao", self.show_rep, st=rs, sel="all", extra=extra)
        if not self.rep:
            return self.del_card(g)
        labels, data = self.report_data()
        c = Card()
        c.add_widget(lbl("Attendance Report", 18, bold=True))
        c.add_widget(lbl(glabel(rs), 13, AC, True))
        c.add_widget(lbl('%s to %s' % (rf["d1"] or 'start', rf["d2"] or 'till today'), 12, MU))
        done = [d for d in data if d[1][3]]
        avg = sum(d[1][4] for d in done) / len(done) if done else 0
        c.add_widget(lbl('Students: %d   |   Class average: %.1f%%   |   below %d%%: %d' % (len(data), avg, self.thr, sum(1 for d in done if d[1][4] < self.thr)), 13, MU))
        c.add_widget(row(btn("CSV export", lambda: self.export(data, "csv")), btn("PDF export", lambda: self.export(data, "pdf"), "ghost")))
        g.add_widget(c)
        if not data:
            c = Card()
            c.add_widget(lbl('No students match this filter.', 14, MU))
            g.add_widget(c)
        for s, (p, a, l, t, pc) in data[:150]:
            col = NO if pc < self.thr and t else OK
            c = Card()
            c.add_widget(row(lbl(s["roll"], 13, MU, True, w=96), lbl(fullname(s), 16, TX, True), lbl(pstr(pc, t), 15, col, True, "right", 78), h=30))
            c.add_widget(lbl("Present: %d   |   Absent: %d   |   Leave: %d   |   Total: %d" % (p, a, l, t), 13, MU))
            b = Bar(size_hint_y=None, height=dp(10), col=list(col))
            grow(b, pc)
            c.add_widget(b)
            g.add_widget(c)
        if len(data) > 150:
            c = Card()
            c.add_widget(lbl('Only the first 150 are shown on screen. Export gives all.', 12, MU))
            g.add_widget(c)
        self.del_card(g)

    def save_export(self, name, data, mime):
        try:
            from jnius import autoclass
            if autoclass("android.os.Build$VERSION").SDK_INT >= 29:
                act = autoclass("org.kivy.android.PythonActivity").mActivity
                cv = autoclass("android.content.ContentValues")()
                cv.put("_display_name", name)
                cv.put("mime_type", mime)
                cv.put("relative_path", "Download/")
                cr = act.getContentResolver()
                uri = cr.insert(autoclass("android.provider.MediaStore$Downloads").EXTERNAL_CONTENT_URI, cv)
                os_ = cr.openOutputStream(uri)
                os_.write(bytearray(data))
                os_.close()
                return "Download/" + name
        except Exception as e:
            log(e, "mediastore")
        for base in ("/storage/emulated/0/Download", os.path.join(self.user_data_dir, "exports")):
            try:
                os.makedirs(base, exist_ok=True)
                path = os.path.join(base, name)
                with open(path, "wb") as f:
                    f.write(data)
                return path
            except Exception:
                continue
        return ""

    def export(self, data, fmt):
        head = ["Enrollment", "Name", "Present", "Absent", "Leave", "Total Classes", "Percentage"]
        rows = [[s["roll"], fullname(s), p, a, l, t, pstr(pc, t)] for s, (p, a, l, t, pc) in data]
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "csv":
            name, blob, mime = "attendance_report_%s.csv" % stamp, make_csv(head, rows), "text/csv"
        else:
            name, mime = "attendance_report_%s.pdf" % stamp, "application/pdf"
            blob = make_pdf("Attendance Report", "%s | %s to %s" % (glabel(self.rs), self.rf["d1"] or "start", self.rf["d2"] or "today"),
                            head, rows, [1.3, 3, .9, .9, .9, 1.3, 1.3])
        path = self.save_export(name, blob, mime)
        msg('Done', 'File saved:\n' + path) if path else msg("Error", 'Could not save the file. Check the storage permission.')

    def del_card(self, g):
        mn = self.db("SELECT MIN(date) FROM attendance_sessions")[0][0] or today()
        old = (dt.date.today() - dt.timedelta(days=365)).isoformat()
        c = Card()
        c.add_widget(lbl('Delete old attendance', 16, bold=True))
        c.add_widget(lbl('Attendance of the selected class (and subject) in this date range will be deleted (from the cloud too). Default: older than 1 year.', 12, MU))
        f, t = inp('From (YYYY-MM-DD)', mn), inp('To (YYYY-MM-DD)', max(min(old, today()), mn))
        c.add_widget(f)
        c.add_widget(t)

        def go():
            if not (vd(f.text) and vd(t.text)) or t.text < f.text:
                return msg('Attention', "Enter valid dates (YYYY-MM-DD); the 'To' date must be after the 'From' date.")
            cids = {s["class_id"] for s in self.students(self.rs)}
            if not cids:
                return msg('No students', 'No class found for this filter.')
            sub = None
            sql = "SELECT id FROM attendance_sessions WHERE date BETWEEN ? AND ? AND class_id IN (%s)" % ",".join("?" * len(cids))
            a = [f.text, t.text] + list(cids)
            if sub:
                sql += " AND subject_id=?"
                a.append(sub)
            ids = [r[0] for r in self.db(sql, a)]
            if not ids:
                return msg('Nothing found', 'There is no attendance in this range.')
            ask('Delete permanently?', '%s\nFrom %s to %s, %d class session(s) will be deleted. This cannot be undone.' % (glabel(self.rs), f.text, t.text, len(ids)),
                lambda: self.do_del(ids))
        c.add_widget(btn('Delete', go, "danger"))
        g.add_widget(c)

    def do_del(self, ids):
        for i in range(0, len(ids), 40):
            ch = ids[i:i + 40]
            for sid in ch:
                self.d.delete_ids("attendance_records", [r[0] for r in self.db("SELECT id FROM attendance_records WHERE session_id=?", (sid,))])
            self.d.delete_ids("attendance_sessions", ch)
            self.d.enqueue("delete", "attendance_sessions", {"q": "id=in.(%s)" % ",".join(ch)})
        self.sync_now()
        self.hz = False
        msg('Done', 'Old attendance deleted.')
        self.refresh()

    # ---------- teacher: leaves ----------
    def t_leaves(self, g):
        self.back_card(g)
        rs = self.rows("SELECT l.*, p.full_name, s.enrollment AS roll, c.kind AS inst, c.branch, c.year, c.semester AS sem, c.section AS sec, c.branch AS cls, s.batch "
                       "FROM leave_requests l JOIN students s ON s.id=l.student_id JOIN profiles p ON p.id=l.student_id JOIN classes c ON c.id=s.class_id "
                       "ORDER BY CASE l.status WHEN 'pending' THEN 0 ELSE 1 END, l.created_at DESC LIMIT 100")
        if not rs:
            c = Card()
            c.add_widget(lbl('No leave requests.', 14, MU))
            g.add_widget(c)
        for r in rs:
            c = Card()
            c.add_widget(row(lbl(r["full_name"], 16, TX, True), lbl(r["status"].upper(), 13, {"pending": LV, "approved": OK, "rejected": NO}[r["status"]], True, "right", 100), h=30))
            c.add_widget(lbl("Enrollment %s  |  %s" % (r["roll"], glabel(r)), 12, MU))
            c.add_widget(lbl("%s  to  %s" % (r["from_date"], r["to_date"]), 13, AC, True))
            c.add_widget(lbl(r["reason"], 14))
            if r["status"] == "pending":
                c.add_widget(row(btn("Approve", lambda i=r["id"]: self.decide(i, True), "ok"), btn("Reject", lambda i=r["id"]: self.decide(i, False), "danger")))
            g.add_widget(c)

    def decide(self, lid, ok):
        r = self.d.one("SELECT * FROM leave_requests WHERE id=?", (lid,))
        if not r:
            return
        st = "approved" if ok else "rejected"
        self.db("UPDATE leave_requests SET status=?,decided_by=?,updated_at=? WHERE id=?", (st, self.uid(), now_iso(), lid))
        self.d.enqueue("patch", "leave_requests", {"q": "id=eq." + lid, "values": {"status": st, "decided_by": self.uid()}})
        nid = str(uuid.uuid4())
        self.d.enqueue("insert", "notifications", {"id": nid, "user_id": r["student_id"], "title": "Leave %s" % st,
                                                  "body": 'Leave request from %s to %s was %s.' % (r["from_date"], r["to_date"], st), "kind": "leave", "is_read": False})
        self.sync_now()
        self.paint_nav()
        self.refresh()

    # ---------- teacher: setup (subjects, classes, notice) ----------
    def t_setup(self, g):
        self.__dict__.setdefault("asg", dict(new_state()))
        self.__dict__.setdefault("nt", dict(all_state(), title="", body=""))
        asg = self.asg
        n = self.pending_leaves()
        c = Card()
        c.add_widget(btn("Leave requests%s" % (" (%d pending)" % n if n else ""), lambda: self.open_sub(self.t_leaves), "warn" if n else "ghost"))
        g.add_widget(c)
        c = Card()
        c.add_widget(lbl('Create class', 16, bold=True))
        for w in class_fields(asg, False, self.refresh):
            c.add_widget(w)
        c.add_widget(btn('Create class', self.add_class, "ghost"))
        g.add_widget(c)
        c = Card()
        c.add_widget(lbl("Classes", 17, bold=True))
        cl = self.rows("SELECT * FROM classes WHERE branch<>'All' ORDER BY branch,year,semester,section")
        if not cl:
            c.add_widget(lbl('No classes yet. They are created automatically when you add students.', 13, MU))
        for k in cl:
            ns_ = self.db("SELECT COUNT(*) FROM students WHERE class_id=?", (k["id"],))[0][0]
            c.add_widget(row(lbl("%s   [%d students]" % (class_label(dict(k, semester=k["semester"])), ns_), 13, TX, True),
                             small("Del", lambda x=k, n=ns_: self.del_class(x, n), "plaindanger", 50, height=dp(34)), h=34))
        g.add_widget(c)
        nt = self.nt
        self.selector(g, 'Send notice', self.send_notice, st=nt, sel="all",
                      extra=lambda: [lbl('Notice to class (choose class above)', 12, MU), tin(nt, "title", "Title"), tin(nt, "body", "Message")])

    def add_class(self):
        asg = self.asg
        if asg["inst"] == "college" and asg["branch"] == "Other" and not asg["branch_o"].strip():
            return msg('Attention', 'Enter your branch name.')
        if self.find_class(asg):
            return msg('Already exists', 'This class already exists.')
        self.ensure_class(asg)
        self.sync_now()
        self.refresh()

    def del_class(self, k, n):
        if n or self.db("SELECT COUNT(*) FROM attendance_sessions WHERE class_id=?", (k["id"],))[0][0]:
            return msg('Cannot delete', 'This class has students or attendance. Remove/move them first.')

        def go():
            self.d.delete_ids("class_subjects", [r[0] for r in self.db("SELECT id FROM class_subjects WHERE class_id=?", (k["id"],))])
            self.d.delete_ids("classes", [k["id"]])
            self.d.enqueue("delete", "classes", {"q": "id=eq." + k["id"]})
            self.sync_now()
            self.refresh()
        ask('Remove class?', 'This class will be deleted.', go, "Delete")

    def send_notice(self):
        nt = self.nt
        if not nt["title"].strip() or not nt["body"].strip():
            return msg('Attention', 'Enter a title and message.')
        studs = self.students(nt)
        if not studs:
            return msg('No students', 'There are no students in this class.')
        rows = [{"id": str(uuid.uuid4()), "user_id": s["id"], "title": nt["title"].strip(), "body": nt["body"].strip(), "kind": "message", "is_read": False}
                for s in studs]
        for i in range(0, len(rows), 100):
            self.d.enqueue("insert", "notifications", rows[i:i + 100])
        nt["title"] = nt["body"] = ""
        self.sync_now()
        msg('Sent', 'Notice sent to %d student(s) (later if you are offline).' % len(rows))
        self.refresh()


if __name__ == "__main__":
    CodeNexus().run()

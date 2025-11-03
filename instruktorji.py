# instruktorji.py — prijava dijakov, ki lahko poučujejo (instruktorji)
from flask import Flask, request, redirect, url_for, render_template_string, flash, session, send_file
import sqlite3, io, csv, os
from datetime import datetime

# --- Google Sheets ---
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1pRGqMwog7XULSUzz-P7nEBKptHxZ9yZ6DcVDyyzz-GA"  # <— zamenjaj s svojim ID
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_JSON_PATH = "/etc/secrets/service_account.json"
if not os.path.isfile(SERVICE_JSON_PATH):
    SERVICE_JSON_PATH = "service_account.json"

# Poverilnice za Google – v Renderju iz ENV, lokalno iz datoteke
import json

if os.getenv("SERVICE_ACCOUNT_JSON"):
    CREDS = Credentials.from_service_account_info(
        json.loads(os.environ["SERVICE_ACCOUNT_JSON"]),
        scopes=SCOPES,
    )
else:
    CREDS = Credentials.from_service_account_file(SERVICE_JSON_PATH, scopes=SCOPES)

_gc = gspread.authorize(CREDS)
_ss = _gc.open_by_key(SHEET_ID)


def ensure_ws(title, headers):
    try:
        ws = _ss.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = _ss.add_worksheet(title=title, rows=1000, cols=max(10, len(headers)))
        ws.append_row(headers)
    # če je prazen, dodaj glavo
    try:
        if not ws.get_all_values():
            ws.append_row(headers)
    except Exception:
        pass
    return ws

WS_TITLE = "Instruktorji"
HEADERS = ["Datum","Ime","Priimek","E-pošta","Razred","Oddelek","Predmeti (učitelj)"]
_ws = ensure_ws(WS_TITLE, HEADERS)

# --- Flask / baza ---
app = Flask(__name__)
app.secret_key = "instruktorji_secret"
DB_PATH = "instruktorji.db"
ADMIN_PASS = "instruktorji2025"

PREDMETI = [
    ("mat","Matematika"), ("fiz","Fizika"), ("ang","Angleščina"),
    ("inf","Informatika"), ("kem","Kemija"), ("nem","Nemščina"),
    ("slo","Slovenščina"), ("bio","Biologija"), ("zgod","Zgodovina"),
    ("geo","Geografija"), ("spa","Španščina"), ("ita","Italijanščina"),
    ("fra","Francoščina"),
]

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS instruktors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datum TEXT NOT NULL,
            ime TEXT NOT NULL,
            priimek TEXT NOT NULL,
            email TEXT NOT NULL,
            razred TEXT NOT NULL,
            oddelek TEXT NOT NULL,
            predmeti TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()

def add_vnos(ime, priimek, email, razred, oddelek, predmeti_str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO instruktors (datum, ime, priimek, email, razred, oddelek, predmeti)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"), ime, priimek, email, razred, oddelek, predmeti_str))
    con.commit()
    con.close()

def all_vnosi():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT id, datum, ime, priimek, email, razred, oddelek, predmeti FROM instruktors ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return rows

def delete_vnos(row_id:int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM instruktors WHERE id = ?", (row_id,))
    con.commit()
    con.close()

# --- HTML ---
BASE_CSS = """
<style>
  body{font-family:system-ui,sans-serif;background:#f5f5f5;margin:0;padding:20px;color:#222}
  .wrap{max-width:820px;margin:0 auto;background:#fff;padding:24px;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,.08)}
  h1{text-align:center;margin:0 0 12px}
  label{display:block;margin-top:12px;font-weight:600}
  input,select{width:100%;padding:8px;margin-top:4px;border-radius:6px;border:1px solid #ccc}
  fieldset{border:1px solid #ddd;border-radius:8px;margin-top:16px;padding:12px}
  legend{font-weight:bold}
  .subject{display:grid;grid-template-columns:24px 1fr;column-gap:8px;align-items:center;margin:6px 0}
  .subject input[type="checkbox"]{width:18px;height:18px;margin:0;justify-self:start;align-self:center}
  .teacher-tab{margin-left:calc(24px + 8px);margin-top:4px;display:none}
  .msg{padding:8px;border-radius:6px;margin-bottom:8px}
  .ok{background:#e8f6ec;border:1px solid #bfe7cc}
  .error{background:#fdecea;border:1px solid #f5c2c0}
  button{margin-top:20px;padding:10px 16px;border:none;background:#0077cc;color:#fff;border-radius:6px;cursor:pointer}
  button:hover{background:#005fa3}
  .hint{font-size:12px;color:#666}
  table{width:100%;border-collapse:collapse;margin-top:12px}
  th,td{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}
  th{background:#f0f0f0}
  .row-actions{display:flex;gap:6px}
  .btn{display:inline-block;padding:6px 10px;background:#0077cc;color:#fff;border:none;border-radius:6px;text-decoration:none;cursor:pointer}
  .btn.secondary{background:#666}
</style>
"""

FORM_HTML = f"""
<!doctype html><html lang="sl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prijava – Instruktorji</title>
{BASE_CSS}
</head><body><div class="wrap">
  <h1>Prijava – Instruktorji</h1>

  {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% if messages %}}{{% for cat, m in messages %}}
      <div class="msg {{'ok' if cat=='ok' else 'error'}}">{{{{ m }}}}</div>
    {{% endfor %}}{{% endif %}}
  {{% endwith %}}

  <form method="post" action="{{{{ url_for('oddaj') }}}}">
    <label>Ime <input name="ime" required></label>
    <label>Priimek <input name="priimek" required></label>
    <label>E-pošta <input type="email" name="email" required></label>

    <label>Razred
      <select name="razred" required>
        <option value="">— izberi —</option>
        <option>1. letnik</option><option>2. letnik</option>
        <option>3. letnik</option><option>4. letnik</option>
      </select>
    </label>

    <label>Oddelek
      <select name="oddelek" required>
        <option value="">— izberi —</option>
        <option>a</option><option>b</option><option>c</option>
        <option>d</option><option>e</option><option>f</option>
      </select>
    </label>

    <fieldset>
      <legend>Predmeti, ki jih lahko poučujem</legend>
      {{% for code, label in predmeti %}}
        <div class="subject">
          <input type="checkbox" id="chk_{{{{code}}}}" name="chk_{{{{code}}}}">
          <label for="chk_{{{{code}}}}">{{{{label}}}}</label>
        </div>
        <div class="teacher-tab" id="tab_{{{{code}}}}">
          <label>Učeči profesor {{{{label}}}} <input name="teacher_{{{{code}}}}"></label>
        </div>
      {{% endfor %}}
    </fieldset>

    <button type="submit">Oddaj prijavo</button>
    <p class="hint">Admin: <a href="{{{{ url_for('admin_login') }}}}">/admin</a></p>
  </form>
</div>

<script>
document.querySelectorAll('input[type="checkbox"][id^="chk_"]').forEach(cb => {{
  const code = cb.id.replace('chk_','');
  const tab = document.getElementById('tab_'+code);
  const input = tab.querySelector('input');
  const sync = () => {{
    const show = cb.checked;
    tab.style.display = show ? 'block' : 'none';
    if (show) input.setAttribute('required','required');
    else {{ input.removeAttribute('required'); input.value=''; }}
  }};
  cb.addEventListener('change', sync);
  sync();
}});
</script>

</body></html>
"""

LOGIN_HTML = f"""
<!doctype html><html lang="sl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin prijava</title>
{BASE_CSS}
</head><body><div class="wrap">
  <h1>Admin</h1>
  {{% with messages = get_flashed_messages(with_categories=true) %}}
    {{% if messages %}}{{% for cat, m in messages %}}<div class="msg error">{{{{ m }}}}</div>{{% endfor %}}{{% endif %}}
  {{% endwith %}}
  <form method="post">
    <label>Geslo <input type="password" name="password" required></label>
    <button class="btn">Prijava</button>
  </form>
</div></body></html>
"""

ADMIN_HTML = f"""
<!doctype html><html lang="sl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin – Instruktorji</title>
{BASE_CSS}
</head><body><div class="wrap">
  <h1>Pregled prijav – Instruktorji</h1>
  <p class="row-actions">
    <a class="btn" href="{{{{ url_for('export_csv') }}}}">Izvozi CSV</a>
    <a class="btn secondary" href="{{{{ url_for('admin_logout') }}}}">Odjava</a>
  </p>
  <table>
    <thead>
      <tr><th>#</th><th>Datum</th><th>Ime</th><th>Priimek</th><th>E-pošta</th><th>Razred</th><th>Oddelek</th><th>Predmeti (učitelj)</th><th>Akcije</th></tr>
    </thead>
    <tbody>
      {{% for r in rows %}}
      <tr>
        <td>{{{{ r[0] }}}}</td>
        <td>{{{{ r[1] }}}}</td>
        <td>{{{{ r[2] }}}}</td>
        <td>{{{{ r[3] }}}}</td>
        <td>{{{{ r[4] }}}}</td>
        <td>{{{{ r[5] }}}}</td>
        <td>{{{{ r[6] }}}}</td>
        <td>{{{{ r[7] }}}}</td>
        <td class="row-actions">
          <form method="post" action="{{{{ url_for('admin_delete', row_id=r[0]) }}}}" onsubmit="return confirm('Izbrišem vnos #{{'{{r[0]}}'}}?')">
            <button class="btn" style="background:#c62828">🗑️ Izbriši</button>
          </form>
        </td>
      </tr>
      {{% endfor %}}
    </tbody>
  </table>
</div></body></html>
"""

# --- Rute ---
@app.get("/")
def index():
    return render_template_string(FORM_HTML, predmeti=PREDMETI)

@app.post("/oddaj")
def oddaj():
    f = request.form
    ime = f.get("ime","").strip()
    priimek = f.get("priimek","").strip()
    email = f.get("email","").strip()
    razred = f.get("razred","").strip()
    oddelek = f.get("oddelek","").strip()

    if not all([ime, priimek, email, razred, oddelek]):
        flash("Izpolnite vsa obvezna polja (ime, priimek, e-pošta, razred, oddelek).", "error")
        return redirect(url_for("index"))

    pari = []
    for code, label in PREDMETI:
        if f.get(f"chk_{code}") == "on":
            teacher = f.get(f"teacher_{code}", "").strip()
            if not teacher:
                flash(f"Vnesite učitelja pri predmetu {label}.", "error")
                return redirect(url_for("index"))
            pari.append(f"{label} ({teacher})")

    predmeti_str = "; ".join(pari)
    # SQLite
    add_vnos(ime, priimek, email, razred, oddelek, predmeti_str)
    # Google Sheets
    try:
        _ws.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), ime, priimek, email, razred, oddelek, predmeti_str])
    except Exception as e:
        print("Sheets zapis ni uspel:", e)

    flash("Hvala! Prijava je shranjena.", "ok")
    return redirect(url_for("index"))

# --- Admin auth + panel + brisanje ---
def admin_ok():
    return session.get("admin_ok") is True

@app.get("/admin")
def admin_login():
    if admin_ok():
        return redirect(url_for("admin_panel"))
    return render_template_string(LOGIN_HTML)

@app.post("/admin")
def admin_do_login():
    if request.form.get("password") == ADMIN_PASS:
        session["admin_ok"] = True
        return redirect(url_for("admin_panel"))
    flash("Napačno geslo.", "error")
    return redirect(url_for("admin_login"))

@app.get("/admin/panel")
def admin_panel():
    if not admin_ok():
        return redirect(url_for("admin_login"))
    rows = all_vnosi()
    return render_template_string(ADMIN_HTML, rows=rows)

@app.post("/admin/delete/<int:row_id>")
def admin_delete(row_id:int):
    if not admin_ok():
        return redirect(url_for("admin_login"))
    delete_vnos(row_id)
    return redirect(url_for("admin_panel"))

@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

# --- Export CSV (podpičje za slovenski Excel) ---
@app.get("/export")
def export_csv():
    if not admin_ok():
        return redirect(url_for("admin_login"))
    rows = all_vnosi()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(["ID","Datum","Ime","Priimek","E-pošta","Razred","Oddelek","Predmeti (učitelj)"])
    for r in rows:
        w.writerow(list(r))
    data = buf.getvalue().encode("utf-8-sig")
    return send_file(io.BytesIO(data), mimetype="text/csv",
                     as_attachment=True, download_name="instruktorji.csv")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)

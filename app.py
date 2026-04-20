"""
app.py  ─  야구 카드 게임 (웹 배포용)
PythonAnywhere WSGI 진입점

구글 OAuth 로그인 + 유저별 컬렉션 (SQLite)
"""
import os, glob, random, sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, jsonify,
                   session, redirect, url_for, g)
from authlib.integrations.flask_client import OAuth

# ══════════════════════════════════════════════
#  경로 설정
# ══════════════════════════════════════════════
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR = os.path.join(BASE_DIR, 'static', 'cards')
DB_PATH   = os.path.join(BASE_DIR, 'instance', 'game.db')

os.makedirs(CARDS_DIR,                  exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH),   exist_ok=True)

# ══════════════════════════════════════════════
#  Flask 앱
# ══════════════════════════════════════════════
app = Flask(__name__)
app.secret_key                     = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['GOOGLE_CLIENT_ID']     = os.environ.get('GOOGLE_CLIENT_ID', '')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET', '')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# ══════════════════════════════════════════════
#  데이터베이스
# ══════════════════════════════════════════════
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            email       TEXT UNIQUE NOT NULL,
            name        TEXT,
            picture     TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS collections (
            id           TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL,
            card_id      TEXT,
            card_name    TEXT,
            team         TEXT,
            position     TEXT,
            rarity       TEXT NOT NULL,
            rarity_label TEXT NOT NULL,
            attempts     INTEGER NOT NULL,
            obtained_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()

init_db()

# ══════════════════════════════════════════════
#  게임 헬퍼
# ══════════════════════════════════════════════
RARITY_LABELS = {
    'hyper_rare': 'HYPER RARE',
    'ultra_rare': 'ULTRA RARE',
    'rare':       'RARE',
    'uncommon':   'UNCOMMON',
    'common':     'COMMON',
}

def get_rarity(attempts: int) -> str:
    if   attempts <= 2: return 'hyper_rare'
    elif attempts == 3: return 'ultra_rare'
    elif attempts == 4: return 'rare'
    elif attempts == 5: return 'uncommon'
    else:               return 'common'

def scan_cards():
    cards = []
    for fp in glob.glob(os.path.join(CARDS_DIR, '*.png')):
        stem  = os.path.splitext(os.path.basename(fp))[0]
        parts = stem.split('_')
        cards.append({
            'card_id':  stem,
            'name':     parts[0] if parts else '?',
            'team':     parts[1] if len(parts) > 1 else '',
            'position': parts[2] if len(parts) > 2 else '',
        })
    return cards

def check_sb(answer, guess):
    s = sum(g == a for g, a in zip(guess, answer))
    b = sum(g in answer for g in guess) - s
    return s, b

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            # API 요청이면 401, 일반 요청이면 로그인 페이지로
            if request.is_json or request.path.startswith('/game') or request.path.startswith('/collection'):
                return jsonify({'error': 'login_required'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════
#  인증 라우트
# ══════════════════════════════════════════════
@app.route('/login')
def login():
    if session.get('user_id'):
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/auth/google')
def auth_google():
    redirect_uri = url_for('auth_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/callback')
def auth_callback():
    try:
        token     = google.authorize_access_token()
        user_info = token.get('userinfo')
    except Exception:
        return redirect(url_for('login'))

    if not user_info:
        return redirect(url_for('login'))

    sub     = user_info['sub']
    email   = user_info.get('email', '')
    name    = user_info.get('name', '')
    picture = user_info.get('picture', '')

    db = get_db()
    db.execute("""
        INSERT INTO users (id, email, name, picture)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name    = excluded.name,
            picture = excluded.picture
    """, (sub, email, name, picture))
    db.commit()

    session.clear()
    session['user_id']      = sub
    session['user_name']    = name
    session['user_picture'] = picture
    session['user_email']   = email
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ══════════════════════════════════════════════
#  페이지 라우트
# ══════════════════════════════════════════════
@app.route('/')
@login_required
def index():
    return render_template('index.html',
        user_name=session.get('user_name', ''),
        user_picture=session.get('user_picture', ''),
    )

@app.route('/collection')
@login_required
def collection():
    return render_template('collection.html',
        user_name=session.get('user_name', ''),
        user_picture=session.get('user_picture', ''),
    )

# ══════════════════════════════════════════════
#  게임 API
# ══════════════════════════════════════════════
@app.route('/game/start', methods=['POST'])
@login_required
def start_game():
    session['answer']   = random.sample(range(1, 10), 3)
    session['attempts'] = 0
    session['history']  = []
    session.modified    = True
    return jsonify({'status': 'ok'})

@app.route('/game/guess', methods=['POST'])
@login_required
def guess():
    data    = request.json or {}
    g_input = data.get('guess')

    if not g_input or len(g_input) != 3:
        return jsonify({'error': '3자리 숫자를 입력하세요'}), 400
    if len(set(g_input)) != 3:
        return jsonify({'error': '중복 없는 숫자를 입력하세요'}), 400

    answer = session.get('answer')
    if not answer:
        return jsonify({'error': '게임을 먼저 시작해주세요'}), 400

    attempts            = int(session.get('attempts', 0)) + 1
    session['attempts'] = attempts
    session.modified    = True

    s, b = check_sb(answer, g_input)
    out  = (s == 0 and b == 0)

    history = session.get('history', [])
    history.append({'guess': g_input, 'strikes': s, 'balls': b, 'out': out})
    session['history'] = history

    result = {
        'strikes': s, 'balls': b, 'out': out,
        'attempts': attempts, 'history': history, 'win': False,
    }

    if s == 3:
        rarity    = get_rarity(attempts)
        all_cards = scan_cards()
        user_id   = session['user_id']
        now_str   = datetime.now().strftime('%Y%m%d%H%M%S%f')

        if all_cards:
            card      = random.choice(all_cards)
            entry_id  = f"{card['card_id']}_{now_str}"
            card_id   = card['card_id']
            card_name = card['name']
            team      = card['team']
            position  = card['position']
        else:
            entry_id  = f"empty_{now_str}"
            card_id   = ''
            card_name = '???'
            team      = ''
            position  = ''

        obtained_at = datetime.now().isoformat()
        db = get_db()
        db.execute("""
            INSERT INTO collections
              (id, user_id, card_id, card_name, team, position,
               rarity, rarity_label, attempts, obtained_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (entry_id, user_id, card_id, card_name, team, position,
              rarity, RARITY_LABELS[rarity], attempts, obtained_at))
        db.commit()

        entry = {
            'id': entry_id, 'card_id': card_id,
            'card_name': card_name, 'team': team, 'position': position,
            'rarity': rarity, 'rarity_label': RARITY_LABELS[rarity],
            'attempts': attempts, 'obtained_at': obtained_at,
        }
        result.update({'win': True, 'card': entry, 'answer': answer})

    return jsonify(result)

# ══════════════════════════════════════════════
#  컬렉션 API
# ══════════════════════════════════════════════
@app.route('/collection/data')
@login_required
def collection_data():
    user_id = session['user_id']
    db      = get_db()
    rows    = db.execute("""
        SELECT id, card_id, card_name, team, position,
               rarity, rarity_label, attempts, obtained_at
        FROM collections WHERE user_id=?
        ORDER BY obtained_at DESC
    """, (user_id,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/collection/stats')
@login_required
def collection_stats():
    user_id = session['user_id']
    db      = get_db()
    rows    = db.execute("""
        SELECT rarity, COUNT(*) as cnt
        FROM collections WHERE user_id=?
        GROUP BY rarity
    """, (user_id,)).fetchall()
    stats = {r['rarity']: r['cnt'] for r in rows}
    return jsonify({'total': sum(stats.values()), 'by_rarity': stats})

@app.route('/cards/pool')
@login_required
def cards_pool():
    return jsonify({'total': len(scan_cards()), 'cards': scan_cards()})

@app.route('/card-image/<path:card_id>')
@login_required
def card_image_check(card_id):
    img_path = os.path.join(CARDS_DIR, f'{card_id}.png')
    if os.path.exists(img_path):
        return jsonify({'exists': True, 'url': f'/static/cards/{card_id}.png'})
    return jsonify({'exists': False})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

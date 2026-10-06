from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, hashlib
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'pronostics.db')
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key')

CARD_PRICES = {'men': 100, 'women': 50, 'reserve': 25}
CARD_VALUES = {'men': 3, 'women': 2, 'reserve': 1}
CARD_LABELS = {'men': 'Hommes', 'women': 'Femmes', 'reserve': 'Équipe réserve'}


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def column_exists(conn, table, column):
    cols = conn.execute(f'PRAGMA table_info({table})').fetchall()
    return any(c['name'] == column for c in cols)


def init_db():
    conn = db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        points INTEGER NOT NULL DEFAULT 0,
        is_admin INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        winning_predictions INTEGER NOT NULL DEFAULT 0,
        free_packs INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        home TEXT NOT NULL,
        away TEXT NOT NULL,
        competition TEXT DEFAULT 'Match',
        match_date TEXT NOT NULL,
        home_score INTEGER,
        away_score INTEGER,
        status TEXT NOT NULL DEFAULT 'upcoming'
    );
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        match_id INTEGER NOT NULL,
        home_score INTEGER NOT NULL,
        away_score INTEGER NOT NULL,
        scored INTEGER NOT NULL DEFAULT 0,
        points_awarded INTEGER NOT NULL DEFAULT 0,
        UNIQUE(user_id, match_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(match_id) REFERENCES matches(id)
    );
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        image TEXT NOT NULL,
        price INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS inventory (
        user_id INTEGER NOT NULL,
        card_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        UNIQUE(user_id, card_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(card_id) REFERENCES cards(id)
    );
    CREATE TABLE IF NOT EXISTS pending_rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        points INTEGER NOT NULL,
        exact INTEGER NOT NULL DEFAULT 0,
        match TEXT NOT NULL,
        pack_earned INTEGER NOT NULL DEFAULT 0
    );
    ''')

    # Safe migrations for databases created with older versions.
    migrations = [
        ('users', 'winning_predictions', 'INTEGER NOT NULL DEFAULT 0'),
        ('users', 'free_packs', 'INTEGER NOT NULL DEFAULT 0'),
        ('predictions', 'points_awarded', 'INTEGER NOT NULL DEFAULT 0'),
        ('pending_rewards', 'pack_earned', 'INTEGER NOT NULL DEFAULT 0'),
    ]
    for table, column, definition in migrations:
        if not column_exists(conn, table, column):
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')

    # Automatic admin account on first launch.
    admin = conn.execute('SELECT id FROM users WHERE username=?', ('admin',)).fetchone()
    if not admin:
        admin_password = os.environ.get('ADMIN_PASSWORD', 'PronoPulseAdmin123!')
        conn.execute(
            'INSERT INTO users(username,password,is_admin,created_at) VALUES(?,?,1,?)',
            ('admin', hash_password(admin_password), datetime.now().isoformat())
        )

    conn.commit()
    conn.close()


def current_user():
    if 'user_id' not in session:
        return None
    conn = db()
    u = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
    conn.close()
    return u


def level(points):
    if points >= 400:
        return 'Diamant', 'diamond'
    if points >= 200:
        return 'Or', 'gold'
    if points >= 100:
        return 'Argent', 'silver'
    return 'Bronze', 'bronze'


def winner(h, a):
    if h == a:
        return 'draw'
    return 'home' if h > a else 'away'


def collection_stats(user_id):
    conn = db()
    row = conn.execute('''
        SELECT
            COUNT(DISTINCT i.card_id) AS count,
            COALESCE(SUM(CASE c.category WHEN 'men' THEN 3 WHEN 'women' THEN 2 WHEN 'reserve' THEN 1 ELSE 0 END), 0) AS value
        FROM inventory i
        JOIN cards c ON c.id=i.card_id
        WHERE i.user_id=?
    ''', (user_id,)).fetchone()
    total = conn.execute('SELECT COUNT(*) AS total FROM cards').fetchone()['total']
    conn.close()
    return int(row['count'] or 0), int(row['value'] or 0), int(total or 0)


init_db()


@app.context_processor
def inject():
    u = current_user()
    if not u:
        return {
            'user': None,
            'user_level': ('Bronze', 'bronze'),
            'collection_count': 0,
            'collection_value': 0,
            'total_cards': 0,
        }
    ccount, cvalue, total = collection_stats(u['id'])
    return {
        'user': u,
        'user_level': level(u['points']),
        'collection_count': ccount,
        'collection_value': cvalue,
        'total_cards': total,
    }


@app.route('/')
def index():
    conn = db()
    matches = conn.execute('SELECT * FROM matches ORDER BY match_date ASC, id ASC').fetchall()
    preds = {}
    if session.get('user_id'):
        rows = conn.execute('SELECT * FROM predictions WHERE user_id=?', (session['user_id'],)).fetchall()
        preds = {r['match_id']: r for r in rows}
    conn.close()
    return render_template('index.html', matches=matches, preds=preds)


@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    if len(username) < 3 or len(password) < 4:
        flash('Pseudo : 3 caractères minimum. Mot de passe : 4 minimum.', 'error')
        return redirect(url_for('index'))
    conn = db()
    try:
        cur = conn.execute(
            'INSERT INTO users(username,password,created_at) VALUES(?,?,?)',
            (username, hash_password(password), datetime.now().isoformat())
        )
        conn.commit()
        session['user_id'] = cur.lastrowid
        session.pop('prediction_results', None)
    except sqlite3.IntegrityError:
        flash('Ce pseudo existe déjà.', 'error')
    finally:
        conn.close()
    return redirect(url_for('index'))


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    conn = db()
    u = conn.execute(
        'SELECT * FROM users WHERE username=? AND password=?',
        (username, hash_password(password))
    ).fetchone()
    conn.close()
    if not u:
        flash('Identifiants incorrects.', 'error')
    else:
        session['user_id'] = u['id']
        session.pop('prediction_results', None)
    return redirect(request.referrer or url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/predict', methods=['POST'])
def predict():
    if not current_user():
        return jsonify({'ok': False, 'error': 'Connexion requise'}), 401
    match_id = request.form.get('match_id', type=int)
    hs = request.form.get('home_score', type=int)
    aws = request.form.get('away_score', type=int)
    if match_id is None or hs is None or aws is None or hs < 0 or aws < 0:
        return jsonify({'ok': False, 'error': 'Score invalide'}), 400

    conn = db()
    m = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
    if not m or m['status'] != 'upcoming':
        conn.close()
        return jsonify({'ok': False, 'error': 'Ce match n’est plus disponible'}), 400

    conn.execute('''
        INSERT INTO predictions(user_id,match_id,home_score,away_score,scored,points_awarded)
        VALUES(?,?,?,?,0,0)
        ON CONFLICT(user_id,match_id) DO UPDATE SET
            home_score=excluded.home_score,
            away_score=excluded.away_score,
            scored=0,
            points_awarded=0
    ''', (session['user_id'], match_id, hs, aws))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/admin')
def admin():
    u = current_user()
    if not u or not u['is_admin']:
        return redirect(url_for('index'))
    conn = db()
    matches = conn.execute('SELECT * FROM matches ORDER BY match_date DESC').fetchall()
    cards = conn.execute('SELECT * FROM cards ORDER BY id DESC').fetchall()
    users = conn.execute('''
        SELECT u.id, u.username, u.points, u.is_admin, u.winning_predictions, u.free_packs,
               COUNT(DISTINCT i.card_id) AS card_count
        FROM users u
        LEFT JOIN inventory i ON i.user_id=u.id
        GROUP BY u.id
        ORDER BY u.points DESC, u.username ASC
    ''').fetchall()
    conn.close()
    return render_template('admin.html', matches=matches, cards=cards, users=users)


@app.route('/admin/match', methods=['POST'])
def admin_match():
    u = current_user()
    if not u or not u['is_admin']:
        return redirect(url_for('index'))
    home = request.form.get('home', '').strip()
    away = request.form.get('away', '').strip()
    match_date = request.form.get('match_date', '').strip()
    if not home or not away or not match_date:
        flash('Complète les informations du match.', 'error')
        return redirect(url_for('admin'))
    conn = db()
    conn.execute(
        'INSERT INTO matches(home,away,competition,match_date) VALUES(?,?,?,?)',
        (home, away, request.form.get('competition') or 'Match', match_date)
    )
    conn.commit()
    conn.close()
    flash('Match ajouté pour tous les comptes.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/result/<int:match_id>', methods=['POST'])
def admin_result(match_id):
    u = current_user()
    if not u or not u['is_admin']:
        return redirect(url_for('index'))
    hs = request.form.get('home_score', type=int)
    aws = request.form.get('away_score', type=int)
    if hs is None or aws is None or hs < 0 or aws < 0:
        flash('Score invalide.', 'error')
        return redirect(url_for('admin'))

    conn = db()
    m = conn.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
    if not m:
        conn.close()
        return redirect(url_for('admin'))
    if m['status'] == 'finished':
        conn.close()
        flash('Ce match a déjà été clôturé.', 'error')
        return redirect(url_for('admin'))

    conn.execute(
        'UPDATE matches SET home_score=?,away_score=?,status="finished" WHERE id=?',
        (hs, aws, match_id)
    )
    rows = conn.execute(
        'SELECT * FROM predictions WHERE match_id=? AND scored=0',
        (match_id,)
    ).fetchall()
    results = []
    actual = winner(hs, aws)

    for p in rows:
        exact = (p['home_score'] == hs and p['away_score'] == aws)
        good = (winner(p['home_score'], p['away_score']) == actual)
        pts = 100 if exact else 50 if good else 0
        pack_earned = 0

        if good:
            old_wins = conn.execute(
                'SELECT winning_predictions FROM users WHERE id=?', (p['user_id'],)
            ).fetchone()['winning_predictions'] or 0
            new_wins = old_wins + 1
            if new_wins % 5 == 0:
                pack_earned = 1
            conn.execute('''
                UPDATE users
                SET points=points+?, winning_predictions=?, free_packs=free_packs+?
                WHERE id=?
            ''', (pts, new_wins, pack_earned, p['user_id']))
        elif pts:
            conn.execute('UPDATE users SET points=points+? WHERE id=?', (pts, p['user_id']))

        results.append({
            'user_id': p['user_id'],
            'points': pts,
            'exact': exact,
            'pack_earned': pack_earned,
            'match': f"{m['home']} – {m['away']}"
        })
        conn.execute(
            'UPDATE predictions SET scored=1, points_awarded=? WHERE id=?',
            (pts, p['id'])
        )

        if pts or pack_earned:
            conn.execute('''
                INSERT INTO pending_rewards(user_id,points,exact,match,pack_earned)
                VALUES(?,?,?,?,?)
            ''', (p['user_id'], pts, int(exact), f"{m['home']} – {m['away']}", pack_earned))

    conn.commit()
    conn.close()
    flash('Résultat enregistré pour tous les joueurs concernés.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/card', methods=['POST'])
def admin_card():
    u = current_user()
    if not u or not u['is_admin']:
        return redirect(url_for('index'))
    category = request.form.get('category')
    if category not in CARD_PRICES:
        flash('Catégorie invalide.', 'error')
        return redirect(url_for('admin'))
    name = request.form.get('name', '').strip()
    image = request.form.get('image', '').strip()
    if not name or not image:
        flash('Nom et image obligatoires.', 'error')
        return redirect(url_for('admin'))
    conn = db()
    conn.execute(
        'INSERT INTO cards(name,category,image,price,created_at) VALUES(?,?,?,?,?)',
        (name, category, image, CARD_PRICES[category], datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    flash('Carte ajoutée à la boutique.', 'success')
    return redirect(url_for('admin'))


@app.route('/history')
def history():
    if not current_user():
        return redirect(url_for('index'))
    conn = db()
    rows = conn.execute('''
        SELECT p.*, m.home, m.away, m.competition, m.match_date,
               m.home_score AS real_home_score, m.away_score AS real_away_score,
               m.status
        FROM predictions p
        JOIN matches m ON m.id = p.match_id
        WHERE p.user_id = ?
        ORDER BY m.match_date DESC, p.id DESC
    ''', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('history.html', predictions=rows)


@app.route('/shop')
def shop():
    conn = db()
    cards = conn.execute('SELECT * FROM cards ORDER BY category,id').fetchall()
    owned = set()
    if session.get('user_id'):
        rows = conn.execute(
            'SELECT card_id FROM inventory WHERE user_id=?', (session['user_id'],)
        ).fetchall()
        owned = {r['card_id'] for r in rows}
    conn.close()
    return render_template('shop.html', cards=cards, owned=owned, card_labels=CARD_LABELS)


@app.route('/buy/<int:card_id>', methods=['POST'])
def buy(card_id):
    u = current_user()
    if not u:
        flash('Connecte-toi pour acheter.', 'error')
        return redirect(url_for('shop'))
    conn = db()
    c = conn.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
    if not c:
        conn.close()
        flash('Carte introuvable.', 'error')
        return redirect(url_for('shop'))
    already = conn.execute(
        'SELECT 1 FROM inventory WHERE user_id=? AND card_id=?', (u['id'], card_id)
    ).fetchone()
    if already:
        conn.close()
        flash('Tu as déjà cette carte. Elle ne peut être achetée qu’une seule fois par compte.', 'error')
        return redirect(url_for('shop'))
    if u['points'] < c['price']:
        conn.close()
        flash('Pas assez de points.', 'error')
        return redirect(url_for('shop'))

    conn.execute('UPDATE users SET points=points-? WHERE id=?', (c['price'], u['id']))
    conn.execute(
        'INSERT INTO inventory(user_id,card_id,quantity) VALUES(?,?,1)',
        (u['id'], card_id)
    )
    conn.commit()
    conn.close()
    flash('Carte ajoutée à ta collection !', 'success')
    return redirect(url_for('shop'))


@app.route('/collection')
def collection():
    u = current_user()
    if not u:
        return redirect(url_for('index'))
    conn = db()
    cards = conn.execute('''
        SELECT c.*,i.quantity
        FROM inventory i
        JOIN cards c ON c.id=i.card_id
        WHERE i.user_id=?
        ORDER BY c.category,c.name
    ''', (u['id'],)).fetchall()
    available = conn.execute('''
        SELECT c.* FROM cards c
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory i WHERE i.user_id=? AND i.card_id=c.id
        )
        ORDER BY c.category,c.name
    ''', (u['id'],)).fetchall()
    total_cards = conn.execute('SELECT COUNT(*) AS total FROM cards').fetchone()['total']
    conn.close()
    return render_template(
        'collection.html',
        cards=cards,
        available=available,
        total_cards=total_cards,
        card_labels=CARD_LABELS
    )


@app.route('/pack/open', methods=['POST'])
def open_pack():
    u = current_user()
    if not u:
        flash('Connecte-toi pour ouvrir un pack.', 'error')
        return redirect(url_for('index'))
    card_id = request.form.get('card_id', type=int)
    if card_id is None:
        flash('Choisis une carte.', 'error')
        return redirect(url_for('collection'))

    conn = db()
    user = conn.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone()
    if not user or user['free_packs'] <= 0:
        conn.close()
        flash('Tu n’as pas de pack gratuit disponible.', 'error')
        return redirect(url_for('collection'))
    card = conn.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
    if not card:
        conn.close()
        flash('Carte introuvable.', 'error')
        return redirect(url_for('collection'))
    owned = conn.execute(
        'SELECT 1 FROM inventory WHERE user_id=? AND card_id=?', (u['id'], card_id)
    ).fetchone()
    if owned:
        conn.close()
        flash('Cette carte est déjà dans ta collection. Choisis-en une autre.', 'error')
        return redirect(url_for('collection'))

    conn.execute('UPDATE users SET free_packs=free_packs-1 WHERE id=?', (u['id'],))
    conn.execute(
        'INSERT INTO inventory(user_id,card_id,quantity) VALUES(?,?,1)',
        (u['id'], card_id)
    )
    conn.commit()
    conn.close()
    flash(f'Pack ouvert : {card["name"]} débloquée gratuitement !', 'success')
    return redirect(url_for('collection'))


@app.route('/classement')
def leaderboard():
    sort = request.args.get('sort', 'points')
    if sort not in ('points', 'cards'):
        sort = 'points'
    conn = db()
    users = conn.execute('''
        SELECT u.id, u.username, u.points, u.winning_predictions, u.free_packs,
               COUNT(DISTINCT i.card_id) AS card_count,
               COALESCE(SUM(CASE c.category WHEN 'men' THEN 3 WHEN 'women' THEN 2 WHEN 'reserve' THEN 1 ELSE 0 END), 0) AS card_value
        FROM users u
        LEFT JOIN inventory i ON i.user_id=u.id
        LEFT JOIN cards c ON c.id=i.card_id
        WHERE u.is_admin=0
        GROUP BY u.id
    ''').fetchall()
    users = list(users)
    if sort == 'cards':
        users.sort(key=lambda x: (-int(x['card_value'] or 0), -int(x['card_count'] or 0), -int(x['points'] or 0), x['username'].lower()))
    else:
        users.sort(key=lambda x: (-int(x['points'] or 0), -int(x['card_value'] or 0), x['username'].lower()))
    conn.close()
    return render_template('leaderboard.html', users=users, sort=sort)


@app.route('/api/rewards')
def rewards():
    if not session.get('user_id'):
        return jsonify({'rewards': []})
    conn = db()
    rows = conn.execute(
        'SELECT id,points,exact,match,pack_earned FROM pending_rewards WHERE user_id=? ORDER BY id',
        (session['user_id'],)
    ).fetchall()
    conn.execute('DELETE FROM pending_rewards WHERE user_id=?', (session['user_id'],))
    conn.commit()
    conn.close()
    return jsonify({'rewards': [dict(r) for r in rows]})


if __name__ == '__main__':
    app.run(debug=True)

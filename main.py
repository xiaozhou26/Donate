from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import schedule
import threading
import psycopg2
import crawler 
import time
import os
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
PER_PAGE = 40  # 每页显示的URL数量

DATABASE_URL = os.getenv('DATABASE_URL')

crawler.init_socketio(socketio)

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def get_urls(page=1, per_page=PER_PAGE):
    offset = (page - 1) * per_page
    conn = get_db_connection()
    if not conn:
        return {}, 0  # 如果数据库连接失败，返回空字典和0
    c = conn.cursor()
    c.execute("SELECT url, gateways, weight FROM urls ORDER BY weight DESC LIMIT %s OFFSET %s", (per_page, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM urls")
    total_rows = c.fetchone()[0]
    conn.close()
    return {row[0]: {"gateways": row[1], "weight": row[2]} for row in rows}, total_rows

def update_weight(url, delta):
    conn = get_db_connection()
    if not conn:
        return 0  # 如果数据库连接失败，返回0
    c = conn.cursor()
    c.execute("UPDATE urls SET weight = weight + %s WHERE url = %s", (delta, url))
    conn.commit()
    c.execute("SELECT weight FROM urls WHERE url = %s", (url,))
    new_weight = c.fetchone()[0]
    conn.close()
    return new_weight

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    url_data, total_rows = get_urls(page)
    total_pages = (total_rows + PER_PAGE - 1) // PER_PAGE
    return render_template('index.html', url_data=url_data, page=page, total_pages=total_pages)

@app.route('/update_weight', methods=['POST'])
def update_weight_route():
    url = request.form['url']
    delta = int(request.form['delta'])
    new_weight = update_weight(url, delta)
    return jsonify({'weight': new_weight})

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    payment_gateways = [
        'paypal', 'stripe', 'braintree', 'checkout.com', 'square', 
        'woocommerce', 'shopify', 'authorize.net', 'adyen', 'sagepay'
    ]

    crawler.init_db()
    threading.Thread(target=lambda: crawler.google_dork_search_and_check(payment_gateways)).start()  # Initial run
    schedule.every(30).minutes.do(crawler.job, payment_gateways)
    threading.Thread(target=run_schedule).start()
    socketio.run(app, host='0.0.0.0', port=3000, allow_unsafe_werkzeug=True)

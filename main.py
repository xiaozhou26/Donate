from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import schedule
import threading
import sqlite3
import crawler
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
DATABASE = 'urls.db'

crawler.init_socketio(socketio)

def get_urls():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT url, gateways, weight FROM urls")
    rows = c.fetchall()
    conn.close()
    return {row[0]: {"gateways": row[1], "weight": row[2]} for row in rows}

def update_weight(url, delta):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE urls SET weight = weight + ? WHERE url = ?", (delta, url))
    conn.commit()
    c.execute("SELECT weight FROM urls WHERE url = ?", (url,))
    new_weight = c.fetchone()[0]
    conn.close()
    return new_weight

@app.route('/')
def index():
    url_data = get_urls()
    return render_template('index.html', url_data=url_data)

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
    socketio.run(app, debug=True, port=5050)
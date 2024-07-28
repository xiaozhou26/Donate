from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import schedule
import threading
import psycopg2
import crawler 
import time
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
port = int(os.getenv('PORT', 5000))
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)
PER_PAGE = 40  # 每页显示的URL数量

DATABASE_URL = os.getenv('DATABASE_URL')

# 初始化爬虫的 SocketIO 配置
crawler.init_socketio(socketio)

# 数据库连接函数
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

# 获取URL数据函数
def get_urls(page=1, per_page=PER_PAGE):
    offset = (page - 1) * per_page
    conn = get_db_connection()
    if not conn:
        return {}, 0  # 如果数据库连接失败，返回空字典和0
    try:
        c = conn.cursor()
        c.execute("SELECT url, gateways, captcha, cloudflare, weight FROM urls ORDER BY weight DESC LIMIT %s OFFSET %s", (per_page, offset))
        rows = c.fetchall()
        c.execute("SELECT COUNT(*) FROM urls")
        total_rows = c.fetchone()[0]
    except Exception as e:
        print(f"Error fetching URLs from the database: {e}")
        return {}, 0
    finally:
        conn.close()
    return {row[0]: {"gateways": row[1], "captcha": row[2], "cloudflare": row[3], "weight": row[4]} for row in rows}, total_rows

# 更新URL权重函数
def update_weight(url, delta):
    conn = get_db_connection()
    if not conn:
        return 0  # 如果数据库连接失败，返回0
    try:
        c = conn.cursor()
        c.execute("UPDATE urls SET weight = weight + %s WHERE url = %s", (delta, url))
        conn.commit()
        c.execute("SELECT weight FROM urls WHERE url = %s", (url,))
        new_weight = c.fetchone()[0]
    except Exception as e:
        print(f"Error updating weight for {url}: {e}")
        return 0
    finally:
        conn.close()
    return new_weight

# 首页路由
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    url_data, total_rows = get_urls(page)
    total_pages = (total_rows + PER_PAGE - 1) // PER_PAGE
    return render_template('index.html', url_data=url_data, page=page, total_pages=total_pages)

# 更新权重路由
@app.route('/update_weight', methods=['POST'])
def update_weight_route():
    url = request.form['url']
    delta = int(request.form['delta'])
    new_weight = update_weight(url, delta)
    return jsonify({'weight': new_weight})

# 计划任务执行函数
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

# 爬虫启动函数
def start_crawler():
    payment_gateways = [
        'paypal', 'stripe', 'braintree', 'checkout.com', 'square', 
        'woocommerce', 'shopify', 'authorize.net', 'adyen', 'sagepay'
    ]
    crawler.init_db()
    threading.Thread(target=lambda: crawler.google_dork_search_and_check(payment_gateways)).start()  # Initial run
    schedule.every(30).minutes.do(crawler.job, payment_gateways)
    threading.Thread(target=run_schedule).start()

if __name__ == '__main__':
    # 启动Flask应用
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port))
    flask_thread.start()
    start_crawler()

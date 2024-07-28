import requests
import time
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import psycopg2
from flask_socketio import SocketIO
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')
socketio = None

def init_socketio(sio: SocketIO):
    global socketio
    socketio = sio

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to the database.")
        return
    try:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                gateways TEXT,
                captcha TEXT,
                cloudflare TEXT,
                weight INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Error initializing the database: {e}")
    finally:
        conn.close()

def insert_url(url, gateways, captcha, cloudflare):
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to the database.")
        return
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO urls (url, gateways, captcha, cloudflare, weight) 
            VALUES (%s, %s, %s, %s, %s) 
            ON CONFLICT (url) 
            DO UPDATE SET gateways = EXCLUDED.gateways, captcha = EXCLUDED.captcha, cloudflare = EXCLUDED.cloudflare
        ''', (url, ','.join(gateways), captcha, cloudflare, 0))
        conn.commit()
    except Exception as e:
        print(f"Error inserting URL into the database: {e}")
    finally:
        conn.close()

def google_dork_search_and_check(payment_gateways):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))

    dorks = [
        'intext:"{}" intitle:"buy now"',
        'inurl:donate + intext:{}',
        'intext:"{}" intitle:"paid plan"',
        'intext:"{}" intitle:"buy membership"',
        'inurl:.com/donate + intext:{}',
        'intext:"{}" intitle:"buy now"',
        'intext:"{}" intitle:"add cart"',
        'intext:"{}" intitle:"membership"',
        'inurl:.com/donate + intext:{}',
        'inurl:.org/donate + intext:{}',
        'inurl:donate + intext:{}',
        'intext:"{}" intitle:"paid plan"',
        'intext:"{}" intitle:"buy membership"',
        'inurl:.com/donate + intext:{}'
    ]

    formatted_dorks = [dork.format(gateway) for dork in dorks for gateway in payment_gateways]

    for dork in formatted_dorks:
        formatted_dork = dork.replace(' ', '+')
        url = f'https://www.google.com/search?q={formatted_dork}'
        try:
            time.sleep(1)  # Sleep to manage request rate
            response = session.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error making request for '{dork}': {e}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        links = soup.find_all('a')

        for link in links:
            href = link.get('href')
            if "url?q=" in href and not "webcache" in href:
                url = href.split("url?q=")[1].split("&sa=U")[0]
                check_website(url, payment_gateways)

def check_website(url, payment_gateways):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            html_content = response.text.lower()
            gateway_found = []

            for gateway in payment_gateways:
                if gateway.lower() in html_content:
                    gateway_found.append(gateway)

            gateway_msg = ', '.join(gateway_found) if gateway_found else 'No gateway detected'
            captcha_msg = 'Yes' if 'captcha' in html_content else 'No'
            cloudflare_msg = 'Yes' if response.headers.get('Server') == 'cloudflare' else 'No'

            insert_url(url, gateway_found, captcha_msg, cloudflare_msg)

            print(f"{url} - Gateway: {gateway_msg}, Captcha: {captcha_msg}, Cloudflare: {cloudflare_msg}")

            if socketio:
                socketio.emit('new_url', {
                    'url': url,
                    'gateways': gateway_msg,
                    'captcha': captcha_msg,
                    'cloudflare': cloudflare_msg,
                    'weight': 0
                }, broadcast=True)

        else:
            print(f"Failed to access {url}")
    except Exception as e:
        print(f"An error occurred with {url}: {str(e)}")

def job(payment_gateways):
    print("Running scheduled job...")
    google_dork_search_and_check(payment_gateways)

import os
import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import telebot
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.Integer, unique=True, nullable=False)
    username = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
logger.info(f"Token loaded: {TOKEN[:10]}...")
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        logger.info(f"Start from: {user_id}")
        user = get_user(user_id)
        bot.send_message(user_id, f"✅ ربات کار می‌کند! موجودی: {user.balance} تومان")
        logger.info(f"Message sent to: {user_id}")
    except Exception as e:
        logger.error(f"Error in start: {e}")

@bot.message_handler(func=lambda message: True)
def echo(message):
    try:
        bot.send_message(message.chat.id, f"پیام شما: {message.text}")
    except Exception as e:
        logger.error(f"Error in echo: {e}")

@app.route('/')
def index():
    return "✅ ربات فعال است!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook is working!", 200
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return f'Error: {e}', 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
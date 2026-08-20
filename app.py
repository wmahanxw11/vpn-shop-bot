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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== مدل‌های دیتابیس =====
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.Integer, unique=True, nullable=False)
    username = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SubscriptionLink(db.Model):
    __tablename__ = 'subscription_links'
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), unique=True, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===== توابع کمکی =====
def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user

def get_unused_link():
    return SubscriptionLink.query.filter_by(is_used=False).first()

def add_balance(telegram_id, amount):
    user = get_user(telegram_id)
    user.balance += amount
    db.session.commit()
    return user

def deduct_balance(telegram_id, amount):
    user = get_user(telegram_id)
    if user.balance >= amount:
        user.balance -= amount
        db.session.commit()
        return True
    return False

def add_transaction(telegram_id, amount, description):
    transaction = Transaction(
        user_id=telegram_id,
        amount=amount,
        description=description
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction

def assign_link_to_user(link_id, telegram_id):
    link = SubscriptionLink.query.get(link_id)
    if link:
        link.is_used = True
        link.used_by = telegram_id
        link.used_at = datetime.utcnow()
        db.session.commit()
        return True
    return False

# ===== ربات تلگرام =====
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    user = get_user(user_id)
    user.username = username
    db.session.commit()
    bot.send_message(
        user_id,
        f"👋 به ربات فروش VPN خوش آمدید!\n"
        f"💰 موجودی: {user.balance} تومان"
    )

@bot.message_handler(commands=['balance'])
def balance(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    bot.send_message(user_id, f"💰 موجودی شما: {user.balance} تومان")

@app.route('/')
def index():
    return "✅ ربات با دیتابیس فعال است!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook is working!", 200
    if request.method == 'POST':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            logger.error(f"Error: {e}")
            return 'Error', 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        logger.info("Database created!")
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
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

# ===== مدل‌ها =====
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.Integer, unique=True, nullable=False)
    username = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===== توابع کمکی با context =====
def get_user(telegram_id):
    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id)
            db.session.add(user)
            db.session.commit()
            logger.info(f"✅ New user created: {telegram_id}")
        return user

def add_balance(telegram_id, amount):
    with app.app_context():
        user = get_user(telegram_id)
        user.balance += amount
        db.session.commit()
        return user

# ===== ربات =====
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

logger.info(f"✅ Token loaded: {TOKEN[:10]}...")
bot = telebot.TeleBot(TOKEN)

# ===== هندلرهای ربات =====
@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        logger.info(f"📩 Start from: {user_id}")
        
        # استفاده از context برای دیتابیس
        with app.app_context():
            user = get_user(user_id)
            user.username = username
            db.session.commit()
            balance = user.balance
        
        bot.send_message(
            user_id,
            f"👋 به ربات فروش VPN خوش آمدید!\n"
            f"💰 موجودی: {balance} تومان"
        )
        logger.info(f"✅ Message sent to: {user_id}")
    except Exception as e:
        logger.error(f"❌ Error in start: {e}")

@bot.message_handler(commands=['balance'])
def balance(message):
    try:
        user_id = message.from_user.id
        logger.info(f"📩 Balance from: {user_id}")
        
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
        
        bot.send_message(user_id, f"💰 موجودی شما: {balance} تومان")
        logger.info(f"✅ Balance sent to: {user_id}")
    except Exception as e:
        logger.error(f"❌ Error in balance: {e}")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    try:
        bot.send_message(
            message.chat.id,
            f"📝 پیام شما: {message.text}\n"
            f"برای مشاهده موجودی از /balance استفاده کنید."
        )
    except Exception as e:
        logger.error(f"❌ Error in echo: {e}")

# ===== روت‌ها =====
@app.route('/')
def index():
    return "✅ ربات با دیتابیس فعال است!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook is working!", 200
    
    if request.method == 'POST':
        try:
            logger.info("📨 Webhook received POST")
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            
            # پردازش در context برنامه
            with app.app_context():
                bot.process_new_updates([update])
            
            return 'OK', 200
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return f'Error: {e}', 500

# ===== راه‌اندازی =====
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        logger.info("✅ Database tables created")
    
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
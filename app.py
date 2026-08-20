import os
import logging
from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import telebot
from datetime import datetime
import traceback

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===== مدل‌ها =====
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

# ===== ساخت جدول‌ها =====
with app.app_context():
    db.create_all()
    logger.info("✅ Database tables created successfully")

# ===== توابع دیتابیس =====
def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
        logger.info(f"✅ New user: {telegram_id}")
    return user

def get_user_balance(telegram_id):
    user = get_user(telegram_id)
    return user.balance

def update_user_balance(telegram_id, amount):
    user = get_user(telegram_id)
    user.balance += amount
    db.session.commit()
    return user.balance

# ===== ربات =====
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("❌ TOKEN not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

logger.info(f"✅ Token: {TOKEN[:10]}...")
bot = telebot.TeleBot(TOKEN)

# ===== هندلرها =====
@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        logger.info(f"📩 /start from: {user_id}")
        
        # همه عملیات دیتابیس داخل context
        with app.app_context():
            user = get_user(user_id)
            user.username = username
            db.session.commit()
            balance = user.balance
        
        bot.send_message(
            user_id,
            f"👋 به ربات فروش VPN خوش آمدید!\n"
            f"💰 موجودی: {balance} تومان\n\n"
            f"/balance - موجودی"
        )
        logger.info(f"✅ /start response sent")
        
    except Exception as e:
        error_msg = f"❌ /start error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        try:
            bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")
        except:
            pass

@bot.message_handler(commands=['balance'])
def balance(message):
    try:
        user_id = message.from_user.id
        logger.info(f"📩 /balance from: {user_id}")
        
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
        
        bot.send_message(user_id, f"💰 موجودی شما: {balance} تومان")
        logger.info(f"✅ /balance response sent")
        
    except Exception as e:
        error_msg = f"❌ /balance error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        try:
            bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")
        except:
            pass

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    try:
        bot.send_message(
            message.chat.id,
            f"📝 پیام شما: {message.text}\n\n"
            f"دستورات:\n"
            f"/start - شروع\n"
            f"/balance - موجودی"
        )
    except Exception as e:
        logger.error(f"❌ Echo error: {e}")

# ===== روت‌ها =====
@app.route('/')
def index():
    return "✅ ربات فعال است!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook is working!", 200
    
    try:
        logger.info("📨 Webhook POST received")
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        with app.app_context():
            bot.process_new_updates([update])
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {str(e)}\n{traceback.format_exc()}")
        return f'Error: {e}', 500

# ===== راه‌اندازی =====
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
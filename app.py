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

# ===== تنظیمات لاگ =====
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

def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
        logger.info(f"✅ New user created: {telegram_id}")
    return user

# ===== ربات =====
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN is required")

logger.info(f"✅ Bot token loaded: {TOKEN[:10]}...")
bot = telebot.TeleBot(TOKEN)

# ===== هندلرها =====
@bot.message_handler(commands=['start'])
def start(message):
    logger.info(f"📩 Start command from: {message.from_user.id}")
    user_id = message.from_user.id
    username = message.from_user.username
    user = get_user(user_id)
    user.username = username
    db.session.commit()
    
    msg = f"👋 به ربات فروش VPN خوش آمدید!\n💰 موجودی: {user.balance} تومان"
    bot.send_message(user_id, msg)
    logger.info(f"✅ Message sent to: {user_id}")

@bot.message_handler(commands=['balance'])
def balance(message):
    logger.info(f"📩 Balance command from: {message.from_user.id}")
    user_id = message.from_user.id
    user = get_user(user_id)
    bot.send_message(user_id, f"💰 موجودی شما: {user.balance} تومان")
    logger.info(f"✅ Balance sent to: {user_id}")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    logger.info(f"📩 Message from {message.from_user.id}: {message.text}")
    bot.send_message(message.chat.id, f"پیام شما: {message.text}")

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
            bot.process_new_updates([update])
            return 'OK', 200
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return f'Error: {e}', 500

# ===== راه‌اندازی =====
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        logger.info("✅ Database tables created")
    
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🚀 Starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
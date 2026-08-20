import os
import logging
from flask import Flask, request, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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
    logger.info("✅ Database tables created")

# ===== توابع دیتابیس =====
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
    return user.balance

def deduct_balance(telegram_id, amount):
    user = get_user(telegram_id)
    if user.balance >= amount:
        user.balance -= amount
        db.session.commit()
        return True
    return False

def add_transaction(telegram_id, amount, description):
    trans = Transaction(
        user_id=telegram_id,
        amount=amount,
        description=description
    )
    db.session.add(trans)
    db.session.commit()
    return trans

def assign_link_to_user(link_id, telegram_id):
    link = SubscriptionLink.query.get(link_id)
    if link:
        link.is_used = True
        link.used_by = telegram_id
        link.used_at = datetime.utcnow()
        db.session.commit()
        return True
    return False

# ===== ربات =====
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

PRICE = 10000  # قیمت هر اشتراک

@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        with app.app_context():
            user = get_user(user_id)
            user.username = username
            db.session.commit()
            balance = user.balance
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
            InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy"),
            InlineKeyboardButton("📊 وضعیت", callback_data="status")
        )
        
        bot.send_message(
            user_id,
            f"👋 به ربات فروش VPN خوش آمدید!\n"
            f"💰 موجودی: {balance} تومان",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Start error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def handle_wallet(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
        bot.send_message(user_id, f"💰 موجودی شما: {balance} تومان")
    except Exception as e:
        logger.error(f"Wallet error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "buy")
def handle_buy(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
            
            if balance < PRICE:
                bot.send_message(
                    user_id,
                    f"❌ موجودی کافی نیست!\n"
                    f"💰 موجودی: {balance} تومان\n"
                    f"💳 قیمت: {PRICE} تومان"
                )
                return
            
            link = get_unused_link()
            if not link:
                bot.send_message(
                    user_id,
                    "❌ لینکی موجود نیست!\n"
                    "لطفاً با پشتیبانی تماس بگیرید."
                )
                return
            
            if assign_link_to_user(link.id, user_id):
                if deduct_balance(user_id, PRICE):
                    add_transaction(user_id, -PRICE, "خرید اشتراک")
                    new_balance = get_user(user_id).balance
                    
                    bot.send_message(
                        user_id,
                        f"✅ اشتراک خریداری شد!\n\n"
                        f"🔗 لینک:\n`{link.link}`\n\n"
                        f"💰 موجودی جدید: {new_balance} تومان",
                        parse_mode='Markdown'
                    )
    except Exception as e:
        logger.error(f"Buy error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "status")
def handle_status(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            links = SubscriptionLink.query.filter_by(used_by=user_id).all()
        
        if links:
            msg = "📊 اشتراک‌های شما:\n\n"
            for i, link in enumerate(links[-5:], 1):
                msg += f"{i}. `{link.link}`\n"
                if link.used_at:
                    msg += f"   🕐 {link.used_at.strftime('%Y-%m-%d')}\n"
            bot.send_message(user_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(user_id, "📊 شما اشتراکی ندارید.")
    except Exception as e:
        logger.error(f"Status error: {e}")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.send_message(
        message.chat.id,
        "👋 سلام! از /start استفاده کنید."
    )

# ===== روت‌های پنل مدیریت =====
@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == os.environ.get('ADMIN_PASSWORD', 'admin123'):
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('login.html', error='رمز اشتباه است!')
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    with app.app_context():
        users_count = User.query.count()
        links_count = SubscriptionLink.query.count()
        used_links = SubscriptionLink.query.filter_by(is_used=True).count()
        total_income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.amount > 0).scalar() or 0
    
    return render_template(
        'admin.html',
        users_count=users_count,
        links_count=links_count,
        used_links=used_links,
        unused_links=links_count - used_links,
        total_income=total_income
    )

@app.route('/admin/users')
def admin_users():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/admin/links')
def admin_links():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    links = SubscriptionLink.query.order_by(SubscriptionLink.created_at.desc()).all()
    return render_template('links.html', links=links)

@app.route('/admin/add_link', methods=['GET', 'POST'])
def admin_add_link():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        link_url = request.form.get('link_url')
        if link_url:
            new_link = SubscriptionLink(link=link_url)
            db.session.add(new_link)
            db.session.commit()
            return redirect(url_for('admin_links'))
    return render_template('add_link.html')

@app.route('/admin/transactions')
def admin_transactions():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    return render_template('transactions.html', transactions=transactions)

@app.route('/admin/charge', methods=['POST'])
def admin_charge():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    telegram_id = request.form.get('telegram_id')
    amount = float(request.form.get('amount', 0))
    
    if telegram_id and amount > 0:
        with app.app_context():
            add_balance(int(telegram_id), amount)
            add_transaction(int(telegram_id), amount, "شارژ توسط ادمین")
        
        # اطلاع به کاربر
        try:
            bot.send_message(
                int(telegram_id),
                f"💰 کیف پول شما به مبلغ {amount} تومان شارژ شد!"
            )
        except:
            pass
        
        return redirect(url_for('admin_users'))
    return "خطا", 400

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "✅ Webhook is working!", 200
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        with app.app_context():
            bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return f'Error: {e}', 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
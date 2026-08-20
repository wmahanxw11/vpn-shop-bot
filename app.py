import os
import logging
from flask import Flask, request, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import threading
import time

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیمات Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# تنظیمات دیتابیس
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///bot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS = False']

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# مدل‌های دیتابیس (تعریف در models.py)
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.Integer, unique=True, nullable=False)
    username = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    transactions = db.relationship('Transaction', backref='user_ref', lazy=True)
    links = db.relationship('SubscriptionLink', backref='user_ref', lazy=True)

class SubscriptionLink(db.Model):
    __tablename__ = 'subscription_links'
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), unique=True, nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, db.ForeignKey('users.telegram_id'), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.telegram_id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# توابع کمکی
def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user

def get_user_by_id(user_id):
    return User.query.filter_by(telegram_id=user_id).first()

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

# تنظیمات ربات تلگرام
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# هندلرهای ربات
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    user = get_user(user_id)
    user.username = username
    db.session.commit()
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💰 کیف پول من", callback_data="wallet"),
        InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy"),
        InlineKeyboardButton("📊 وضعیت اشتراک", callback_data="status")
    )
    bot.send_message(
        user_id,
        f"👋 به ربات فروش VPN خوش آمدید!\n\n"
        f"📌 برای خرید اشتراک، ابتدا کیف پول خود را شارژ کنید.\n"
        f"💰 موجودی فعلی: {user.balance} تومان",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def handle_wallet(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    bot.send_message(
        user_id,
        f"💰 موجودی کیف پول شما: {user.balance} تومان"
    )

@bot.callback_query_handler(func=lambda call: call.data == "buy")
def handle_buy(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    
    PRICE = 10000  # قیمت هر اشتراک
    
    if user.balance < PRICE:
        bot.send_message(
            user_id,
            f"❌ موجودی کافی نیست!\n"
            f"💰 موجودی: {user.balance} تومان\n"
            f"💳 قیمت هر اشتراک: {PRICE} تومان\n\n"
            f"📞 برای شارژ کیف پول با پشتیبانی تماس بگیرید."
        )
        return
    
    # پیدا کردن لینک استفاده‌نشده
    link = get_unused_link()
    if not link:
        bot.send_message(
            user_id,
            "❌ متأسفانه لینکی موجود نیست!\n"
            "📞 لطفاً با پشتیبانی تماس بگیرید."
        )
        return
    
    # اختصاص لینک به کاربر
    if assign_link_to_user(link.id, user_id):
        # کم کردن از کیف پول
        if deduct_balance(user_id, PRICE):
            # ثبت تراکنش
            add_transaction(user_id, -PRICE, f"خرید اشتراک - لینک: {link.link[:20]}...")
            
            # ارسال لینک به کاربر
            bot.send_message(
                user_id,
                f"✅ اشتراک شما با موفقیت خریداری شد!\n\n"
                f"🔗 لینک ساب:\n`{link.link}`\n\n"
                f"⚠️ این لینک یکبار مصرف است و پس از استفاده منقضی می‌شود.\n"
                f"💰 موجودی جدید: {user.balance} تومان",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(user_id, "❌ خطا در پرداخت! لطفاً دوباره تلاش کنید.")

@bot.callback_query_handler(func=lambda call: call.data == "status")
def handle_status(call):
    user_id = call.from_user.id
    user = get_user(user_id)
    
    # پیدا کردن لینک‌های خریداری شده توسط کاربر
    purchased_links = SubscriptionLink.query.filter_by(used_by=user_id).all()
    
    if purchased_links:
        message = "📊 لیست اشتراک‌های خریداری شده:\n\n"
        for i, link in enumerate(purchased_links[-5:], 1):  # آخرین 5 اشتراک
            message += f"{i}. `{link.link}`\n"
            message += f"   📅 تاریخ خرید: {link.used_at.strftime('%Y-%m-%d %H:%M')}\n\n"
    else:
        message = "📊 شما هنوز هیچ اشتراکی خریداری نکرده‌اید."
    
    bot.send_message(user_id, message, parse_mode='Markdown')

# روت‌های وب‌پنل مدیریت
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
        else:
            return render_template('login.html', error='رمز عبور اشتباه است!')
    return render_template('login.html')

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    users_count = User.query.count()
    links_count = SubscriptionLink.query.count()
    used_links = SubscriptionLink.query.filter_by(is_used=True).count()
    unused_links = links_count - used_links
    
    # محاسبه درآمد کل
    total_income = db.session.query(db.func.sum(Transaction.amount)).filter(Transaction.amount > 0).scalar() or 0
    
    return render_template(
        'admin.html',
        users_count=users_count,
        links_count=links_count,
        used_links=used_links,
        unused_links=unused_links,
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
        try:
            user = get_user(int(telegram_id))
            add_balance(int(telegram_id), amount)
            add_transaction(int(telegram_id), amount, "شارژ کیف پول توسط ادمین")
            
            # اطلاع‌رسانی به کاربر
            try:
                bot.send_message(
                    int(telegram_id),
                    f"💰 کیف پول شما به مبلغ {amount} تومان شارژ شد.\n"
                    f"💰 موجودی جدید: {user.balance} تومان"
                )
            except:
                pass
            
            return redirect(url_for('admin_users'))
        except:
            return "خطا در شارژ کیف پول", 400
    
    return "مقادیر نامعتبر", 400

@app.route('/admin/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Webhook برای تلگرام
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Unsupported media type', 415

# راه‌اندازی برنامه
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # تنظیم Webhook در تلگرام
    if os.environ.get('RAILWAY_ENV'):
        webhook_url = os.environ.get('RAILWAY_PUBLIC_URL', '') + '/webhook'
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
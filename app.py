import os
import logging
from flask import Flask, request, render_template, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import traceback
import json

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
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=True)
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Plan(db.Model):
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    volume = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ===== ساخت جدول‌ها =====
with app.app_context():
    db.create_all()
    
    # تنظیمات پیش‌فرض
    default_settings = [
        Setting(key='currency', value='تومان'),
        Setting(key='bot_name', value='فروشگاه VPN'),
        Setting(key='theme', value='default'),
        Setting(key='primary_color', value='#667eea'),
        Setting(key='secondary_color', value='#764ba2'),
    ]
    
    for setting in default_settings:
        if not Setting.query.filter_by(key=setting.key).first():
            db.session.add(setting)
    
    # پلن‌های پیش‌فرض
    default_plans = [
        Plan(name='پایه', volume='10GB', duration='1 ماهه', price=15000),
        Plan(name='استاندارد', volume='30GB', duration='1 ماهه', price=35000),
        Plan(name='پیشرفته', volume='50GB', duration='1 ماهه', price=55000),
        Plan(name='حرفه‌ای', volume='100GB', duration='1 ماهه', price=95000),
        Plan(name='پایه ۳ ماهه', volume='10GB', duration='3 ماهه', price=35000),
        Plan(name='استاندارد ۳ ماهه', volume='30GB', duration='3 ماهه', price=85000),
        Plan(name='پیشرفته ۳ ماهه', volume='50GB', duration='3 ماهه', price=135000),
        Plan(name='حرفه‌ای ۳ ماهه', volume='100GB', duration='3 ماهه', price=225000),
    ]
    
    for plan in default_plans:
        if not Plan.query.filter_by(name=plan.name).first():
            db.session.add(plan)
    
    db.session.commit()
    logger.info("✅ Database tables and default data created")

# ===== توابع =====
def get_setting(key, default=''):
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def update_setting(key, value):
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
        setting.updated_at = datetime.utcnow()
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    db.session.commit()
    return setting

def get_theme():
    return get_setting('theme', 'default')

def get_primary_color():
    return get_setting('primary_color', '#667eea')

def get_secondary_color():
    return get_setting('secondary_color', '#764ba2')

def get_user(telegram_id):
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user

def get_plans():
    return Plan.query.filter_by(is_active=True).all()

def get_plan(plan_id):
    return Plan.query.get(plan_id)

def get_unused_link(plan_id=None):
    if plan_id:
        return SubscriptionLink.query.filter_by(is_used=False, plan_id=plan_id).first()
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

def add_transaction(telegram_id, amount, description, plan_id=None):
    trans = Transaction(
        user_id=telegram_id,
        plan_id=plan_id,
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
            currency = get_setting('currency', 'تومان')
            bot_name = get_setting('bot_name', 'فروشگاه VPN')
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💰 کیف پول", callback_data="wallet"),
            InlineKeyboardButton("🛒 خرید اشتراک", callback_data="buy_plans"),
            InlineKeyboardButton("📊 وضعیت", callback_data="status")
        )
        
        bot.send_message(
            user_id,
            f"👋 به {bot_name} خوش آمدید!\n"
            f"💰 موجودی: {balance} {currency}",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Start error: {e}")

@bot.message_handler(commands=['balance'])
def balance(message):
    try:
        user_id = message.from_user.id
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
            currency = get_setting('currency', 'تومان')
        bot.send_message(user_id, f"💰 موجودی شما: {balance} {currency}")
    except Exception as e:
        logger.error(f"Balance error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "wallet")
def handle_wallet(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            user = get_user(user_id)
            balance = user.balance
            currency = get_setting('currency', 'تومان')
        bot.send_message(user_id, f"💰 موجودی شما: {balance} {currency}")
    except Exception as e:
        logger.error(f"Wallet error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "buy_plans")
def handle_buy_plans(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            plans = get_plans()
            currency = get_setting('currency', 'تومان')
        
        if not plans:
            bot.send_message(user_id, "❌ هیچ پلنی موجود نیست!")
            return
        
        markup = InlineKeyboardMarkup(row_width=2)
        for plan in plans:
            markup.add(
                InlineKeyboardButton(
                    f"{plan.name} - {plan.volume} - {plan.duration} - {plan.price} {currency}",
                    callback_data=f"plan_{plan.id}"
                )
            )
        markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back"))
        
        bot.send_message(
            user_id,
            "🛒 لطفاً پلن مورد نظر را انتخاب کنید:",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Buy plans error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def handle_plan_selection(call):
    try:
        user_id = call.from_user.id
        plan_id = int(call.data.split("_")[1])
        
        with app.app_context():
            plan = get_plan(plan_id)
            if not plan:
                bot.send_message(user_id, "❌ پلن مورد نظر یافت نشد!")
                return
            
            user = get_user(user_id)
            balance = user.balance
            currency = get_setting('currency', 'تومان')
            
            if balance < plan.price:
                bot.send_message(
                    user_id,
                    f"❌ موجودی کافی نیست!\n"
                    f"💰 موجودی: {balance} {currency}\n"
                    f"💳 قیمت پلن: {plan.price} {currency}"
                )
                return
            
            link = get_unused_link(plan_id)
            if not link:
                bot.send_message(
                    user_id,
                    f"❌ لینکی برای این پلن موجود نیست!\n"
                    f"لطفاً با پشتیبانی تماس بگیرید."
                )
                return
            
            if assign_link_to_user(link.id, user_id):
                if deduct_balance(user_id, plan.price):
                    add_transaction(
                        user_id,
                        -plan.price,
                        f"خرید {plan.name} - {plan.volume} - {plan.duration}",
                        plan_id
                    )
                    new_balance = get_user(user_id).balance
                    
                    bot.send_message(
                        user_id,
                        f"✅ اشتراک خریداری شد!\n\n"
                        f"📦 پلن: {plan.name}\n"
                        f"📊 حجم: {plan.volume}\n"
                        f"⏱ مدت: {plan.duration}\n"
                        f"🔗 لینک:\n`{link.link}`\n\n"
                        f"💰 موجودی جدید: {new_balance} {currency}",
                        parse_mode='Markdown'
                    )
    except Exception as e:
        logger.error(f"Plan selection error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "status")
def handle_status(call):
    try:
        user_id = call.from_user.id
        with app.app_context():
            links = SubscriptionLink.query.filter_by(used_by=user_id).all()
        
        if links:
            msg = "📊 اشتراک‌های شما:\n\n"
            for i, link in enumerate(links[-5:], 1):
                plan = Plan.query.get(link.plan_id)
                plan_name = f"{plan.name} - {plan.volume}" if plan else "نامشخص"
                msg += f"{i}. {plan_name}\n"
                msg += f"   🔗 `{link.link}`\n"
                if link.used_at:
                    msg += f"   🕐 {link.used_at.strftime('%Y-%m-%d %H:%M')}\n"
                msg += "\n"
            bot.send_message(user_id, msg, parse_mode='Markdown')
        else:
            bot.send_message(user_id, "📊 شما اشتراکی ندارید.")
    except Exception as e:
        logger.error(f"Status error: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "back")
def handle_back(call):
    start(call.message)

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.send_message(
        message.chat.id,
        "👋 سلام! از /start استفاده کنید."
    )

# ===== روت‌های پنل مدیریت =====

# تابع inject_theme برای اعمال تم به همه صفحات
@app.context_processor
def inject_theme():
    return {
        'theme': get_theme(),
        'primary_color': get_primary_color(),
        'secondary_color': get_secondary_color(),
        'currency': get_setting('currency', 'تومان'),
        'bot_name': get_setting('bot_name', 'فروشگاه VPN')
    }

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
        currency = get_setting('currency', 'تومان')
        bot_name = get_setting('bot_name', 'فروشگاه VPN')
        plans = Plan.query.all()
    
    return render_template(
        'admin.html',
        users_count=users_count,
        links_count=links_count,
        used_links=used_links,
        unused_links=links_count - used_links,
        total_income=total_income,
        plans=plans
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
    plans = Plan.query.all()
    return render_template('links.html', links=links, plans=plans)

@app.route('/admin/add_link', methods=['GET', 'POST'])
def admin_add_link():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    plans = Plan.query.all()
    
    if request.method == 'POST':
        link_url = request.form.get('link_url')
        plan_id = request.form.get('plan_id')
        if link_url:
            new_link = SubscriptionLink(
                link=link_url,
                plan_id=int(plan_id) if plan_id else None
            )
            db.session.add(new_link)
            db.session.commit()
            return redirect(url_for('admin_links'))
    
    return render_template('add_link.html', plans=plans)

@app.route('/admin/transactions')
def admin_transactions():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    transactions = Transaction.query.order_by(Transaction.created_at.desc()).all()
    plans = Plan.query.all()
    return render_template('transactions.html', transactions=transactions, plans=plans)

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
        
        try:
            bot.send_message(
                int(telegram_id),
                f"💰 کیف پول شما به مبلغ {amount} {get_setting('currency', 'تومان')} شارژ شد!"
            )
        except:
            pass
        
        return redirect(url_for('admin_users'))
    return "خطا", 400

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        currency = request.form.get('currency')
        bot_name = request.form.get('bot_name')
        new_theme = request.form.get('theme')
        new_primary = request.form.get('primary_color')
        new_secondary = request.form.get('secondary_color')
        
        with app.app_context():
            if currency:
                update_setting('currency', currency)
            if bot_name:
                update_setting('bot_name', bot_name)
            if new_theme:
                update_setting('theme', new_theme)
            if new_primary:
                update_setting('primary_color', new_primary)
            if new_secondary:
                update_setting('secondary_color', new_secondary)
        
        return redirect(url_for('admin_settings', saved=1))
    
    currency = get_setting('currency', 'تومان')
    bot_name = get_setting('bot_name', 'فروشگاه VPN')
    
    return render_template(
        'settings.html',
        saved=request.args.get('saved')
    )

@app.route('/admin/plans', methods=['GET', 'POST'])
def admin_plans():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            name = request.form.get('name')
            volume = request.form.get('volume')
            duration = request.form.get('duration')
            price = float(request.form.get('price', 0))
            
            if name and volume and duration and price > 0:
                new_plan = Plan(name=name, volume=volume, duration=duration, price=price)
                db.session.add(new_plan)
                db.session.commit()
        
        elif action == 'toggle':
            plan_id = int(request.form.get('plan_id'))
            plan = Plan.query.get(plan_id)
            if plan:
                plan.is_active = not plan.is_active
                db.session.commit()
        
        elif action == 'delete':
            plan_id = int(request.form.get('plan_id'))
            plan = Plan.query.get(plan_id)
            if plan:
                db.session.delete(plan)
                db.session.commit()
        
        return redirect(url_for('admin_plans'))
    
    plans = Plan.query.all()
    return render_template('plans.html', plans=plans)

@app.route('/admin/plans/edit/<int:plan_id>', methods=['GET', 'POST'])
def admin_plan_edit(plan_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    plan = Plan.query.get_or_404(plan_id)
    
    if request.method == 'POST':
        plan.name = request.form.get('name')
        plan.volume = request.form.get('volume')
        plan.duration = request.form.get('duration')
        plan.price = float(request.form.get('price', 0))
        plan.is_active = True if request.form.get('is_active') else False
        db.session.commit()
        return redirect(url_for('admin_plans'))
    
    return render_template('plan_edit.html', plan=plan)

@app.route('/admin/plans/delete/<int:plan_id>', methods=['POST'])
def admin_plan_delete(plan_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    plan = Plan.query.get_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    return redirect(url_for('admin_plans'))

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
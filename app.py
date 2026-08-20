import os
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "✅ برنامه کار می‌کند!"

@app.route('/webhook', methods=['GET'])
def webhook():
    return "✅ Webhook is working!", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
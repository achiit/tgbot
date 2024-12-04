from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Bot, Update
from telegram.ext import Application
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, RetryAfter
import os
from dotenv import load_dotenv
import asyncio
from functools import wraps

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize Telegram bot with custom connection pool
request = HTTPXRequest(connection_pool_size=8)
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'), request=request)
GROUP_ID = os.getenv('TELEGRAM_GROUP_ID')

# Store user join status
user_join_status = {}

def async_route(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(f(*args, **kwargs))
        finally:
            loop.close()
    return wrapped

async def check_member_with_retry(user_id):
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            chat_member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
            return chat_member.status in ['member', 'administrator', 'creator']
        except TimedOut:
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                raise

@app.route('/check-join-status/<user_id>', methods=['GET'])
@async_route
async def check_join_status(user_id):
    try:
        # Check if user is a member of the group with retry logic
        is_member = await check_member_with_retry(user_id)
        
        # Store the status
        user_join_status[user_id] = is_member
        
        return jsonify({
            'user_id': user_id,
            'is_member': is_member
        })
    except Exception as e:
        print(f"Error checking membership: {str(e)}")
        return jsonify({
            'error': str(e),
            'user_id': user_id,
            'is_member': False
        })

@app.route('/webhook', methods=['POST'])
@async_route
async def webhook():
    try:
        update = Update.de_json(request.get_json(), bot)
        
        if update and update.my_chat_member:
            user_id = str(update.my_chat_member.from_user.id)
            new_status = update.my_chat_member.new_chat_member.status
            
            user_join_status[user_id] = new_status in ['member', 'administrator', 'creator']
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Webhook error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/')
def home():
    return 'Bot is running!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
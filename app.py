import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import anthropic

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# เก็บ conversation state ของแต่ละ user
user_sessions = {}

SYSTEM_PROMPT = """คุณคือ SolarFiX Bot ผู้ช่วยรับแจ้งซ่อมอินเวอร์เตอร์โซลาร์เซลล์ของบริษัท SolarFiX

หน้าที่ของคุณคือถามข้อมูลลูกค้าให้ครบ 5 ข้อ ทีละข้อ อย่างสุภาพและเป็นมิตร:
1. ยี่ห้อและรุ่นของอินเวอร์เตอร์
2. กำลังวัตต์ (เช่น 3kW, 5kW)
3. อาการที่พบ (อธิบายให้ละเอียด)
4. Error Code ที่แสดงบนหน้าจอ (ถ้าไม่มีให้บอก "ไม่มี")
5. ชื่อ-นามสกุล, เบอร์โทรศัพท์ และจังหวัดที่อยู่

เมื่อได้ข้อมูลครบ 5 ข้อแล้ว ให้สรุปข้อมูลทั้งหมดและแจ้งลูกค้าว่า:
"ขอบคุณครับ ทีม SolarFiX จะติดต่อกลับภายใน 24 ชั่วโมง เพื่อแจ้งราคาประเมินและขั้นตอนการส่งเครื่อง"

กฎสำคัญ:
- ถามทีละข้อ ไม่ถามรวมกัน
- ใช้ภาษาไทย สุภาพ กระชับ
- ถ้าลูกค้าตอบไม่ชัด ให้ถามซ้ำหรือขอตัวอย่างเพิ่มเติม
- ห้ามออกนอกเรื่องการรับซ่อม"""

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text

    # สร้าง session ใหม่ถ้ายังไม่มี
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    # เพิ่มข้อความ user เข้า history
    user_sessions[user_id].append({
        "role": "user",
        "content": user_message
    })

    # เรียก Claude API
    response = claude_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=user_sessions[user_id]
    )

    bot_reply = response.content[0].text

    # เพิ่ม reply เข้า history
    user_sessions[user_id].append({
        "role": "assistant",
        "content": bot_reply
    })

    # ส่ง reply กลับ LINE
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=bot_reply)
    )

@app.route("/", methods=["GET"])
def index():
    return "SolarFiX Chatbot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

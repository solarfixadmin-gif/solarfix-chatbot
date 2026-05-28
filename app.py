import os
import threading
import requests
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import anthropic

app = Flask(__name__)

line_bot_api = LineBotApi(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.environ.get("LINE_CHANNEL_SECRET"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

ADMIN_USER_ID = "U1adb92ef2e33e6beda1fff9fbce5d017"

user_sessions = {}

def is_business_hours():
    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    if now.hour == 20:
        return now.minute == 0
    return 8 <= now.hour < 20

def keep_alive():
    while True:
        try:
            requests.get("https://solarfix-chatbot.onrender.com/")
        except:
            pass
        time.sleep(600)

threading.Thread(target=keep_alive, daemon=True).start()

WELCOME_MESSAGE = """👋 สวัสดีครับ! ยินดีต้อนรับสู่ SolarFiX 🔆⚡

เราคือบริการซ่อมอินเวอร์เตอร์และโซลาร์เซลล์ครบวงจร
📦 ส่งซ่อมได้ทั่วประเทศทางไปรษณีย์
✅ ประเมินราคาฟรี ไม่มีค่าใช้จ่ายล่วงหน้า
✅ แจ้งผลวินิจฉัยภายใน 24 ชั่วโมง
✅ รับซ่อมทุกยี่ห้อ Growatt, Deye, Solis, Huawei ฯลฯ

━━━━━━━━━━━━━━━
📌 เลือกสิ่งที่ต้องการได้เลยครับ:

1️⃣ สอบถามราคาและขั้นตอนบริการ
2️⃣ แจ้งซ่อมอินเวอร์เตอร์
3️⃣ ติดต่อเจ้าหน้าที่โดยตรง

พิมพ์ตัวเลข 1, 2 หรือ 3
หรือกดปุ่มเมนูด้านล่างได้เลยครับ 😊"""

FAQ_MESSAGE = """💡 ขั้นตอนการใช้บริการ SolarFiX

📦 เราทำงานอย่างไร?
เราไม่สามารถบอกราคาได้ก่อนเห็นเครื่อง
เพราะอาการเดียวกันอาจมีสาเหตุต่างกัน
ช่างต้องตรวจก่อนถึงจะวินิจฉัยได้แม่นยำ

✅ ขั้นตอน 4 ขั้น:
1️⃣ แจ้งอาการผ่านแชทนี้
2️⃣ ส่งเครื่องมาทางไปรษณีย์ (ฟรีค่าตรวจ)
3️⃣ ช่างตรวจและแจ้งราคาจริงภายใน 24 ชม.
4️⃣ ยืนยันซ่อม → ซ่อมเสร็จส่งคืน

⚠️ ลูกค้ามีสิทธิ์ปฏิเสธได้
หากไม่พอใจราคา เราส่งเครื่องคืนฟรี
ไม่มีค่าใช้จ่ายใดๆ ทั้งสิ้น

━━━━━━━━━━━━━━━
พร้อมแจ้งซ่อมไหมครับ?
กดปุ่ม "แจ้งซ่อม" หรือพิมพ์ 2 ได้เลยครับ"""

SHIPPING_MESSAGE = """📦 วิธีส่งเครื่องมาซ่อม SolarFiX

1️⃣ แพ็คเครื่องให้แน่น
ใช้ฟองน้ำหรือกระดาษกันกระแทกรอบเครื่อง

2️⃣ เขียน Ticket ID บนกล่อง
(ได้รับ Ticket ID หลังจากแจ้งซ่อมแล้ว)

3️⃣ ส่งมาที่อยู่นี้:
━━━━━━━━━━━━━━━
📍 บริษัท เจริญนราพัฒน์ จำกัด
114 หมู่ 9 ต.บัวใหญ่
อ.น้ำพอง จ.ขอนแก่น 40140
📞 097-951-5096
━━━━━━━━━━━━━━━
🚚 ส่งได้ทุกบริษัทขนส่ง
แนะนำ Flash Express / Kerry / ไปรษณีย์ไทย

⚠️ ยังไม่มีกล่องส่ง?
กดปุ่ม "แจ้งซ่อม" เพื่อแจ้งข้อมูลก่อนได้เลยครับ 😊"""

TRACKING_MESSAGE = """🔍 ติดตามสถานะการซ่อม SolarFiX

กรุณาแจ้ง Ticket ID ของคุณครับ
(รูปแบบ: SF-YYYYMMDD-XXX)

━━━━━━━━━━━━━━━
ยังไม่มี Ticket ID?
→ กดปุ่ม "แจ้งซ่อม" เพื่อเริ่มต้นได้เลยครับ

หรือติดต่อ Admin โดยตรง
→ กดปุ่ม "ติดต่อ Admin" ครับ 😊"""

SYSTEM_PROMPT_BUSINESS = """คุณคือ SolarFiX Bot ผู้ช่วยรับแจ้งซ่อมอินเวอร์เตอร์โซลาร์เซลล์

หน้าที่ของคุณคือถามข้อมูลลูกค้าให้ครบ 5 ข้อ ทีละข้อเท่านั้น:
1. ยี่ห้อและรุ่นของอินเวอร์เตอร์
2. กำลังวัตต์ (เช่น 3kW, 5kW)
3. อาการที่พบ
4. Error Code ที่แสดงบนหน้าจอ (ถ้าไม่มีให้บอก "ไม่มี")
5. ชื่อ-นามสกุล, เบอร์โทรศัพท์ และจังหวัดที่อยู่

เมื่อได้ครบ 5 ข้อแล้ว ให้ถามเพิ่ม 1 ข้อ:
6. "สะดวกให้ทีมงานติดต่อกลับเลยตอนนี้ หรือต้องการให้โทรกลับในเวลาที่กำหนดครับ? 😊
   (เช่น ติดต่อได้เลย / วันนี้ 14:00 น. / พรุ่งนี้ 10:00 น.)"

กฎสำคัญ:
- ถามทีละข้อเท่านั้น ห้ามถามคำถามย่อยหรือคำถามเทคนิคเพิ่มเติมเอง
- ห้ามถามเรื่อง DC Switch, LED, Display หรือรายละเอียดเทคนิคใดๆ เพิ่ม
- ถ้าลูกค้าตอบรวมหลายข้อในครั้งเดียว ให้บันทึกและข้ามไปข้อถัดไปได้เลย
- ถ้าลูกค้าตอบว่า "ไม่ทราบ" หรือ "ไม่รู้" ในข้อ 1-4 ให้บันทึกว่า "ไม่ทราบ" และถามข้อถัดไป
- ถ้าลูกค้าตอบว่า "ไม่ทราบ" ในข้อ 3 (อาการ) ให้ตอบว่า:
  "ไม่เป็นไรครับ! 😊 กรุณาทิ้งเบอร์โทรไว้ได้เลยครับ ทีมงานจะโทรหาคุณโดยตรงครับ 📞"
  แล้วรอรับเบอร์โทร จากนั้นให้สรุป [SUMMARY_COMPLETE] ได้เลย
- ใช้ภาษาไทย สุภาพ กระชับ ไม่เยิ่นเย้อ ไม่ถามซ้ำในสิ่งที่ลูกค้าตอบแล้ว

เมื่อได้ข้อมูลครบทุกข้อแล้ว ให้สรุปในรูปแบบนี้ (ใส่ [SUMMARY_COMPLETE] ต่อท้าย):

📋 สรุปข้อมูลการแจ้งซ่อม
━━━━━━━━━━━━━━━
1️⃣ ยี่ห้อ/รุ่น: [ข้อมูล]
2️⃣ กำลังวัตต์: [ข้อมูล]
3️⃣ อาการ: [ข้อมูล]
4️⃣ Error Code: [ข้อมูล]
5️⃣ ชื่อ/เบอร์/จังหวัด: [ข้อมูล]
📞 นัดติดต่อกลับ: [ข้อมูล]
━━━━━━━━━━━━━━━
✅ ทีม SolarFiX จะติดต่อกลับตามเวลาที่คุณสะดวกครับ 🙏

[SUMMARY_COMPLETE]"""

SYSTEM_PROMPT_AFTER_HOURS = """คุณคือ SolarFiX Bot ผู้ช่วยรับแจ้งซ่อมอินเวอร์เตอร์โซลาร์เซลล์

หน้าที่ของคุณคือถามข้อมูลลูกค้าให้ครบ 5 ข้อ ทีละข้อเท่านั้น:
1. ยี่ห้อและรุ่นของอินเวอร์เตอร์
2. กำลังวัตต์ (เช่น 3kW, 5kW)
3. อาการที่พบ
4. Error Code ที่แสดงบนหน้าจอ (ถ้าไม่มีให้บอก "ไม่มี")
5. ชื่อ-นามสกุล, เบอร์โทรศัพท์ และจังหวัดที่อยู่

เมื่อได้ครบ 5 ข้อแล้ว ให้แจ้งลูกค้าและถามเพิ่ม 1 ข้อ:
6. "ขอบคุณครับ! ขณะนี้เป็นนอกเวลาทำการครับ (เวลาทำการ 08:00-20:00 น.)
   ทีมงานจะติดต่อกลับในเวลาทำการถัดไปครับ
   กรุณาแจ้งเวลาที่สะดวกให้โทรกลับด้วยครับ 😊
   (เช่น พรุ่งนี้ 09:00 น. / พรุ่งนี้ 13:00 น.)"

กฎสำคัญ:
- ถามทีละข้อเท่านั้น ห้ามถามคำถามย่อยหรือคำถามเทคนิคเพิ่มเติมเอง
- ห้ามถามเรื่อง DC Switch, LED, Display หรือรายละเอียดเทคนิคใดๆ เพิ่ม
- ถ้าลูกค้าตอบรวมหลายข้อในครั้งเดียว ให้บันทึกและข้ามไปข้อถัดไปได้เลย
- ถ้าลูกค้าตอบว่า "ไม่ทราบ" หรือ "ไม่รู้" ในข้อ 1-4 ให้บันทึกว่า "ไม่ทราบ" และถามข้อถัดไป
- ถ้าลูกค้าตอบว่า "ไม่ทราบ" ในข้อ 3 (อาการ) ให้ตอบว่า:
  "ไม่เป็นไรครับ! 😊 กรุณาทิ้งชื่อและเบอร์โทรไว้ได้เลยครับ ทีมงานจะโทรหาคุณในเวลาทำการครับ 📞"
  แล้วรอรับชื่อและเบอร์โทร จากนั้นให้สรุป [SUMMARY_COMPLETE] ได้เลย
- ใช้ภาษาไทย สุภาพ กระชับ ไม่เยิ่นเย้อ ไม่ถามซ้ำในสิ่งที่ลูกค้าตอบแล้ว

เมื่อได้ข้อมูลครบทุกข้อแล้ว ให้สรุปในรูปแบบนี้ (ใส่ [SUMMARY_COMPLETE] ต่อท้าย):

📋 สรุปข้อมูลการแจ้งซ่อม
━━━━━━━━━━━━━━━
1️⃣ ยี่ห้อ/รุ่น: [ข้อมูล]
2️⃣ กำลังวัตต์: [ข้อมูล]
3️⃣ อาการ: [ข้อมูล]
4️⃣ Error Code: [ข้อมูล]
5️⃣ ชื่อ/เบอร์/จังหวัด: [ข้อมูล]
📞 นัดติดต่อกลับ: [ข้อมูล]
⏰ หมายเหตุ: แจ้งนอกเวลาทำการ
━━━━━━━━━━━━━━━
✅ ทีม SolarFiX จะติดต่อกลับในเวลาที่คุณสะดวกครับ 🙏

[SUMMARY_COMPLETE]"""

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
    user_message = event.message.text.strip()

    if user_id == ADMIN_USER_ID:
        return

    session = user_sessions.get(user_id, {"state": "new", "history": []})

    # --- GLOBAL KEYWORDS ---

    if user_message in ["เริ่มใหม่", "reset", "เมนู", "menu", "หน้าหลัก"]:
        user_sessions[user_id] = {"state": "menu", "history": []}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=WELCOME_MESSAGE)
        )
        return

    if user_message == "แจ้งซ่อม":
        user_sessions[user_id] = {"state": "collecting", "history": []}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="🔧 เริ่มแจ้งซ่อมได้เลยครับ!\n\n❓ ข้อที่ 1: ยี่ห้อและรุ่นของอินเวอร์เตอร์คืออะไรครับ?\n(เช่น Growatt MIN 5000TL-X, Deye 5K, Solis 3K)")
        )
        return

    if user_message == "วิธีส่งเครื่อง":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=SHIPPING_MESSAGE)
        )
        return

    if user_message == "ติดตามสถานะ":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=TRACKING_MESSAGE)
        )
        return

    if user_message == "ติดต่อ Admin":
        admin_msg = f"🔔 ลูกค้าต้องการติดต่อเจ้าหน้าที่\n📌 LINE User ID: {user_id}"
        line_bot_api.push_message(
            ADMIN_USER_ID,
            TextSendMessage(text=admin_msg)
        )
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="✅ ได้เลยครับ! เจ้าหน้าที่จะติดต่อกลับโดยเร็วที่สุดครับ 😊\n\nหากต้องการเริ่มใหม่ พิมพ์ 'เมนู' ได้เลยครับ")
        )
        return

    # --- STATE: NEW ---
    if session["state"] == "new":
        user_sessions[user_id] = {"state": "menu", "history": []}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=WELCOME_MESSAGE)
        )
        return

    # --- STATE: MENU ---
    if session["state"] == "menu":
        if user_message == "1":
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=FAQ_MESSAGE)
            )
        elif user_message == "2":
            user_sessions[user_id]["state"] = "collecting"
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="🔧 เริ่มแจ้งซ่อมได้เลยครับ!\n\n❓ ข้อที่ 1: ยี่ห้อและรุ่นของอินเวอร์เตอร์คืออะไรครับ?\n(เช่น Growatt MIN 5000TL-X, Deye 5K, Solis 3K)")
            )
        elif user_message == "3":
            admin_msg = f"🔔 ลูกค้าต้องการติดต่อเจ้าหน้าที่\n📌 LINE User ID: {user_id}"
            line_bot_api.push_message(
                ADMIN_USER_ID,
                TextSendMessage(text=admin_msg)
            )
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="✅ ได้เลยครับ! เจ้าหน้าที่จะติดต่อกลับโดยเร็วที่สุดครับ 😊")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณาพิมพ์ 1, 2 หรือ 3\nหรือกดปุ่มเมนูด้านล่างได้เลยครับ 😊")
            )
        return

    # --- STATE: COLLECTING ---
    if session["state"] == "collecting":
        session["history"].append({"role": "user", "content": user_message})

        active_prompt = SYSTEM_PROMPT_BUSINESS if is_business_hours() else SYSTEM_PROMPT_AFTER_HOURS

        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=active_prompt,
            messages=session["history"]
        )

        bot_reply = response.content[0].text
        session["history"].append({"role": "assistant", "content": bot_reply})
        user_sessions[user_id] = session

        if "[SUMMARY_COMPLETE]" in bot_reply:
            clean_reply = bot_reply.replace("[SUMMARY_COMPLETE]", "").strip()
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=clean_reply)
            )
            admin_message = f"🔔 มี Ticket ใหม่!\n\n{clean_reply}\n\n📌 LINE User ID: {user_id}"
            line_bot_api.push_message(
                ADMIN_USER_ID,
                TextSendMessage(text=admin_message)
            )
            user_sessions[user_id] = {"state": "menu", "history": []}
        else:
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

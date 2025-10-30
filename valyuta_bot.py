# valyuta_bot.py
import asyncio
import aiohttp
import aiosqlite
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, aiohttp
from datetime import datetime
import os

# === Sozlamalar ===
API_TOKEN = os.getenv("API_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render avto beradi
CBU_API = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
DB = "kurs.db"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

CODES = {
    "USD": "Dollar", "EUR": "EURO", "KGS": "Qirg'iz so'mi",
    "KZT": "Qo'zoq Tenge", "RUB": "RUBL"
}

# === DB ===
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript('''
            CREATE TABLE IF NOT EXISTS subs (user_id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS rates (code TEXT, rate REAL, ts TEXT);
        ''')
        await db.commit()

async def get_subs():
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT user_id FROM subs") as cur:
            return [r[0] for r in await cur.fetchall()]

async def add_sub(uid): ...
async def del_sub(uid): ...
async def get_last_rate(code): ...
async def save_rate(code, rate): ...

# === API ===
async def fetch_cbu():
    async with aiohttp.ClientSession() as s:
        async with s.get(CBU_API) as r:
            return await r.json() if r.status == 200 else None

def fmt(n): return f"{n:,.0f}".replace(",", " ")

# === Kurs yuborish ===
async def send_kurs():
    data = await fetch_cbu()
    if not data: return

    txt = "*Kurslar yangilandi (CBU)*\n\n"
    rates = {}
    for item in data:
        if item['Ccy'] in CODES:
            rate = float(item['Rate'])
            rates[item['Ccy']] = rate
            txt += f"*{CODES[item['Ccy']]}*: `{fmt(rate)}` UZS\n"
    txt += f"\nSana: {data[0]['Date']}"

    subs = await get_subs()
    for uid in subs:
        try:
            await bot.send_message(uid, txt, parse_mode="Markdown")
        except Exception as e:
            log.error(f"Xabar yuborilmadi {uid}: {e}")

    # Alert
    for code, rate in rates.items():
        last = await get_last_rate(code)
        if last and abs(rate - last) >= 100:
            alert = f"*OGOHLANTIRISH*\n{CODES[code]} kursi o'zgardi!\nHozir: `{fmt(rate)}` UZS"
            for uid in subs:
                try: await bot.send_message(uid, alert, parse_mode="Markdown")
                except: pass
        await save_rate(code, rate)

# === Commandlar ===
@dp.message(Command("start"))
async def start(m: types.Message):
    await add_sub(m.from_user.id)
    await m.answer("Obuna bo'ldingiz!\nHar 6 soatda + o'zgarishda xabar keladi.\n/kurs – hozirgi kurs")

@dp.message(Command("stop"))
async def stop(m: types.Message):
    await del_sub(m.from_user.id)
    await m.answer("Obuna bekor qilindi")

@dp.message(Command("kurs"))
async def kurs(m: types.Message):
    data = await fetch_cbu()
    if not data:
        return await m.answer("Xatolik")
    
    txt = "*Hozirgi kurslar*\n\n"
    for item in data:
        if item['Ccy'] in CODES:
            txt += f"*{CODES[item['Ccy']]}*: `{fmt(float(item['Rate']))}` UZS\n"
    txt += f"\nSana: {data[0]['Date']}"
    await m.answer(txt, parse_mode="Markdown")

# === Cron uchun alohida endpoint ===
@dp.message(Command("cron"))  # Faqat Render ichidan chaqiriladi
async def cron(m: types.Message):
    if m.from_user.id != int(os.getenv("ADMIN_ID", "0")):
        return
    await send_kurs()
    await m.answer("Kurslar yangilandi!")

# === Webhook server ===
async def on_startup(app):
    await init_db()
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await bot.set_webhook(webhook_url)
    log.info(f"Webhook o'rnatildi: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook()
    log.info("Webhook o'chirildi")

async def main():
    app = aiohttp.web.Application()
    app.router.add_post("/webhook", SimpleRequestHandler(dp, bot).handle)
    
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    log.info("Bot ishga tushdi (Webhook)")

    # Har 6 soatda ichki chaqiruv
    async def scheduler():
        while True:
            await send_kurs()
            await asyncio.sleep(21600)

    asyncio.create_task(scheduler())
    await asyncio.Event().wait()  # Doimiy ishlash

if __name__ == "__main__":
    asyncio.run(main())

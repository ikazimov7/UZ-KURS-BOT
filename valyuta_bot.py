# valyuta_bot.py
import asyncio
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from datetime import datetime
import os

API_TOKEN = os.getenv("API_TOKEN")
CBU_API = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
DB = "kurs.db"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

CODES = {
    "USD": "Dollar", "EUR": "EURO", "KGS": "Qirg'iz so'mi",
    "KZT": "Qo'zoq Tenge", "RUB": "RUBL"
}

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

async def add_sub(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO subs (user_id) VALUES (?)", (uid,))
        await db.commit()

async def del_sub(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM subs WHERE user_id=?", (uid,))
        await db.commit()

async def get_last_rate(code):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT rate FROM rates WHERE code=? ORDER BY rowid DESC LIMIT 1", (code,)) as cur:
            r = await cur.fetchone()
            return r[0] if r else None

async def save_rate(code, rate):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO rates (code, rate, ts) VALUES (?, ?, ?)", 
                        (code, rate, datetime.utcnow().isoformat()))
        await db.commit()

async def fetch_cbu():
    async with aiohttp.ClientSession() as s:
        async with s.get(CBU_API) as r:
            if r.status == 200:
                return await r.json()
    return None

def fmt(n):
    return f"{n:,.0f}".replace(",", " ")

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
        except:
            pass

    for code, rate in rates.items():
        last = await get_last_rate(code)
        if last and abs(rate - last) >= 100:
            alert = f"*OGOHLANTIRISH*\n{CODES[code]} kursi o'zgardi!\nHozir: `{fmt(rate)}` UZS"
            for uid in subs:
                try: await bot.send_message(uid, alert, parse_mode="Markdown")
                except: pass
        await save_rate(code, rate)

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

async def every_6_hours():
    while True:
        await send_kurs()
        await asyncio.sleep(180)  # 6 soat

async def main():
    await init_db()
    asyncio.create_task(every_6_hours())
    print("Bot Renderda ishga tushdi")
    await dp.start_polling(bot)
    
# Kodning oxiriga, if __name__ == "__main__": dan oldin qo‘shing

@dp.message(Command("update"))
async def update(m: types.Message):
    await send_kurs()
    await m.answer("Kurslar yangilandi!")
    
if __name__ == "__main__":
    asyncio.run(main())

from aiogram import Bot
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import Dispatcher
from aiogram.types import Message
from aiogram.utils import executor
import sqlite3
import asyncio
import aioschedule
import datetime
from settings import TOKEN
from urllib.request import urlopen
from bs4 import BeautifulSoup

bot = Bot(TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


connect = sqlite3.connect('base.db')
cursor = connect.cursor()


async def on_startup(_):
    connect.execute('CREATE TABLE IF NOT EXISTS users(id_user INTEGER, first_name TEXT, last_name TEXT, username TEXT, notify BLOB)')
    connect.execute('CREATE TABLE IF NOT EXISTS notifications(id_user INTEGER, date TEXT, text TEXT, sent BLOB)')
    connect.commit()

    asyncio.create_task(scheduler())


def shielding(text):
    text_result = ''
    forbidden_characters = '_*[]()~">#+-=|{}.!'
    for i in text:
        if i in forbidden_characters:
            text_result += '\\' + i
        else:
            text_result += i

    return text_result


async def parsing_url(url):
    html = urlopen(url).read()
    soup = BeautifulSoup(html, features="html.parser")
    for script in soup(["script", "style"]):
        script.extract()
    page_text = soup.get_text()
    lines = (line.strip() for line in page_text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    page_text = '\n'.join(chunk for chunk in chunks if chunk)
    page_text_list = page_text.splitlines()
    search_text = 'ТСН «Орешек»'
    for i in page_text_list:
        if i.find(search_text) > 0:
            index = page_text_list.index(i)
            while index > 0:
                index -= 1
                str = page_text_list[index]
                try:
                    date = datetime.datetime.strptime(str[:10], '%d.%m.%Y')
                    return date, shielding(str + ' \nПодробнее на сайте ' + url)
                except Exception:
                    pass

    return datetime.datetime.strptime('01.01.0001', '%d.%m.%Y'), ''


async def scheduler():
    aioschedule.every().day.do(get_send_info)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)


async def get_info(id_user=None):
    if id_user is None:
        cursor.execute(f'SELECT id_user FROM users WHERE notify = 1')
        users_typle = cursor.fetchall()
    else:
        users_typle = ((id_user,),)

    answer = []
    urls = ["https://sevenergo.net/news/plan.html", "https://sevenergo.net/news/official.html", "https://sevenergo.net/news/incident.html"]
    for url in urls:
        date, text = await parsing_url(url)
        if not text == '':
            cursor.execute(f'SELECT * FROM notifications WHERE date = "{date}" AND text = "{text}"')
            result = cursor.fetchone()
            if result is None:
                for i in users_typle:
                    cursor.execute(f'INSERT INTO notifications (id_user, date, text, sent) VALUES ({i[0]}, "{date}", "{text}", 0)')
                    connect.commit()

        answer.append((date, text))

    return answer


async def get_send_info(users=None):
    await get_info(users)

    cursor.execute(f'SELECT * FROM notifications WHERE sent = 0')
    notifications_typle = cursor.fetchall()
    for i in notifications_typle:
        await bot.send_message(chat_id=i[0], text=i[2], parse_mode='MarkdownV2', disable_web_page_preview=True)
        cursor.execute(f'UPDATE notifications SET sent = 1')
        connect.commit()

    today = datetime.datetime.today()
    tomorrow = today + datetime.timedelta(days=1)
    tomorrow_text = tomorrow.strftime('%Y-%m-%d 00:00:00')
    cursor.execute(f'SELECT * FROM notifications WHERE date = "{tomorrow_text}"')
    notifications_typle = cursor.fetchall()
    for i in notifications_typle:
        await bot.send_message(chat_id=i[0], text=i[2], parse_mode='MarkdownV2', disable_web_page_preview=True)


async def get_info_user(id_user):
    answer = await get_info(id_user)
    date1, text1 = answer[0]
    date2, text2 = answer[1]
    date3, text3 = answer[2]

    text = text1

    if not text2 == '':
        if not text == '':
            text += '\n'
        text += text2

    if not text3 == '':
        if not text == '':
            text += '\n'
        text += text3

    return text


@dp.message_handler(commands=['start', 'stop', 'check'])
async def command_start(message: Message):
    id_user = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    if last_name is None:
        last_name = ''
    username = message.from_user.username
    if username is None:
        username = ''
    cursor.execute(f'SELECT * FROM users WHERE id_user = {id_user}')
    result = cursor.fetchone()

    if result is None:
        cursor.execute(
            'INSERT INTO users (id_user, first_name, last_name, username, notify) '
            f'VALUES ({id_user}, "{first_name}", "{last_name}", "{username}", 1)')
    else:
        cursor.execute(f'UPDATE users SET first_name = "{first_name}", last_name = "{last_name}", '
                       f'username = "{username}", notify = 1 WHERE id_user = {id_user}')
    connect.commit()

    text = ''
    if message.text == '/start':
        text = 'Здравствуйте\! Теперь вы подписаны на уведомления\.'
    elif message.text == '/stop':
        text = 'Вы больше не будете получать уведомления\.'
        cursor.execute(f'UPDATE users SET notify = 0')
        connect.commit()
    elif message.text == '/check':
        await message.answer('Ищем информацию, минуту\.\.\.', parse_mode='MarkdownV2', disable_web_page_preview=True)
        text = await get_info_user(id_user)
        if text == '':
            text = 'Информации об отключениях электроэнергии не найдено.'

    if not text == '':
        await message.answer(text, parse_mode='MarkdownV2', disable_web_page_preview=True)


executor.start_polling(dp, skip_updates=False, on_startup=on_startup)
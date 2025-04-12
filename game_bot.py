import asyncio
import logging
import sys
import urllib.parse
import aiohttp
import json
import html as html_escape

from datetime import datetime

from aiogram import Router, html
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BASE_GAME_URL = "https://t.me/timonqi_bot?game=bandit0"
FIREBASE_DB_URL = "https://timonqibot-default-rtdb.firebaseio.com"

leaderboard_cache = {
    "data": None,
    "last_updated": 0,
    "ttl": 10
}

http_session: aiohttp.ClientSession = None

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s - %(levelname)s - %(message)s')

router = Router()

async def update_leaderboard_cache():
    global leaderboard_cache, http_session
    while True:
        try:
            top_players_url = f"{FIREBASE_DB_URL}/scores.json?orderBy=\"maxScore\"&limitToLast=10"
            logging.info(f"Обновление кеша лидерборда: {top_players_url}")
            async with http_session.get(top_players_url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    leaderboard_cache["data"] = data
                    leaderboard_cache["last_updated"] = asyncio.get_event_loop().time()
                    logging.info("Кеш лидерборда успешно обновлён")
                else:
                    logging.error(f"Ошибка обновления кеша: статус {response.status}")
        except Exception as e:
            logging.error(f"Ошибка обновления кеша лидерборда: {e}", exc_info=True)
        await asyncio.sleep(leaderboard_cache["ttl"])


@router.message(Command("play"))
async def send_game_button(message: Message):
    user = message.from_user
    user_id = str(user.id)
    user_name = user.full_name
    encoded_user_name = urllib.parse.quote(user_name)

    logging.info(f"Команда /start или /play от пользователя {user_id} ({user_name})")

    if not BASE_GAME_URL or BASE_GAME_URL == "СЮДА_ВАШ_HTTPS_URL_ИГРЫ_С_GITHUB_PAGES":
         logging.warning("BASE_GAME_URL не установлен!")
         await message.answer("Извините, URL игры не настроен.")
         return

    try:
        game_url_with_params = f"{BASE_GAME_URL}?userId={user_id}&userName={encoded_user_name}"
        logging.info(f"Сгенерирован URL для пользователя {user_id}: {game_url_with_params}")

        web_app_info = WebAppInfo(url=game_url_with_params)

        play_button = InlineKeyboardButton(
            text="🚀 Запустить Игру!",
            web_app=web_app_info
        )

        leaderboard_button = InlineKeyboardButton(
            text="🏆 Таблица лидеров",
            callback_data="show_leaderboard"
        )

        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [play_button],
            [leaderboard_button]
        ])

        await message.answer(
            f"Привет, {html.bold(user_name)}!\n\n"
            "Готов уворачиваться? 😉\n"
            "Нажми кнопку ниже, чтобы начать!",
            reply_markup=inline_keyboard
        )
        logging.info(f"Кнопка для запуска игры отправлена пользователю {user_id}")

    except Exception as e:
        logging.error(f"Ошибка при отправке кнопки игры пользователю {user_id}: {e}", exc_info=True)
        await message.answer("Ой! Что-то пошло не так. Попробуйте позже.")


@router.message(Command("leaderboard"))
async def show_leaderboard_command(message: Message):
    user_id = str(message.from_user.id)
    await fetch_and_show_leaderboard(message, user_id)


@router.message(Command("help"))
async def show_help(message: Message):
    help_text = (
        "🎮 <b>Игровой бот - Справка</b>\n\n"
        "Доступные команды:\n"
        "/play - Запустить игру\n"
        "/leaderboard - Показать таблицу лидеров\n"
        "/profile - Посмотреть свой профиль\n"
        "/help - Показать эту справку\n\n"
        "Удачной игры! 🍀"
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)


@router.message(Command("profile"))
async def show_profile(message: Message):
    user = message.from_user
    user_id = str(user.id)
    user_name = user.full_name

    try:
        url = f"{FIREBASE_DB_URL}/scores/{user_id}.json"
        async with http_session.get(url, timeout=10) as response:
            if response.status != 200:
                await message.answer("Не удалось получить данные вашего профиля. Попробуйте позже.")
                return

            player_data = await response.json()

            if not player_data:
                profile_text = (
                    f"👤 <b>Профиль игрока</b>\n\n"
                    f"Имя: {html_escape.escape(user_name)}\n"
                    f"ID: {user_id}\n\n"
                    f"Вы еще не играли. Нажмите /play чтобы начать!"
                )
            else:
                max_score = player_data.get('maxScore', 0)
                last_update = player_data.get('lastUpdate', 0)
                last_played = "Никогда"
                if last_update:
                    date_obj = datetime.fromtimestamp(last_update / 1000)
                    last_played = date_obj.strftime('%d.%m.%Y %H:%M')

                profile_text = (
                    f"👤 <b>Профиль игрока</b>\n\n"
                    f"Имя: {html_escape.escape(player_data.get('name', user_name))}\n"
                    f"ID: {user_id}\n\n"
                    f"📊 <b>Статистика:</b>\n"
                    f"Лучший результат: {max_score} очков\n"
                    f"Последняя игра: {last_played}\n\n"
                    f"Нажмите /play, чтобы начать новую игру!"
                )
            await message.answer(profile_text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при получении профиля: {e}", exc_info=True)
        await message.answer("Ой! Не удалось получить данные профиля. Попробуйте позже.")


@router.callback_query(lambda c: c.data == "show_leaderboard")
async def show_leaderboard_callback(callback_query):
    user_id = str(callback_query.from_user.id)
    await callback_query.answer()
    await fetch_and_show_leaderboard(callback_query.message, user_id)


async def fetch_and_show_leaderboard(message, user_id):
    global leaderboard_cache, http_session
    try:
        current_time = asyncio.get_event_loop().time()
        if leaderboard_cache["data"] and (current_time - leaderboard_cache["last_updated"]) < leaderboard_cache["ttl"]:
            top_players_data = leaderboard_cache["data"]
            logging.info("Используем кеш лидерборда")
        else:
            top_players_url = f"{FIREBASE_DB_URL}/scores.json?orderBy=\"maxScore\"&limitToLast=10"
            async with http_session.get(top_players_url, timeout=10) as response:
                if response.status != 200:
                    logging.error(f"Ошибка при запросе к Firebase: {response.status}")
                    await message.answer("Не удалось получить данные таблицы лидеров. Попробуйте позже.")
                    return
                top_players_data = await response.json()
                leaderboard_cache["data"] = top_players_data
                leaderboard_cache["last_updated"] = current_time

        if not top_players_data:
            await message.answer("Таблица лидеров пуста! Будь первым, кто установит рекорд! 🏆")
            return

        top_players = []
        for player_id_key, player_data in top_players_data.items():
            if isinstance(player_data, dict) and 'maxScore' in player_data:
                entry = {
                    'id': player_id_key,
                    'name': player_data.get('name', 'Unknown'),
                    'maxScore': player_data.get('maxScore', 0)
                }
                top_players.append(entry)

        top_players.sort(key=lambda x: x['maxScore'], reverse=True)

        player_info = None
        player_rank = -1

        for i, player in enumerate(top_players):
            if player['id'] == user_id:
                player_info = player
                player_rank = i + 1
                break

        if not player_info:
            player_url = f"{FIREBASE_DB_URL}/scores/{user_id}.json"
            async with http_session.get(player_url, timeout=10) as player_response:
                if player_response.status == 200:
                    player_data = await player_response.json()
                    if player_data and 'maxScore' in player_data:
                        player_info = {
                            'id': user_id,
                            'name': player_data.get('name', 'Unknown'),
                            'maxScore': player_data.get('maxScore', 0)
                        }

                        rank_url = f"{FIREBASE_DB_URL}/scores.json?orderBy=\"maxScore\"&startAt={player_info['maxScore'] + 1}&shallow=true"
                        async with http_session.get(rank_url, timeout=10) as rank_response:
                            if rank_response.status == 200:
                                better_players_data = await rank_response.json()
                                better_count = len(better_players_data) if better_players_data else 0
                                player_rank = better_count + 1

        message_text = "🏆 <b>ТАБЛИЦА ЛИДЕРОВ</b> 🏆\n\n"
        for i, entry in enumerate(top_players):
            rank = i + 1
            name = html_escape.escape(entry.get('name', 'Unknown'))
            score = entry.get('maxScore', 0)
            if entry.get('id') == user_id:
                message_text += f"{rank}. 👉 <b>{name}</b>: {score} очков\n"
            else:
                message_text += f"{rank}. {name}: {score} очков\n"

        if player_info and player_rank > 10:
            message_text += f"\nВаш результат:\n{player_rank}. <b>{html_escape.escape(player_info.get('name', 'Unknown'))}</b>: {player_info.get('maxScore', 0)} очков"
        elif not player_info:
            message_text += "\nУ вас пока нет результатов в таблице. Сыграйте, чтобы получить место в рейтинге!"

        await message.answer(message_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logging.error(f"Ошибка при получении лидерборда: {e}", exc_info=True)
        await message.answer("Ой! Не удалось получить данные таблицы лидеров. Попробуйте позже.")


@router.message(Command("debug_firebase"))
async def debug_firebase(message: Message):
    try:
        url = f"{FIREBASE_DB_URL}.json"
        logging.info(f"Запрос структуры базы: {url}")
        async with http_session.get(url, timeout=10) as response:
            if response.status != 200:
                await message.answer(f"Ошибка при запросе к Firebase: {response.status}")
                return

            data = await response.json()
            result = "📊 <b>Структура базы данных:</b>\n\n"
            if not data:
                result += "База данных пуста или нет доступа."
            else:
                for key, value in data.items():
                    if isinstance(value, dict):
                        count = len(value)
                        result += f"• <b>{key}</b>: {count} записей\n"
                        if count > 0:
                            sample_key = next(iter(value))
                            sample_value = value[sample_key]
                            if isinstance(sample_value, dict):
                                sample_str = json.dumps(sample_value, ensure_ascii=False)
                                result += f"  └ Пример ({sample_key}): {sample_str[:100]}...\n"
                    else:
                        result += f"• <b>{key}</b>: {type(value).__name__}\n"

            await message.answer(result, parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при отладке Firebase: {e}", exc_info=True)
        await message.answer(f"Ошибка: {str(e)}")
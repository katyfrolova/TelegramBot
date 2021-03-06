#!/usr/bin/env python
import os
from collections import defaultdict
import telebot
from telebot import types
import token_bot
import googlemaps
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DATABASE_URL = os.environ['DATABASE_URL']

con = psycopg2.connect(DATABASE_URL, sslmode='require')

con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

db_name = 'allplaces'
cursor = con.cursor()

# try:
#     cursor.execute("CREATE DATABASE %s  ;" % db_name)
# except psycopg2.errors.DuplicateDatabase:
#     con = psycopg2.connect(dbname=db_name,
#           user='postgres', host='/tmp/',
#           password=token_bot.passw2)

try:
    create_table_query = '''CREATE TABLE places
              (user_id INTEGER NOT NULL,
              places_name VARCHAR(50),
              lat VARCHAR(50) DEFAULT NULL,
              lon VARCHAR(50) DEFAULT NULL); '''
    cursor.execute(create_table_query)
    con.commit()
except psycopg2.errors.DuplicateTable:
    pass


bot = telebot.TeleBot(token_bot.TOKEN)
gmaps = googlemaps.Client(key=token_bot.key_map)

START, NAME, LOCATION, NEARBY = range(4)
USER_STATE = defaultdict(lambda: START)

types_list = ['yes', 'NO']

cache = {}

def create_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width = 2)
    buttons = [types.InlineKeyboardButton(text=t, callback_data=t) for t in types_list]
    keyboard.add(*buttons)
    return keyboard


def get_state(message):
    return USER_STATE[message.chat.id]


def update_state(message, state):
    USER_STATE[message.chat.id] = state


def check_location(message):
    if message.text is not None:
        if message.text.startswith('/'):
            bot.send_message(message.chat.id, text="Incorrect command. Try again")
        return False
    elif message.location or message.venue:
        return True



@bot.callback_query_handler(func=lambda x: True)
def callback_handler(callback_query):
    type = callback_query.data
    message = callback_query.message
    cache['type'] = type
    if type == 'yes':
        cursor.execute("DELETE FROM places WHERE user_id = %s",(message.chat.id, ))
        con.commit()
        bot.send_message(message.chat.id, text="I've deleted all of your places")
    else:
        pass
    update_state(message, START)


@bot.message_handler(commands=['start'])
def handle_welcome(message):
    bot.send_message(message.chat.id, text="Hi! I can save all places you're going to visit! Please, start to type with '/' !")



@bot.message_handler(commands=['add'])
def handle_add(message):
    bot.send_message(message.chat.id, text="Send a name of the place")
    update_state(message, NAME)


@bot.message_handler(func=lambda message: get_state(message) == NAME)
def handle_name(message):
    if message.text is not None:
        if message.text.startswith('/'):
            bot.send_message(message.chat.id, text="Incorrect command. Try again")
            update_state(message, START)
        else:
            try:
                cache['id'] = message.chat.id
                cache['name'] = message.text
                update_state(message, LOCATION)
                bot.send_message(message.chat.id, text="Send a location of the place")
            except:
                bot.send_message(message.chat.id, text="Incorrect command. Try again")
                update_state(message, START)
    else:
        bot.send_message(message.chat.id, text="Send a name of the place")


@bot.message_handler(func=lambda message: get_state(message) == NEARBY)
@bot.message_handler(func=lambda message: get_state(message) == LOCATION)
@bot.message_handler(content_types=['location', 'venue'])
def handle_location(message):
    if USER_STATE[message.chat.id] == 2:
        try:
            lon, lat = message.location.longitude, message.location.latitude
            cursor.execute('INSERT INTO places (user_id, places_name, lat, lon) VALUES (%s, %s, %s, %s)', (cache['id'], cache['name'], lat, lon))
            con.commit()
            bot.send_message(message.chat.id, text="Congrats! We've saved another one place!")
            update_state(message, START)
        except:
            bot.send_message(message.chat.id, text="Incorrect command. Try again")
            update_state(message, START)

    if USER_STATE[message.chat.id] == 3:
        if check_location(message) == True:
            lon, lat = message.location.longitude, message.location.latitude
            my_location =f'{lat},{lon}'
            cursor.execute("SELECT * FROM places WHERE user_id = %s",(message.chat.id, ))
            places = cursor.fetchall()

            if places:
                n = []
                for row in places:
                    name = f'{row[1]}'
                    lat, lon = f'{row[2]}',f'{row[3]}'
                    distance = gmaps.distance_matrix(origins=my_location, destinations=f'{lat}, {lon}')
                    meters, km = distance['rows'][0]['elements'][0]['distance']['text'].split(' ')
                    if km == 'km':
                        distance = (float(meters)*100)
                    elif km == 'm':
                        distance = int(meters)

                    if distance < 500:
                        bot.send_message(message.chat.id, text=f"Name: {name}")
                        bot.send_location(message.chat.id, f'{lat}', f'{lon}')
                        n.append(name)
                if n:
                    pass
                else:
                    bot.send_message(message.chat.id, text="I didn't find any place for you!")
            else:
                bot.send_message(message.chat.id, text="No places yet!")
        update_state(message, START)


@bot.message_handler(commands=['reset'])
def handle_reset(message):
    keyboard = create_keyboard()
    bot.send_message(message.chat.id, text="I will delete all of your places. Are you sure?", reply_markup=keyboard)


@bot.message_handler(commands=['list'])
def handle_list(message):
    cursor.execute("SELECT * FROM places WHERE user_id = %s",(message.chat.id, ))
    places = cursor.fetchmany(10)
    if places:
        for row in places:
            name = row[1]
            lat, lon = f'{row[2]}',f'{row[3]}'
            bot.send_message(message.chat.id, text=f"Name: {name}")
            bot.send_location(message.chat.id, f'{lat}', f'{lon}')
    else:
        bot.send_message(message.chat.id, text="No places yet!")
    update_state(message, START)


@bot.message_handler(commands=['nearby'])
def handle_nearby(message):
    bot.send_message(message.chat.id, text='Send your location')
    update_state(message, NEARBY)

@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.send_message(message.chat.id, text='/add - add some place you are going to visit.')
    bot.send_message(message.chat.id, text='/list - I will show you all of your places.')
    bot.send_message(message.chat.id, text='/reset - I will delete all of your places.')
    bot.send_message(message.chat.id, text='/nearby - I will show your places around you.')
    bot.send_message(message.chat.id, text='/help - all commands.')
    update_state(message, START)

bot.polling(none_stop=True)
con.close()

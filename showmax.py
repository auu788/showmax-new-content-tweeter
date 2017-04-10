# -*- coding: utf-8 -*-

import sqlite3
import time
from twython import Twython
import requests
import configparser
from difflib import SequenceMatcher
from urllib.request import urlopen
from filmweb.filmweb import Filmweb

SHOWMAX_API_URL = "http://api.showmax.com/v36.0/website/catalogue/assets?content_country=PL&lang=pol&num=60&subscription_status=full&start="

config = configparser.ConfigParser()
config.read('config.ini')

DB_FILE = config['Config']['DatabaseFile']
POST_TWEETS = config['Config']['PostTweets']

APP_KEY = config['Config']['AppKey']
APP_SECRET = config['Config']['AppSecret']
OAUTH_TOKEN = config['Config']['OAuthToken']
OAUTH_TOKEN_SECRET = config['Config']['OAuthTokenSecret']

current_date = time.strftime("%d-%m-%Y")

fw = Filmweb()

def getRating(item):
    item_title = item['title']
    item_year = str(item['year'])

    items = fw.search(item_title + ' ' + item_year)
    for elem in items:
        elem_title = elem.name
        if SequenceMatcher(None, elem_title, item_title).ratio() > 0.70:
            elem.get_info()
            #print ('Showmax: ' + item_title + ' ' + item_year + ' --- ' + elem_title + ' ' + str(elem.year) + ' ' + str(elem.rate))
            if (abs(int(elem.year) - int(item_year)) < 2):
                return round(elem.rate, 1)

    return 0

def getTotalNumFromAPI(test=True):
    if test == True:
        div = 10
    else:
        div = 1

    data = requests.get(SHOWMAX_API_URL + str(0), timeout=60).json()

    return int(data['total'] / div)

def getAPIData():
    showmax_data = list()
    total_num = getTotalNumFromAPI(False)

    for i in range(0, total_num, 60):
        print ("Retriving data from API: " + str(int((i/60)+1)) + ' / ' + str(total_num // 60 + (total_num % 60 > 0)))

        data = requests.get(SHOWMAX_API_URL + str(i), timeout=60).json()
        showmax_data += data['items']

    return showmax_data

def prepareMsg(item, isChangedSeason, delta, isPolishSub, isPolishAudio, isDeleted, isReverted):
    movie_url = "showmax.com/pol/movie/" + item['slug']
    tvseries_url = "showmax.com/pol/tvseries/" + item['slug']

    if isChangedSeason == True:
        if abs(delta) == 1:
            season_msg = ' sezon'
        elif abs(delta) > 1 and abs(delta) < 5:
            season_msg = ' sezony'
        else:
            season_msg = ' sezonów'
        if delta > 0:
            msg = 'Dodano ' + str(delta) + season_msg + ' serialu ' + item['title'] + ' [teraz jest ich: ' + str(item['count_seasons']) + ']. ' + tvseries_url + ' #ShowMaxPolska'
        else:
            delta = delta * (-1)
            msg = 'Usunięto ' + str(delta) + season_msg + ' serialu ' + item['title'] + ' [teraz jest ich: ' + str(item['count_seasons']) + ']. ' + tvseries_url + ' #ShowMaxPolska'
        return msg

    elif isDeleted == True:
        if item['type'] == 'tv_series':
            msg = 'Usunięto serial ' + item['title'] + " [" + str(item['year']) + "]. #ShowMaxPolska"
        else:
            msg = 'Usunięto film ' + item['title'] + " [" + str(item['year']) + "]. #ShowMaxPolska"
        return msg

    else:
        rating = getRating(item)

        if rating == 0:
            rating_msg = ". "
        else:
            rating_msg = ", FW: " + str(getRating(item)) + " "

        if isPolishSub == True and isPolishAudio == True:
            lang_msg = u' z \U0001F1F5\U0001F1F1 audio/napisami'
        elif isPolishSub == True and isPolishAudio == False:
            lang_msg = u' z \U0001F1F5\U0001F1F1 napisami'
        elif isPolishSub == False and isPolishAudio == True:
            lang_msg = u' z \U0001F1F5\U0001F1F1 audio'
        else:
            lang_msg = ''

        if item['type'] == 'movie':
            if isReverted == True:
                msg = "Przywrócono film " + item['title'] + " [" + str(item['year']) + "]" + lang_msg + '. ' + movie_url + " #ShowMaxPolska"
            else:
                msg = "Dodano film " + item['title'] + " [" + str(item['year']) + "]" + lang_msg + rating_msg + movie_url + " #ShowMaxPolska"
        else:
            if item['count_seasons'] == 1:
                seasons_msg = " sezon"
            elif item['count_seasons'] > 1 and item['count_seasons'] < 5:
                seasons_msg = " sezony"
            else:
                seasons_msg = " sezonów"

            if isReverted == True:
                msg = "Przywrócono serial " + item['title'] + " [" + str(item['year']) + "] [" + str(item['count_seasons']) + seasons_msg + "]" + lang_msg + '. ' + tvseries_url + " #ShowMaxPolska"
            else:
                msg = "Dodano serial " + item['title'] + " [" + str(item['year']) + "] [" + str(item['count_seasons']) + seasons_msg + "]" + lang_msg + rating_msg + tvseries_url + " #ShowMaxPolska"

        return msg

def postOnTwitter(item, isChangedSeason, delta, isPolishSub, isPolishAudio, isDeleted, isReverted):
    if POST_TWEETS == True:
        img_url = None

        if isDeleted == True:
            img_url = item['img_url']
        else:
            for img_item in item['images']:
                if img_item['type'] == 'hero' and img_item['language'] == 'pol':
                    img_url = img_item['link']

        msg = prepareMsg(item, isChangedSeason, delta, isPolishSub, isPolishAudio, isDeleted, isReverted)

        twitter = Twython(APP_KEY, APP_SECRET, OAUTH_TOKEN, OAUTH_TOKEN_SECRET)

        try:
            img = urlopen(img_url)
            response = twitter.upload_media(media=img)
        except:
            response = None

        try:
            twitter.update_status(status=msg, media_ids=[response['media_id']])
        except TypeError:
            twitter.update_status(status=msg)
        except:
            msg = msg[:-15]
            twitter.update_status(status=msg, media_ids=[response['media_id']])

        print (msg)
        print ("Created tweet: " + item['title'])

def addItemToDB(item, revertItem):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if item['type'] == 'boxset':
        return

    is_subbed_pol = False
    is_audio_pol = False
    seasons = None
    img_url = None

    try:
        for audio_item in item['audio_languages']:
            if audio_item == 'pol':
                is_audio_pol = True
    except KeyError:
        pass

    try:
        for subtitle_item in item['subtitles_languages']:
            if subtitle_item == 'pol':
                is_subbed_pol = True
    except KeyError:
        pass

    for img_item in item['images']:
        if img_item['type'] == 'hero' and img_item['language'] == 'pol':
            img_url = img_item['link']

    if item['type'] == 'tv_series':
        seasons = item['count_seasons']
        if seasons == 0:
            print ("TV series has 0 seasons, something is wrong...")
            return

    fw_rating = 0
    fw_rating = getRating(item)

    if revertItem == True:
        c.execute('UPDATE showmax_content SET id=?, slug=?, title=?, year=?, type=?, polish_subtitles=?, polish_audio=?, seasons=?, fw_rating=?, img_url=?, add_date=?, is_removed=? WHERE id=?', (item['id'], item['slug'], item['title'], item['year'], item['type'], is_subbed_pol, is_audio_pol, seasons, fw_rating, img_url, current_date, 0, item['id']))
        conn.commit()
        postOnTwitter(item, False, 0, is_subbed_pol, is_audio_pol, False, True)

    else:
        c.execute("INSERT INTO showmax_content VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);", (item['id'], item['slug'], item['title'], item['year'], item['type'], is_subbed_pol, is_audio_pol, seasons, fw_rating, img_url, current_date, 0))
        conn.commit()
        postOnTwitter(item, False, 0, is_subbed_pol, is_audio_pol, False, False)

    conn.close()

def createContentDB():
    data_api = getAPIData()

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS showmax_content
                 (id TEXT, slug TEXT, title TEXT, year INTEGER, type TEXT, polish_subtitles INTEGER, polish_audio INTEGER, seasons INTEGER, fw_rating DECIMAL, img_url TEXT, add_date TEXT, is_removed INTEGER)''')
    conn.commit()
    conn.close()

    cnt = 1
    for item in data_api:
        print (str(cnt) + ": " + item['title'])
        cnt += 1
        addItemToDB(item, False)

def changeTvSeries(item, delta):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('UPDATE showmax_content SET seasons=? WHERE id=?', (item['count_seasons'], item['id']))
    conn.commit()

    postOnTwitter(item, True, delta, False, False, False, False)
    conn.close()

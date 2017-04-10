import sqlite3
import showmax
import configparser
import argparse
import os

config = configparser.ConfigParser()
config.read('config.ini')

DB_FILE = config['Config']['DatabaseFile']

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
c = conn.cursor()

parser = argparse.ArgumentParser(description='Get polish Showmax data content and tweet about new things.')
parser.add_argument('--init', '-i', action='store_true', help='creates fresh DB')
parser.add_argument('--tweet', '-t', action='store_true', help='tweets about changes in DB')

args = parser.parse_args()
if args.init:
    showmax.createContentDB()
    print ('Creating new DB done.')
    exit()

if not os.path.isfile(DB_FILE):
    print ('There is no DB file, try again: python3 {} --init'.format(os.path.basename(__file__)))
    exit()

if args.tweet:
    showmax.POST_TWEETS = True


try:
    data_db = c.execute('SELECT * FROM showmax_content').fetchall()
except:
    print ('DB is unfinished, try again: python3 {} --init'.format(os.path.basename(__file__)))
    exit()

data_api = showmax.getAPIData()

cnt = 1
for item in data_api:
    if item['type'] != 'boxset':
        if not any(item['id'] in sub for sub in data_db):
            print ("New: " + item['title'] + ' --- ' + item['id'])
            showmax.addItemToDB(item, False)
        else:
            is_removed = c.execute('SELECT is_removed FROM showmax_content WHERE id=?', (item['id'],)).fetchone()
            if is_removed[0] == 1:
                print ("Restored: " + item['title'] + ' --- ' + item['id'])
                showmax.addItemToDB(item, True)

            else:
                if item['type'] == 'tv_series':
                    cnt_seasons = c.execute('SELECT seasons FROM showmax_content WHERE id=?', (item['id'],)).fetchone()
                    delta = item['count_seasons'] - cnt_seasons[0]
                    if item['count_seasons'] > cnt_seasons[0]:
                        print ("No. of seasons changed: " + item['title'] + " [" + str(cnt_seasons[0]) + " -> " + str(item['count_seasons']) + "]")

                    elif item['count_seasons'] < cnt_seasons[0]:
                        print ("No. of seasons changed: " + item['title'] + " [" + str(cnt_seasons[0]) + " -> " + str(item['count_seasons']) + "]")

                    if delta != 0:
                        showmax.changeTvSeries(item, delta)

for item_db in data_db:
    if not any(d['id'] == item_db['id'] for d in data_api) and item_db['is_removed'] == 0:
        print ("Removed: " + item['title'] + ' --- ' + item['id'])
        c.execute('UPDATE showmax_content SET is_removed=? WHERE id=?', (1, item_db['id']))
        conn.commit()
        showmax.postOnTwitter(item_db, False, 0, False, False, True, False)

conn.close()

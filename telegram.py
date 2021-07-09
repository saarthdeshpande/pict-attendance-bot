import telebot
import pandas as pd
import selenium
from selenium import webdriver
from flask import Flask, request
from tabulate import tabulate
from time import sleep
import os
import re
import weasyprint as wsp
import PIL as pil

TOKEN = os.environ.get('TOKEN')

bot = telebot.TeleBot(token=TOKEN)

chrome_options = webdriver.ChromeOptions()
chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

server = Flask(__name__)


def getData(userid, pwd):

    parent_login = userid.lower().startswith('p')

    driver = webdriver.Chrome(executable_path=os.environ.get("CHROMEDRIVER_PATH"), chrome_options=chrome_options)

    driver.get("https://pict.ethdigitalcampus.com/PICT/")

    username = driver.find_element_by_name("loginid")
    username.clear()
    username.send_keys(f"{userid}")

    password = driver.find_element_by_name("password")
    password.clear()
    password.send_keys(f"{pwd}")

    driver.find_element_by_xpath("//input[@type='submit']").click()
    error500 = driver.find_element_by_tag_name("body").text
    if error500.startswith('HTTP Status 500'):
        return 'Site is down.\nPlease try after some time.'
    elif 'Your last login attempt was not successful' in error500:
        raise AttributeError
    if parent_login:
        driver.find_element_by_id("MyWards").click()
        driver.find_elements_by_class_name('img-circle')[1].click()
        sleep(1)
        data = driver.find_elements_by_xpath("//*[contains(@id,'student_attendance_details')]")
    else:
        driver.get("https://pict.ethdigitalcampus.com/DCWeb/form/jsp_sms/StudentsPersonalFolder_pict.jsp?dashboard=1")
        data = driver.find_elements_by_xpath("//*[contains(@class,'MTTD')]")

    scrapedData = []
    for string in data:
        if parent_login:
            scrapedData = string.text.split('\n')
            break
        else:
            scrapedData.append(string.text)

    if parent_login:

        if 'ATTENDANCE DETAILS' not in scrapedData:
            raise AttributeError

        average = float(scrapedData[-1].split()[1])
        cleaned_data = []
        for subject in scrapedData[3:-1]:
            cleaned_data += re.split(' ([0-9]+)', subject)

        attendanceDataframe = pd.DataFrame(
            {'Subject': cleaned_data[::7], 'Total': cleaned_data[1::7], 'Attended': cleaned_data[3::7],
             '%': list(map(lambda x: x[0] + x[1], zip(cleaned_data[5::7], cleaned_data[6::7])))})

    else:
        if 'Subjects' not in scrapedData:
            raise AttributeError

        average = float(scrapedData[scrapedData.index('Average :') + 1])

        scrapedData = scrapedData[68:scrapedData.index('Average :')]

        attendanceDataframe = pd.DataFrame(
            {'Subject': scrapedData[::4], 'Total': scrapedData[1::4], 'Attended': scrapedData[2::4],
             '%': scrapedData[3::4]})

    attendanceDataframe.set_index(['Subject', 'Total', 'Attended', '%'], inplace=True)

    html = wsp.HTML(string=attendanceDataframe.to_html())
    html.write_png(img_filepath, stylesheets=[css])
    trim(img_filepath)

    driver.close()

    return average


def trim(source_filepath, target_filepath=None, background=None):
    if not target_filepath:
        target_filepath = source_filepath
    img = pil.Image.open(source_filepath)
    if background is None:
        background = img.getpixel((0, 0))
    border = pil.Image.new(img.mode, img.size, background)
    diff = pil.ImageChops.difference(img, border)
    bbox = diff.getbbox()
    img = img.crop(bbox) if bbox else img
    img.save(target_filepath)


img_filepath = 'table.png'
css = wsp.CSS(string='''
@page { size: 2048px 2048px; padding: 0px; margin: 0px; }
table, td, tr, th { border: 1px solid black; }
td, th { padding: 4px 8px; }
''')


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
                 "Welcome! Hope this API is useful. For any feedback, please send a message with the first word as "
                 "'feedback' (without the inverted commas).")


@bot.message_handler(commands=['help'])
def send_welcome(message):
    bot.reply_to(message, 'Please enter your MIS Login details.\ne.g.:\nStudent Login: I2K18102551 123456\nParent '
                          'Login: P12333 123456')


@bot.message_handler(func=lambda msg: msg.text is not None and (('2k' in msg.text.lower()) ^ msg.text.lower().startswith('p')) and len(
    msg.text.split()) == 2 and not msg.text.lower().startswith('feedback'))
def send_attendance(message):
    text = message.text.split()
    bot.reply_to(message, 'API created by Saarth Deshpande.\nPlease wait. Loading ...')
    try:
        avg = getData(text[0], text[1])
        if isinstance(avg, str):
            bot.send_message(message.chat.id, f'{avg}')
        else:
            bot.send_photo(message.chat.id, open('table.png', 'rb'))
            bot.reply_to(message, 'Average Attendance: {}'.format(avg))
    except selenium.common.exceptions.NoSuchElementException:
        bot.send_message(message.chat.id, 'Site is down.\nPlease try after some time.')
    except ValueError:
        bot.reply_to(message, 'Attendance not available on MIS yet.')
    except Exception as e:
        print(e)
        bot.reply_to(message, 'Error. Please ensure correct credentials and format.\ne.g.:\nStudent Login: I2K18102551 '
                              '123456\nParent Login: P12333 123456')


@bot.message_handler(func=lambda msg: msg.text is not None and msg.text.lower().startswith('feedback'))
def send_feedback(message):
    bot.reply_to(message, 'Thank you for your feedback.')
    try:
        bot.send_message(255404186,
                         '****FEEDBACK****\n\n' + str(message.text) + '\n\n by ' + str(message.chat.first_name) + ' (' + str(message.chat.username) + ')')
    except Exception as e:
        print('Error sending feedback: ' + str(e))


@server.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://tranquil-sea-14525.herokuapp.com/' + TOKEN)
    return "!", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9876))
    server.run(host="0.0.0.0", port=port)

# -*- coding: utf-8 -*-
# vim: set ts=4 sts=4 sw=4 noet:

# Python imports.
import datetime
import urllib
import urllib2

# GAE imports.
from google.appengine.api import urlfetch

# site imports.
import config
import model
import oauth

def shorten_url(url):
	"""
	Возвращает сокращённый адрес страницы.  Если сокращение не работает —
	возвращает исходный адрес.
	"""
	args = { 'login': config.BITLY_NAME, 'apiKey': config.BITLY_KEY, 'domain': 'j.mp', 'format': 'txt', 'longUrl': url }
	url = 'http://api.bit.ly/v3/shorten?' + urllib.urlencode(args)
	result = urlfetch.fetch(url)
	if result.status_code != 200:
		return args['longUrl']
	return result.content


def twit(message):
	"""
	Отправляет в твиттер произвольное сообщение.
	"""
	client = oauth.TwitterClient(config.TWITTER_CONSUMER_KEY, config.TWITTER_CONSUMER_SECRET, 'http://%s/verify' % config.HOSTNAME)
	result = client.make_request('http://twitter.com/statuses/update.json',
		token=config.TWITTER_ACCESS_TOKEN_KEY,
		secret=config.TWITTER_ACCESS_TOKEN_SECRET,
		additional_params={'status':message},
		method=urlfetch.POST)


def twit_event(event):
	"""
	Отправляет в twitter сообщение о событии.
	"""
	date = event.date.strftime('%d.%m')
	time = event.date.strftime('%H:%M')
	text = u'%s в %s, %s. %s' % (date, time, event.title, event.short_url)
	twit(text)


def get_csv():
	"""
	Формирует CSV файл с подписчиками.
	"""
	text = ''
	mails = phones = 0
	for email in model.Email.all().order('email').fetch(1000):
		if email.confirmed:
			date = email.date_added.strftime('%Y-%m-%d')
			text += '%s,%s,\n' % (date, email.email)
			mails += 1
	for phone in model.Phone.all().order('phone').fetch(1000):
		if phone.confirmed:
			date = phone.date_added.strftime('%Y-%m-%d')
			text += '%s,,%s\n' % (date, phone.phone)
			phones += 1
	header = 'added on,email (%u),phone (%u)\n' % (mails, phones)
	return header + text


def fetch(url, data=None):
    if data is not None:
        url += '?' + urllib.urlencode(data)
    result = urlfetch.fetch(url)
    if result.status_code != 200:
        raise Exception('Could not fetch ' + url)
    return result.content


def now():
	"""Returns current time, fixes TZ to MSK."""
	return datetime.datetime.now() + datetime.timedelta(0, 0, 0, 0, 0, config.TZ)

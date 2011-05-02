# -*- coding: utf-8 -*-
# vim: set ts=4 sts=4 sw=4 noet:

# Python imports
import datetime
import logging
import os
import random
import re
import urlparse
import urllib
import wsgiref.handlers

# GAE imports
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.api.labs import taskqueue
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# Site imports.
import config
import model
import util

def send_sms(phone, text):
	options = {
		'api_id': config.SMS_ID,
		'to': phone,
		'text': text.encode('utf-8'),
	}
	if hasattr(config, 'SMS_FROM'):
		options['from'] = config.SMS_FROM
	util.fetch('http://sms.ru/sms/send', options)
	logging.info('Sent an SMS to %s' % phone)



class BaseRequestHandler(webapp.RequestHandler):
	def render(self, template_name, vars={}, ret=False, mime_type='text/html'):
		u"""
		Вызывает указанный шаблон, возвращает результат.
		"""
		vars['base'] = self.getBaseURL()
		vars['self'] = self.request.uri
		vars['host'] = self.getHost()
		#vars['styles'] = self.get_styles(vars['host'])
		#vars['scripts'] = self.get_scripts(vars['host'])
		vars['logout_uri'] = users.create_logout_url(self.request.uri)
		vars['login_uri'] = users.create_login_url(self.request.uri)
		vars['admin'] = users.is_current_user_admin()
		directory = os.path.dirname(__file__)
		path = os.path.join(directory, 'templates', template_name)
		response = template.render(path, vars)
		if not ret:
			self.response.headers['Content-Type'] = mime_type + '; charset=utf-8'
			self.response.out.write(response)
		return response

	def send_mail(self, address, subject, template_name, template_vars=None):
		if not template_vars:
			template_vars = dict()
		template_vars['address'] = address
		template_vars['base'] = self.getBaseURL()
		template_vars['host'] = self.getHost()
		path = os.path.join(os.path.dirname(__file__), 'templates', template_name)
		text = template.render(path + '.txt', template_vars)
		html = template.render(path + '.html', template_vars)
		mail.send_mail(sender=config.ADMIN, to=address, subject=subject, body=text, html=html)


	def getBaseURL(self):
		"""
		Возвращает базовый адрес текущего сайта.
		"""
		url = urlparse.urlparse(self.request.url)
		return url[0] + '://' + url[1] + '/'

	def getHost(self):
		url = urlparse.urlparse(self.request.url)
		return url[1]


class IndexHandler(BaseRequestHandler):
	"""
	Вывод главной страницы.  Выводит 20 ближайших событий через шаблон
	index.html.
	"""
	def get(self):
		# Считаем количество предстоящих событий.
		upcoming = model.Event.gql('WHERE date > :1', util.now() + datetime.timedelta(0, 0, 0, 0, 0, -8)).count()

		# Загружаем все события.
		events = model.Event.all().order('date').fetch(1000)

		gaid = hasattr(config, 'GA_ID') and config.GA_ID or None
		self.render('index.html', {
			'events': events,
			'status': {
				'subscribed': self.request.get('status') == 'subscribed',
				'mod': self.request.get('status') == 'mod',
			},
			'start_event': len(events) - upcoming + 1,
			'gaid': gaid,
		})


class SubmitHandler(BaseRequestHandler):
	"""
	Добавление события в список.  Если событие с таким URL уже есть,
	обвновляется информация о существующем.  После обработки данных
	пользователя отправляют на главную страницу.
	"""
	def get(self):
		if self.request.get('key'):
			event = model.get_by_key(self.request.get('key'))
		else:
			event = None
		self.render('submit.html', {
			'wtf': 'hello',
			'event': event,
			'event_exists': event and event.is_saved(),
		})

	def post(self):
		date = datetime.datetime.strptime(self.request.get('date')[:16], '%Y-%m-%d %H:%M')
		title = self.request.get('title').strip()
		url = self.request.get('url').strip() or None
		poster = self.request.get('poster').strip() or None
		video = self.request.get('video').strip() or None
		discount = self.request.get('discount') and True or False

		if self.request.get('key'):
			event = model.get_by_key(self.request.get('key'))
		else:
			event = model.Event(user=users.get_current_user())
			event.far_sent = False
			event.soon_sent = False

		event.url = url
		event.short_url = util.shorten_url(url)
		event.date = date
		event.title = title
		event.poster = poster
		event.video = video
		event.discount = discount
		event.put()
		self.redirect('/')

		"""
		text = u'Date: %s\nTitle: %s\nURL: %s' % (self.request.get('date'), title, url)
		html = u'<html><body><table><tr><th>Date:</th><td>%s</td></tr><tr><th>Title:</th><td>%s</td></tr><tr><th>URL:</th><td>%s</td></tr></table></body></html>' % (self.request.get('date'), title, url)
		mail.send_mail(sender=config.ADMIN, to=config.ADMIN, subject='New event', body=text, html=html)
		self.redirect('/?status=mod')
		"""


class SubscribeHandler(BaseRequestHandler):
	"""
	Добавление данных в список рассылки.  Обрабатывает параметры email и phone,
	сохраняя их как одноимённые объекты.  Существующие объекты не дублируются.
	"""
	def get(self):
		self.render('subscribe.html')

	def post(self):
		phone = email = None
		if self.request.get('email_address'):
			email = model.Email.gql('WHERE email = :1', self.request.get('email_address')).get()
			if email is None:
				email = model.Email(email=self.request.get('email_address'))
		if self.request.get('phone_number'):
			number = self.__normalize_phone_number(self.request.get('phone_number'))
			phone = model.Phone.gql('WHERE phone = :1', number).get()
			if phone is None:
				phone = model.Phone(phone=number)
		redirect = self._process(phone, email)
		if redirect:
			self.redirect(redirect)
		else:
			self.render('subscription_ok.html')


	def _process(self, phone, email):
		redirect = None
		code = random.randrange(1111, 9999)
		if phone is not None and not phone.confirmed:
			phone.confirm_code = code
			phone.put()
			send_sms(phone.phone, u'Код подтверждения подписки на %s: %s' % (config.HOSTNAME, code))
			redirect = '/subscribe/confirm/phone?number=' + urllib.quote(phone.phone)
		if email is not None and not email.confirmed:
			email.confirm_code = code
			email.put()
			self.send_mail(email.email, u'Подтверждение подписки на %s' % config.HOSTNAME, 'email_add', {
				'code': email.confirm_code,
			})
		return redirect


	def __normalize_phone_number(self, number):
		number = re.sub('[^0-9]', '', self.request.get('phone_number'))
		if number.startswith('8'):
			number = '7' + number[1:]
		if not number.startswith('7'):
			number = '7' + number
		return '+' + number


	def add(self):
		next = '/'
		email = self.request.get('email')
		if email:
			obj = model.Email.gql('WHERE email = :1', email).get()
			if obj is None:
				obj = model.Email(email=email)
				obj.put()
			next = '/?status=subscribed'
		phone = self.request.get('phone')
		if phone:
			# Коррекция формата номера.
			if phone.startswith('8'): phone = '+7' + phone[1:]
			phone = phone.replace(' ', '')
			obj = model.Phone.gql('WHERE phone = :1', phone).get()
			if obj is None:
				obj = model.Phone(phone=phone)
				obj.put()
			next = '/?status=subscribed'
		self.redirect(next)

	def remove(self):
		email = self.request.get('email', 'n/a')
		phone = self.request.get('phone', 'n/a')
		text = 'Email: %s\nPhone: %s' % (email, phone)
		mail.send_mail(sender=config.ADMIN, to=config.ADMIN, subject='Unsubscribe request', body=text)


class UnsubscribeHandler(SubscribeHandler):
	def get(self):
		self.render('unsubscribe.html', {
			'phone': self.request.get('phone'),
		})

	def _process(self, phone, email):
		redirect = None
		code = random.randrange(1111, 9999)
		if email is not None and email.confirmed:
			email.confirm_code = code
			email.put()
			self.send_mail(email.email, u'Подтверждение отказа от напоминаний', 'email_remove', {
				'code': email.confirm_code,
			})
		if phone is not None and phone.confirmed:
			phone.confirm_code = code
			phone.put()
			send_sms(phone.phone, u'Код подтверждения отказа от напоминаний на %s: %s' % (config.HOSTNAME, code))
			redirect = '/unsubscribe/confirm/phone?number=' + urllib.quote(phone.phone)
		return redirect


class HourlyCronHandler(BaseRequestHandler):
	"""
	Находит события, по которым ещё не были отправлены уведомления, но уже
	пора, и добавляет их в очередь.  Количество дней, за которое отправляется
	уведомление, настраивается в файле config.py, параметрами FAR_LIMIT и
	SOON_LIMIT.

	При отправке уведомлений выбираются все события, до которых осталось менее
	определённого времени (FAR_LIMIT или SOON_LIMIT).  При том, что обработчик
	вызывается каждый час, получается, что при SOON_LIMIT уведомления
	отправляются для событий, до которых осталось от 23 до 24 часов.
	"""
	def get(self):
		hour = util.now().hour
		if hour < 12 or hour > 22:
			self.response.headers['Content-Type'] = 'text/plain'
			self.response.out.write('Delayed.')
			return

		emails = [x for x in model.Email.all().fetch(1000) if x.confirmed]
		phones = [x for x in model.Phone.all().fetch(1000) if x.confirmed]
		count = 0 # количество поставленных в очередь событий
		now = util.now()

		# Отправка уведомлений за неделю
		d1 = now + datetime.timedelta(config.FAR_LIMIT)
		for event in model.Event.gql('WHERE far_sent = :1 AND date < :2 AND date > :3', False, d1, now).fetch(10):
			count += self.notify(event, emails, phones, True)
			event.far_sent = True
			event.put()

		# Отправка уведомлений за сутки
		d1 = now + datetime.timedelta(config.SOON_LIMIT)
		for event in model.Event.gql('WHERE soon_sent = :1 AND date < :2 AND date > :3', False, d1, now).fetch(10):
			count += self.notify(event, emails, phones, False)
			event.soon_sent = True
			event.far_sent = True
			event.put()

		if count:
			logging.info('Queued %u notifications.' % count)

	def notify(self, event, emails, phones, week=False):
		count = 0
		util.twit_event(event)
		for email in emails:
			taskqueue.Task(url='/notify', params={ 'event': event.key(), 'email': email.email, 'week': week }).add()
			count += 1
		for phone in phones:
			taskqueue.Task(url='/notify', params={ 'event': event.key(), 'phone': phone.phone, 'week': week }).add()
			count += 1
		return count


class DailyCronHandler(BaseRequestHandler):
	"""
	Отправляет администратору список подписчиков в CSV.  Вызывается каждую
	ночь.  Нужно как архив, на случай повреждения данных на сервере.
	"""
	def get(self):
		subject = 'Subscribers.csv from ' + self.request.host
		mail.send_mail(sender=config.ADMIN, to=config.ADMIN, subject=subject, body=util.get_csv())


class NotifyHandler(BaseRequestHandler):
	"""
	Отправка сообщений подписчикам.  Используется вместе с TaskQueue, один
	запрос отправляет одно сообщение, на email или телефон.  Параметры email
	или phone содержат адреса получателей, параметр event содержит ключ записи.

	SMS отправляется через sms.ru, ключ API указывается в файле config.py,
	через переменную SMS_ID, вот так:

	SMS_ID = 'xyz'
	"""
	def post(self):
		try:
			event = model.Event.get(self.request.get('event'))
			if 'phone' in self.request.arguments():
				self.notify_phone(event, self.request.get('phone'))
			elif 'email' in self.request.arguments():
				self.notify_email(event, self.request.get('email'))
		except Exception, e:
			logging.error('Notification failed: %s' % e)
			self.response.set_status(500)
			self.response.out.write(str(e))

	def notify_phone(self, event, phone):
		date = event.date.strftime('%d.%m')
		time = event.date.strftime('%H:%M')
		if self.request.get('week'):
			text = u'%s в %s %s' % (date, time, event.title)
			# text = u'%s (через неделю) в %s %s' % (date, time, event.title)
		else:
			text = u'%s в %s %s' % (date, time, event.title)
			# text = u'%s (завтра) в %s %s' % (date, time, event.title)
		if event.discount:
			text += u', скидки по СМС'
		text += u', см. %s' % config.HOSTNAME
		send_sms(phone, text)

	def notify_email(self, event, email):
		date = event.date.strftime('%d.%m.%Y')
		time = event.date.strftime('%H:%M')
		text = u"Привет.\n\nНапоминаю, что %s в %s состоится мероприятие: %s.\n\nПодробности:\n%s" % (date, time, event.title, event.url)
		html = u"<p>Привет.</p><p>Напоминаю, что %s в %s состоится мероприятие: <a href=\"%s\">%s</a>.</p><p>Подробности:<br/>%s</p>" % (date, time, event.url, event.title, event.url)

		# http://code.google.com/intl/ru/appengine/docs/python/mail/emailmessagefields.html
		mail.send_mail(sender=config.ADMIN, to=email, subject=u'Напоминание о событии', body=text, html=html)


class ListHandler(BaseRequestHandler):
	"""
	Выводит список всех подписчиков в формате CSV.
	"""
	def get(self):
		self.response.headers['Content-Type'] = 'text/plain'
		self.response.out.write(util.get_csv())


class RSSHandler(BaseRequestHandler):
	"""
	Выводит RSS ленту со всеми событиями.  В будущем можно будет придумать фильтрацию.
	"""
	def get(self):
		self.render('rss.xml', {
			'events': model.Event.all().order('-date').fetch(1000),
		}, mime_type='text/xml')


class CalHandler(BaseRequestHandler):
	"""
	Выводит календарь со всеми событиями.
	"""
	def get(self):
		text = u'BEGIN:VCALENDAR\n'
		text += u'VERSION:2.0\n'
		text += u'PRODID:-//hacksw/handcal//NONSGML v1.0//EN\n'
		text += u'CALSCALE:GREGORIAN\n'
		text += u'X-WR-CALNAME:Санкт-Петербург\n'
		text += u'X-WR-TIMEZONE:Europe/Moscow\n'
		text += u'X-WR-CALDESC:Афиша тёмной сцены Санкт-Петербурга.\n'
		for event in model.Event.all().order('-date').fetch(1000):
			text += u'BEGIN:VEVENT\n'
			text += u'DTSTAMP:%sZ\n' % event.date.strftime('%Y%m%dT%H%M%S')
			text += u'DTSTART:%sZ\n' % event.date.strftime('%Y%m%dT%H%M%S')
			text += u'SUMMARY:%s\n' % event.title.replace(',', '\\,')
			text += u'DESCRIPTION:%s\n' % event.url
			text += u'END:VEVENT\n'
		text += u'END:VCALENDAR\n'
		self.response.headers['Content-Type'] = 'text/calendar; charset=utf-8'
		self.response.out.write(text)


class FeedbackHandler(BaseRequestHandler):
	def post(self):
		text = self.request.get('text').strip()
		sender = self.request.get('from').strip()
		site = self.request.get('site').strip()
		to = self.request.get('to').strip()
		if to not in config.FEEDBACK_RECIPIENTS:
			to = config.ADMIN
		if not site:
			site = self.request.host
		if text and sender:
			text += u'\n\n---\nFrom: %s\n' % sender
			mail.send_mail(sender=config.ADMIN, to=to, subject='Feedback from ' + site, body=text)
		self.redirect(self.request.get('back'))


class NowHandler(BaseRequestHandler):
	def get(self):
		text = 'Real server time: %s.\n' % datetime.datetime.now().strftime('%d.%m.%Y, %H:%M:%S')
		text += 'Converted time:   %s.' % util.now().strftime('%d.%m.%Y, %H:%M:%S')
		self.response.headers['Content-Type'] = 'text/plain'
		self.response.out.write(text)


class SubscribeEmailHandler(BaseRequestHandler):
	def get(self):
		email = self.request.get('address')
		if not email:
			raise Exception('Email address not specified.')
		code = self.request.get('code')
		if not code:
			raise Exception('Confirmation code not specified.')
		if not code.isdigit():
			raise Exception('Wrong confirmation code.')
		email = model.Email.gql('WHERE email = :1', email).get()
		if not email.confirmed:
			if email.confirm_code != int(code):
				raise Exception('Wrong confirmation code.')
			email.confirm_code = None
			email.confirmed = True
			email.put()
			self.send_mail(config.ADMIN, u'Подписка на напоминания', 'admin_notification', {
				'email': email,
			})
		self.render('confirm.html', {
			'email': email.email,
		})


class SubscribePhoneHandler(BaseRequestHandler):
	get_template = 'subscribe_phone.html'
	post_template = 'subscribe_phone_ok.html'
	confirmed_value = True

	def get(self):
		self.render(self.get_template, {
			'phone_number': self.request.get('number'),
		})

	def post(self):
		code = self.request.get('code')
		if not code.isdigit():
			raise Exception('Wrong confirmation code.')
		phone = model.Phone.gql('WHERE confirm_code = :1', int(code)).get()
		if phone is None:
			raise Exception('Wrong confirmation code.')
		phone.confirmed = self.confirmed_value
		phone.confirm_code = None
		phone.put()
		self.send_mail(config.ADMIN, u'Подписка на напоминания', 'admin_notification', {
			'phone': phone,
		})
		self.render(self.post_template, { 'phone': phone.phone })


class UnsubscribePhoneHandler(SubscribePhoneHandler):
	get_template = 'unsubscribe_phone.html'
	post_template = 'unsubscribe_phone_ok.html'
	confirmed_value = False


class UnsubscribeEmailHandler(BaseRequestHandler):
	def get(self):
		address = self.request.get('address')
		code = self.request.get('code')
		if not code.isdigit():
			raise Exception('Wrong confirmation code.')
		email = model.Email.gql('WHERE email = :1', address).get()
		if email is None or email.confirm_code != int(code):
			raise Exception('Wrong confirmation code.')
		email.confirm_code = None
		email.confirmed = False
		email.put()
		self.send_mail(config.ADMIN, u'Подписка на напоминания', 'admin_notification', {
			'email': email,
		})
		self.render('confirm_email_ok.html', { 'action': 'removed', 'address': address })


class AdminTaskHandler(BaseRequestHandler):
	def get(self):
		if not users.is_current_user_admin():
			raise Exception('Restricted area.')
		for phone in model.Phone.all().fetch(1000):
			if not phone.confirmed:
				phone.confirmed = True
				phone.put()
		for email in model.Email.all().fetch(1000):
			if not email.confirmed:
				email.confirmed = True
				email.put()
		self.response.out.write('OK')


if __name__ == '__main__':
	wsgiref.handlers.CGIHandler().run(webapp.WSGIApplication([
		('/', IndexHandler),
		('/all.ics', CalHandler),
		('/cron/hourly', HourlyCronHandler),
		('/cron/daily', DailyCronHandler),
		('/feedback', FeedbackHandler),
		('/list.csv', ListHandler),
		('/notify', NotifyHandler),
		('/now', NowHandler),
		('/rss.xml', RSSHandler),
		('/submit', SubmitHandler),
		('/subscribe', SubscribeHandler),
		('/subscribe/confirm/email$', SubscribeEmailHandler),
		('/subscribe/confirm/phone$', SubscribePhoneHandler),
		('/unsubscribe', UnsubscribeHandler),
		('/unsubscribe/confirm/email', UnsubscribeEmailHandler),
		('/unsubscribe/confirm/phone', UnsubscribePhoneHandler),
		('/zxc', AdminTaskHandler),
	], debug=config.DEBUG))

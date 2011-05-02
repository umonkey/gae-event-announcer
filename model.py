# vim: set ts=4 sts=4 sw=4 noet fileencoding=utf-8:

import logging

from google.appengine.ext import db

import util

class Event(db.Model):
	# Добавивший пользователь.
	user = db.UserProperty(required=True)

	# Время начала события.
	date = db.DateTimeProperty()

	# Заголовок, выводится в списке и в SMS.
	title = db.StringProperty()

	# Ссылка на какое-нибудь описание.
	url = db.LinkProperty()

	# Сокращённая ссылка (для отправки в Twitter).
	short_url = db.LinkProperty()

	# Иллюстрация.
	poster = db.LinkProperty()

	# Ссылка на клип.
	video = db.LinkProperty()

	# True если есть скидки.
	discount = db.BooleanProperty()

	# True, если отправлено напоминание за неделю.
	far_sent = db.BooleanProperty()

	# True, если отправлено напоминание за сутки.
	soon_sent = db.BooleanProperty()

	def css_class(self):
		classes = ''
		if self.soon_sent:
			classes += ' soon'
		if self.date < util.now():
			classes += ' past'
		return classes.strip()


class Email(db.Model):
	date_added = db.DateTimeProperty(auto_now_add=True)
	email = db.EmailProperty()
	# Напоминание отправляется только на подтверждённые адреса.
	confirmed = db.BooleanProperty()
	confirm_code = db.IntegerProperty()


class Phone(db.Model):
	date_added = db.DateTimeProperty(auto_now_add=True)
	phone = db.PhoneNumberProperty()
	# Напоминания отправляются только на подтверждённые номера.
	confirmed = db.BooleanProperty()
	# Код подтверждения.  Сохраняется при выдаче, после проверки очищается.
	confirm_code = db.IntegerProperty()

def get_by_key(key):
    return db.get(db.Key(key))

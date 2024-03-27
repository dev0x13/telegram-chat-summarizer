import atexit
from datetime import datetime, timedelta, timezone
import threading
import time
import logging
from telethon.sync import TelegramClient
from telethon.tl.types import User, Channel
import telebot


class GroupChatScrapper:
    def __init__(self, telegram_api_id, telegram_api_hash):
        self.client = TelegramClient("CSB", api_id=telegram_api_id, api_hash=telegram_api_hash)
        self.client.connect()
        atexit.register(self.client.disconnect)

    @staticmethod
    def get_telegram_user_name(sender):
        if type(sender) is User:
            if sender.first_name and sender.last_name:
                return sender.first_name + " " + sender.last_name
            elif sender.first_name:
                return sender.first_name
            elif sender.last_name:
                return sender.last_name
            else:
                return "<unknown>"
        else:
            if type(sender) is Channel:
                return sender.title

    @staticmethod
    def get_datetime_from(lookback_period):
        return (datetime.utcnow() - timedelta(seconds=lookback_period)).replace(tzinfo=timezone.utc)

    def get_message_history(self, chat_id, lookback_period):
        history = []
        datetime_from = self.get_datetime_from(lookback_period)
        for message in self.client.iter_messages(chat_id):
            if message.date < datetime_from:
                break
            sender = message.get_sender()
            data = {"id": message.id, "datetime": str(message.date), "text": message.text,
                    "sender_user_name": self.get_telegram_user_name(sender), "sender_user_id": sender.id,
                    "is_reply": message.reply_to is not None}
            if message.reply_to:
                data["reply_to_message_id"] = message.reply_to.reply_to_msg_id
            history.append(data)
        return list(reversed(history))


class EnvoyBot:
    def __init__(self, telegram_bot_auth_token, telegram_summary_receivers, allowed_contexts, chat_callback):
        self.logger = logging.getLogger("CSB")
        self.telegram_summary_receivers = telegram_summary_receivers
        self.verified_receivers = dict()
        self.allowed_commands = ["/" + c for c in allowed_contexts]
        self.current_user_contexts = dict()
        self.chat_callback = chat_callback
        self.bot = telebot.TeleBot(telegram_bot_auth_token)
        self.bot.set_update_listener(self.__handle_messages)
        self.bot_thread = threading.Thread(target=self.bot.infinity_polling)
        self.bot_thread.start()

    def send_summary(self, username, text, chat_id):
        if not username in self.verified_receivers:
            self.logger.info(f"User {username} is not yet verified")
            return
        self.bot.send_message(self.verified_receivers[username], text, parse_mode="HTML")
        self.set_current_user_context(username, chat_id)

    def set_typing_status(self, users, predicate):
        def f():
            while predicate():
                for u in users:
                    if u in self.verified_receivers:
                        self.bot.send_chat_action(self.verified_receivers[u], "typing")
                time.sleep(5)
        threading.Thread(target=f).start()

    def set_current_user_context(self, username, context):
        self.current_user_contexts[username] = context

    def __handle_messages(self, messages):
        for message in messages:
            if not message.text:
                return
            sender = message.from_user.username
            if not sender or not sender in self.telegram_summary_receivers:
                self.logger.warning(f"Unauthorized usage attempt from user: {str(message.from_user)}")
                return
            if message.text.startswith("/"):
                if message.text == "/verify":
                    self.verified_receivers[sender] = message.chat.id
                    self.bot.send_message(message.chat.id, "You are now verified and will receive generated summaries")
                    return
                else:
                    if not message.text in self.allowed_commands:
                        self.bot.send_message(message.chat.id,
                                              "Invalid command, valid commands are: " + ", ".join(
                                                  self.allowed_commands))
                        return
                    self.set_current_user_context(sender, message.text[1:])
                    self.bot.send_message(message.chat.id, f"Switched context to {self.current_user_contexts[sender]}")
            else:
                if not sender in self.current_user_contexts:
                    self.bot.send_message(message.chat.id,
                                          "Select context first, valid commands are: " + ", ".join(
                                              self.allowed_commands))
                    return
                self.chat_callback(message.text, sender, self.current_user_contexts[sender],
                                   lambda x: self.bot.send_message(message.chat.id, x))

import argparse
from typing import List, Union
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import logging
import schedule
import time
import json
import telebot
import threading
from telethon.sync import TelegramClient
from telethon.tl.types import User, Channel
from pydantic import BaseModel, Field
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory

# TODO: divide implementation / refactor
# TODO: add db persistence?

llm_contexts = defaultdict(dict)


def create_logger(level):
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


class SummarizationConfig(BaseModel):
    id: Union[str, int]
    lookback_period_seconds: int
    summarization_prompt_path: str


class AppConfig(BaseModel):
    log_level: str = Field(default="INFO")
    telegram_api_id: int
    telegram_api_hash: str
    telegram_bot_auth_token: str
    openai_api_key: str
    chats_to_summarize: List[SummarizationConfig]
    telegram_summary_receivers: List[str]


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


def get_datetime_from(lookback_period):
    return (datetime.now() - timedelta(seconds=1)).replace(hour=0, minute=0, second=0, microsecond=0,
                                                           tzinfo=timezone.utc)


def get_message_history(client, chat_id, datetime_from):
    history = []
    for message in client.iter_messages(chat_id):
        if message.date < datetime_from:
            break
        sender = message.get_sender()
        data = {"id": message.id, "datetime": str(message.date), "text": message.text,
                "sender_user_name": get_telegram_user_name(sender), "sender_user_id": sender.id,
                "is_reply": message.reply_to is not None}
        if message.reply_to:
            data["reply_to_message_id"] = message.reply_to.reply_to_msg_id
        history.append(data)
    return list(reversed(history))


def main(client, cfg, send_summary_callback):
    persistent_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(
                content="You are a chatbot having a conversation with a human."),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{human_input}")
        ]
    )

    def summarize_chat(client, chat_cfg, summarization_prompt, openai_api_key):
        messages = get_message_history(
            client, chat_cfg.id, get_datetime_from(chat_cfg.lookback_period_seconds))
        memory = ConversationBufferMemory(
            memory_key="chat_history", return_messages=True)

        llm = ChatOpenAI(model_name="gpt-4-turbo-preview", openai_api_key=openai_api_key)
        chat_llm_chain = LLMChain(
            llm=llm,
            prompt=persistent_prompt,
            verbose=False,
            memory=memory,
        )
        init_prompt = summarization_prompt.format(json_document=json.dumps(
            {"messages": list(reversed(messages))}, ensure_ascii=False))
        return chat_llm_chain.predict(human_input=init_prompt), chat_llm_chain

    def job(client, chat_cfg, summarization_prompt, summary_receivers, openai_api_key, send_summary_callback):
        logger.info("Running summarization job for: " + chat_cfg.id)
        # summarizations_in_progress.add(chat_cfg.id)
        summary, context = summarize_chat(client, chat_cfg, summarization_prompt, openai_api_key)
        for u in summary_receivers:
            llm_contexts[chat_cfg.id][u] = context
            logger.info("Sending summary to: " + u)
            send_summary_callback(u, summary, chat_cfg.id)
        # summarizations_in_progress.remove(chat_cfg.id)

    for chat_config in cfg.chats_to_summarize:
        with open(chat_config.summarization_prompt_path, "r") as f:
            chat_summarization_prompt = f.read()
        schedule.every(chat_config.lookback_period_seconds).seconds.do(
            job, client=client, chat_cfg=chat_config, summarization_prompt=chat_summarization_prompt,
            summary_receivers=cfg.telegram_summary_receivers, openai_api_key=cfg.openai_api_key,
            send_summary_callback=send_summary_callback)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path_to_config")
    args = parser.parse_args()

    app_config = AppConfig.parse_file(args.path_to_config)
    # TODO: validate summarization prompts
    # TODO: auto-join channels?

    logger = create_logger(app_config.log_level)
    logger.info("Started!")

    client = TelegramClient(
        "CSB", api_id=app_config.telegram_api_id, api_hash=app_config.telegram_api_hash)

    bot = telebot.TeleBot(app_config.telegram_bot_auth_token)

    # TODO: add locking
    # summarizations_locks = {}
    user_selections = {}
    allowed_contexts = ["/" + c.id for c in app_config.chats_to_summarize]
    verified_users = {}

    def handle_messages(messages):
        for message in messages:
            if not message.text:
                return
            sender = message.from_user.username
            if not sender or not sender in app_config.telegram_summary_receivers:
                logger.warning("Unauthorized usage attempt from user: %s",
                               str(message.from_user))
                return
            if message.text.startswith("/"):
                if message.text == "/verify":
                    verified_users[sender] = message.chat.id
                    bot.send_message(message.chat.id, "You are now verified and will receive generated summaries")
                    return
                else:
                    if not message.text in allowed_contexts:
                        bot.send_message(message.chat.id,
                                         "Invalid command, valid commands are: " + str(allowed_contexts))
                        return
                    user_selections[sender] = message.text[1:]
                    bot.send_message(message.chat.id, "Switched context to: " + user_selections[sender])
            else:
                if not sender in user_selections:
                    bot.send_message(message.chat.id,
                                     "Select context first, valid commands are: " + str(allowed_contexts))
                    return
                if not user_selections[sender] in llm_contexts or not sender in llm_contexts[user_selections[sender]]:
                    bot.send_message(message.chat.id, "No context is available for " + user_selections[sender] + " yet")
                    return
                # TODO: add logging
                bot.send_message(message.chat.id,
                                 llm_contexts[user_selections[sender]][sender].predict(human_input=message.text))


    bot.set_update_listener(handle_messages)
    bot_thread = threading.Thread(target=bot.infinity_polling)
    bot_thread.start()


    def send_summary_callback(username, text, chat_id):
        if not username in verified_users:
            logger.info("User %s is not yet verified" % username)
            return
        bot.send_message(verified_users[username], text)
        user_selections[username] = chat_id


    with client:
        client.loop.run_until_complete(main(client, app_config, send_summary_callback))

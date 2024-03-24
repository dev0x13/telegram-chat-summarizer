import argparse
from typing import List, Union
from datetime import datetime, timedelta, timezone
import logging
import schedule
import time
import json
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
from langchain.prompts import PromptTemplate


# TODO: divide implementation


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
    return (datetime.now() - timedelta(seconds=1)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def get_message_history(client, chat_id, datetime_from):
    history = []
    for message in client.iter_messages(chat_id):
        if message.date < datetime_from:
            break
        sender = message.get_sender()
        data = {}
        data["id"] = message.id
        data["datetime"] = str(message.date)
        data["text"] = message.text
        data["sender_user_name"] = get_telegram_user_name(sender)
        data["sender_user_id"] = sender.id
        data["is_reply"] = message.reply_to != None
        if message.reply_to:
            data["reply_to_message_id"] = message.reply_to.reply_to_msg_id
        history.append(data)
    return list(reversed(history))


def main(client, cfg):
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

        # TODO: support chatting
        llm = ChatOpenAI(model_name="gpt-4-turbo-preview", openai_api_key=openai_api_key)
        chat_llm_chain = LLMChain(
            llm=llm,
            prompt=persistent_prompt,
            verbose=False,
            memory=memory,
        )
        init_prompt = summarization_prompt.format(json_document=json.dumps(
            {"messages": list(reversed(messages))}, ensure_ascii=False))
        return chat_llm_chain.predict(human_input=init_prompt)

    def job(client, chat_cfg, summarization_prompt, summary_receivers, openai_api_key):
        logger.info("Running summarization job for: " + chat_cfg.id)
        summary = summarize_chat(client, chat_cfg, summarization_prompt, openai_api_key)
        for u in summary_receivers:
            logger.info("Sending summary to: " + u)
            client.send_message(u, summary)

    chat_config = cfg.chats_to_summarize[0]
    with open(chat_config.summarization_prompt_path, "r") as f:
        chat_summarization_prompt = f.read()
    schedule.every(chat_config.lookback_period_seconds).seconds.do(
        job, client=client, chat_cfg=chat_config, summarization_prompt=chat_summarization_prompt,
        summary_receivers=cfg.telegram_summary_receivers, openai_api_key=cfg.openai_api_key)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path_to_config")
    args = parser.parse_args()

    app_config = AppConfig.parse_file(args.path_to_config)
    # TODO: validate summarization prompts
    # TODO: auto-join channels
    if len(app_config.chats_to_summarize) > 1:
        # TODO: support multiple chats
        raise RuntimeError("Only one chat summarization is supported yet")

    logger = create_logger(app_config.log_level)
    logger.info("Started!")

    client = TelegramClient(
        'CSB', api_id=app_config.telegram_api_id, api_hash=app_config.telegram_api_hash)

    with client:
        client.loop.run_until_complete(main(client, app_config))

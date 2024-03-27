# Telegram Chat Summarizer App

**Are you sick of skimming through tons of Telegram messages daily looking for the valuable info? The salvation is here!**

This repository hosts an implementation of a Telegram application which monitors and summarizes group chats. Initially
created for personal usage, it's intended for people who need to gather information from one or several live massive
Telegram group chats which generate way too many messages to be reviewed manually.

Based on the given configurations it:

1. Monitors a set of given Telegram group chats using [Telegram API](https://core.telegram.org/#telegram-api).
2. Summarizes the monitored chats over the defined lookback period (i.e. if you set the lookback period to 12 hours,
   you'll be receiving summaries for the last 12 hours twice a day).
3. Sends the summaries to a given set of Telegram users using the [Bot API](https://core.telegram.org/#bot-api).
4. For each sent summary the app preserves the summarization context until the next summarization so that the user can
   ask clarifying questions on the summary.

## Usage

1. Obtain `api_id` and `api_hash` values for the Telegram API
   using [this](https://core.telegram.org/api/obtaining_api_id#obtaining-api-id) guide.
2. Create a Telegram bot and obtain its token
   using [this](https://core.telegram.org/bots/tutorial#obtain-your-bot-token) guide.
3. Obtain the OpenAI API key from [here](https://platform.openai.com/api-keys). For now the app has OpenAI backend
   hard-coded (`gpt-4-turbo-preview` model), but it's pretty easy to replace it with the backend of your choice as it's
   used via the [LangChain library](https://github.com/langchain-ai/langchain) calls.
4. Write a prompt for the chat summarization. Use the one in the `examples/` folder as a reference.
5. Define the configuration and save it to the `config.json` file:

```json
{
  "telegram_api_id": <api_id>,
  "telegram_api_hash": "<api_hash>",
  "openai_api_key": "<key>",
  "telegram_bot_auth_token": "<token>",
  "chats_to_summarize": [
    {
      "id": "<group chat ID or name>",
      "lookback_period_seconds": 86400,
      "summarization_prompt_path": "prompts/example_summarization_prompt.txt"
    }
  ],
  "telegram_summary_receivers": [
    "<Telegram username>"
  ]
}
```

5. Install Python requirements defined in the requirements.txt file or build the Docker image:

```shell
python3 -m pip install -r requirements.txt
```

or

```shell
docker build -t tcsa:latest .
```

6. Run the app:

```shell
python3 app.py config.json
```

or

```shell
docker run -it tcsa:latest
```

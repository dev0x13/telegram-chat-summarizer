FROM python:3

COPY requirements.txt /app/
COPY app.py /app/
COPY summarization.py /app/
COPY communication.py /app/
COPY prompts/ /app/
COPY config.json /app/

RUN python3 -m pip install -r /app/requirements.txt

WORKDIR /app

CMD ["python3", "/app/bot.py", "/app/config.json"]

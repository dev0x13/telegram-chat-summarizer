from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory


class Summarizer:
    def __init__(self, openai_api_key):
        self.openai_api_key = openai_api_key
        self.openai_model = "gpt-4-turbo-preview"

        # Needed to store chat history
        self.persistent_prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content="You are a chatbot having a conversation with a human."),
                MessagesPlaceholder(variable_name="chat_history"),
                HumanMessagePromptTemplate.from_template("{human_input}")
            ]
        )

    def summarize(self, text_to_summarize, summarization_prompt):
        memory = ConversationBufferMemory(
            memory_key="chat_history", return_messages=True)
        llm = ChatOpenAI(model_name=self.openai_model, openai_api_key=self.openai_api_key)
        chat_llm_chain = LLMChain(
            llm=llm,
            prompt=self.persistent_prompt,
            verbose=False,
            memory=memory,
        )
        init_prompt = summarization_prompt.format(text_to_summarize=text_to_summarize)
        return chat_llm_chain.predict(human_input=init_prompt), chat_llm_chain

    @staticmethod
    def validate_summarization_prompt(summarization_prompt):
        if not "{text_to_summarize}" in summarization_prompt:
            raise RuntimeError("Summarization prompt should include \"{ text_to_summarize }\"")

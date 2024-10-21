import asyncio
import datetime
import logging
from typing import AsyncIterable

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    tokenize,
)
from livekit.agents.pipeline import VoicePipelineAgent, AgentTranscriptionOptions
from livekit.plugins import deepgram, openai, silero, qwen

load_dotenv()
logger = logging.getLogger("voice-assistant")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            # "You are a voice assistant created by LiveKit. Your interface with users will be voice. "
            # "You should use short and concise responses, and avoiding usage of unpronouncable punctuation."
            "你是一个语音助手，你的主要语言是中文，你与用户的界面将是语音。"
            "你应该使用简短的回答，并避免使用难发音的汉字。"
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    ## TODO - deepgram
    # dg_model = "nova-2-general"
    # if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
    #     # use a model optimized for telephony
    #     dg_model = "nova-2-phonecall"

    ## TODO
    def _before_tts_cb(agent: VoicePipelineAgent, text: str | AsyncIterable[str]):
        if isinstance(text, str):
            return str.replace(text,"。", ".").replace("，", ".").replace("！", "!").replace("；",".").replace("？","?")
        else:
            async def _iterate_str():
                async for chunk in text:
                    yield chunk.replace("。", ".").replace("，", ".").replace("！", "!").replace("；",".").replace("？","?")

            return _iterate_str()

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        # stt=deepgram.STT(model=dg_model),
        # llm=openai.LLM(),
        # tts=openai.TTS(),

        ## TODO - qwen2
        stt=openai.STT(base_url="http://10.218.127.29:3000/", language="zn"),
        llm=openai.LLM(base_url="http://10.176.196.194:11434/v1/", model="qwen2:72b"),
        tts=qwen.TTS(
            seed=42,
            style_type="中文女",
            base_url="http://10.218.126.243:3000/instruct/synthesize",
            prompt="A girl speaker with a brisk pitch, an enthusiastic speaking pace, and a upbeat emotional demeanor.",
        ),

        chat_ctx=initial_ctx,

        before_tts_cb=_before_tts_cb,
        transcription=AgentTranscriptionOptions(
            sentence_tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=5,
            )
        ),
    )

    agent.start(ctx.room, participant)

    # listen to incoming chat messages, only required if you'd like the agent to
    # answer incoming messages from Chat
    chat = rtc.ChatManager(ctx.room)

    async def answer_from_text(txt: str):
        print("LLM input timestamp", txt, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))
        chat_ctx = agent.chat_ctx.copy()
        chat_ctx.append(role="user", text=txt)
        stream = agent.llm.chat(chat_ctx=chat_ctx)
        await agent.say(stream)

    @chat.on("message_received")
    def on_chat_received(msg: rtc.ChatMessage):
        if msg.message:
            asyncio.create_task(answer_from_text(msg.message))

    # await agent.say("Hey, how can I help you today?", allow_interruptions=True)

    ## TODO
    test = "你好，有什么我可以帮你的吗？"
    # test = "欢迎使用360智汇云RTC驱动的大模型AI语音助手"
    # test = "Hey, how can I help you today?"
    await agent.say(test, allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))

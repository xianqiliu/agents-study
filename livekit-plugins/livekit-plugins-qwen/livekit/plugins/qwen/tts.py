# Copyright 2023 LiveKit, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass

import aiohttp
from livekit import rtc
from livekit.agents import tts, utils
from openai import audio

from .log import logger

from scipy import signal
from scipy.io import wavfile
from io import BytesIO
import numpy as np

import datetime
import asyncio
import re


class TTS(tts.TTS):
    def __init__(
            self,
            *,
            seed: int = 42,
            style_type: str = "中文女",
            base_url: str = "http://10.218.127.100:3000/instruct/synthesize",
            prompt: str = "A girl speaker with a brisk pitch, an enthusiastic speaking pace, and a upbeat emotional demeanor.",
            sample_rate: int = 48000,
            http_session: aiohttp.ClientSession | None = None,
    ) -> None:
        """
        Create a new instance of Google TTS.

        Credentials must be provided, either by using the ``credentials_info`` dict, or reading
        from the file specified in ``credentials_file`` or the ``GOOGLE_APPLICATION_CREDENTIALS``
        environmental variable.
        """
        super().__init__(
            capabilities=tts.TTSCapabilities(
                streaming=False,
            ),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self._seed, self._style_type, self._base_url, self._prompt = seed, style_type, base_url, prompt
        self._session = http_session

    def _ensure_session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = utils.http_context.http_session()

        return self._session

    def synthesize(self, text: str) -> "ChunkedStream":
        print("TTS start synthesize timestamp", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))
        return ChunkedStream(text, self._seed, self._style_type, self.sample_rate, self._prompt, self._base_url,
                             self._ensure_session())


class ChunkedStream(tts.ChunkedStream):
    def __init__(
            self, text: str, seed: int, style_type: str, rate: int, prompt: str, url: str,
            session: aiohttp.ClientSession
    ) -> None:
        super().__init__()
        self._text, self._seed, self._style_type, self._sample_rate, self._prompt, self._url, self._session = text, seed, style_type, rate, prompt, url, session

    @utils.log_exceptions(logger=logger)
    async def _main_task(self) -> None:
        stream = utils.audio.AudioByteStream(
            sample_rate=self._sample_rate, num_channels=1
        )
        request_id = utils.shortuuid()
        segment_id = utils.shortuuid()

        # TODO 3 顺序多次请求，利用播放间隙，进行下一次请求，达到伪流式的效果
        print("TTS(qwen2) input timestamp", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))

        ## TODO
        chunks = self.cut_sent(self._text)
        tasks = []
        for chunk in chunks:
            print(chunk)
            # task = asyncio.create_task(self.process_chunk(stream, chunk, request_id, segment_id))
            # tasks.append(task)
            await self.process_chunk(stream, chunk, request_id, segment_id)

        ## TODO
        # await self.process_chunk(stream, self._text, request_id, segment_id)

        print("TTS(qwen2) output timestamp", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))

    async def process_chunk(self, stream, chunk, request_id, segment_id):
        payload = {
            'text': chunk,
            'seed': self._seed,
            'style_type': self._style_type,
            'prompt': self._prompt,
            'format': 48000
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        print("TTS(qwen2) trunk input timestamp", chunk, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))
        async with self._session.post(url=self._url, headers=headers, data=payload) as resp:
            if not resp.content_type.startswith("audio/"):
                content = await resp.text()
                logger.error("TTS service returned non-audio data: %s", content)
                return None

            audio_data = await resp.read()

            print("TTS(qwen2) trunk output timestamp", chunk, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))

            audio_data = await self.resample_audio(audio_data, 20500, self._sample_rate)

            audio_data = audio_data[44:]  # skip WAV header

            self._event_ch.send_nowait(
                tts.SynthesizedAudio(
                    request_id=request_id,
                    segment_id=segment_id,
                    frame=rtc.AudioFrame(
                        data=audio_data,
                        sample_rate=self._sample_rate,
                        num_channels=1,
                        samples_per_channel=len(audio_data) // 2,  # 16-bit
                    ),
                )
            )

    def cut_sent(self, para):
        ## TODO 3.2 文本分割优化
        para = re.sub('([，。！？\?])([^”’])', r"\1\n\2", para)  # 单字符断句符
        para = re.sub('([,.!?\?])([^"])', r"\1\n\2", para)  # 4 en
        para = re.sub('(\.{6})([^”’])', r"\1\n\2", para)  # 英文省略号
        para = re.sub('(\…{2})([^”’])', r"\1\n\2", para)  # 中文省略号
        para = re.sub('([。！？\?][”’])([^，。！？\?])', r'\1\n\2', para)

        # 如果双引号前有终止符，那么双引号才是句子的终点，把分句符\n放到双引号后，注意前面的几句都小心保留了双引号
        para = para.rstrip()  # 段尾如果有多余的\n就去掉它
        # 很多规则中会考虑分号;，但是这里我把它忽略不计，破折号、英文双引号等同样忽略，需要的再做些简单调整即可。
        return para.split("\n")

    async def resample_audio(self, audio_bytes, original_sample_rate, target_sample_rate):
        # 使用BytesIO来读取WAV文件
        with BytesIO(audio_bytes) as wav_file:
            _, audio_data = wavfile.read(wav_file)

        num_samples = int(len(audio_data) * target_sample_rate / original_sample_rate)
        audio_resampled = signal.resample(audio_data, num_samples)

        # 将重采样后的音频数据转换为 16-bit PCM
        audio_resampled_int16 = np.clip(audio_resampled * 32767, -32768, 32767).astype(np.int16)

        # 保存重采样后的音频数据
        with BytesIO() as output:
            wavfile.write(output, target_sample_rate, audio_resampled_int16)
            # 获取BytesIO缓冲区中的所有数据
            resampled_data = output.getvalue()

        return resampled_data

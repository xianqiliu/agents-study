#!/bin/bash
set -e

if [[ -z "$VIRTUAL_ENV" ]]; then
    echo "You are not in a virtual environment."
    exit 1
fi

## TODO - livekit
#pip install -e ./livekit-plugins-azure --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-cartesia --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-deepgram --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-elevenlabs --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-google --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-minimal --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-nltk --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-openai --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-rag --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-silero --config-settings editable_mode=strict
#pip install -e ./livekit-plugins-browser --config-settings editable_mode=strict

## TODO - study
## ../../livekit-plugins/

pip install -e ../../livekit-plugins/livekit-plugins-deepgram --config-settings editable_mode=strict
pip install -e ../../livekit-plugins/livekit-plugins-openai --config-settings editable_mode=strict
pip install -e ../../livekit-plugins/livekit-plugins-silero --config-settings editable_mode=strict

# TODO - qwen
pip install -e ../../livekit-plugins/livekit-plugins-qwen --config-settings editable_mode=strict
pip install scipy==1.14.1
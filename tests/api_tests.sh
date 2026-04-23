
python -m pdb run.py \
    --text "繁华的商业街，街头艺人在弹唱歌曲《成都》，歌词是"让我感到为难的，是挣扎的自由"。行人在围观鼓掌欢呼，天空中放着烟花。" \
    --llm "qwen3-omni-alibaba" \
    --video bin/chengdu_guitar.mp4 \
    --outdir "test_outputs"
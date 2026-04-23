# Start server with BF16 model on 4 GPUs using TP=4
export CUDA_VISIBLE_DEVICES=0,1
export NCCL_P2P_DISABLE=1
export NCCL_IB_DISABLE=1
export NCCL_NVLS_DISABLE=1

# 2. 告诉 vLLM 别用那些新驱动才有的特技
export VLLM_ATTENTION_BACKEND=XFORMERS # 强制用老牌 xformers 代替新版 flashinfer
vllm serve Qwen/Qwen2.5-VL-32B-Instruct-AWQ  \
  --host 127.0.0.1 \
  --port 10086 \
  --tensor-parallel-size 2 \
  --limit-mm-per-prompt '{"image":1,"video":1}'
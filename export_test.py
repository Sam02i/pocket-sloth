from tinker_cookbook import weights

CHECKPOINT = "tinker://b05365f5-edfb-556d-97a3-9cce7f1e9a92:train:0/sampler_weights/derisk"

adapter_dir = weights.download(
    tinker_path=CHECKPOINT,
    output_dir="./adapter",
)
print("Adapter downloaded to:", adapter_dir)

weights.build_hf_model(
    base_model="Qwen/Qwen3.5-4B",
    adapter_path=adapter_dir,
    output_path="./merged_model",
)
print("Merged model saved to ./merged_model")
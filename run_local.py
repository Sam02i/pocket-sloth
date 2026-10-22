from mlx_lm import load, generate

model, tok = load("./mlx_4bit")
msgs = [{"role": "user", "content": "Describe mountains in two sentences."}]
prompt = tok.apply_chat_template(
    msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False
)
print(generate(model, tok, prompt=prompt, max_tokens=100))
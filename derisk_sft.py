import asyncio
import tinker

MODEL = "Qwen/Qwen3.5-4B"

# Tiny practice data: every answer is lowercase.
# After training, the model should answer in lowercase too.
EXAMPLES = [
("Describe the ocean in two sentences.",
    "the ocean is a vast body of salt water that covers most of the earth. it is home to countless species."),
("Write a one-line greeting for a friend.",
    "hey you, hope your day is going wonderfully!"),
("What is the capital of France?",
    "the capital of france is paris."),
("Name two primary colors.",
    "two primary colors are red and blue."),
("Give me a tip for studying.",
    "take a short break every 25 minutes so your brain can rest."),
("What is 2 + 2?",
    "2 + 2 equals 4."),
]


async def main():
    service_client = tinker.ServiceClient(display_name="derisk")
    training_client = await service_client.create_lora_training_client_async(
        base_model=MODEL, rank=16
    )
    tokenizer = training_client.get_tokenizer()

    def make_datum(question, answer):
        messages = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
        # Thinking is turned OFF everywhere. Keep it that way for the whole project.
        prompt_text = tokenizer.apply_chat_template(
            messages[:1], tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        full_text = tokenizer.apply_chat_template(
            messages, tokenize=False, enable_thinking=False
        )
        prompt_tokens = tokenizer.encode(prompt_text, add_special_tokens=False)
        answer_tokens = tokenizer.encode(full_text[len(prompt_text):], add_special_tokens=False)
        tokens = prompt_tokens + answer_tokens
        # Weight 0 = ignore the question, weight 1 = learn the answer.
        weights = [0.0] * len(prompt_tokens) + [1.0] * len(answer_tokens)
        return tinker.Datum(
            model_input=tinker.ModelInput.from_ints(tokens[:-1]),
            loss_fn_inputs={"target_tokens": tokens[1:], "weights": weights[1:]},
        )

    data = [make_datum(q, a) for q, a in EXAMPLES]

    # 10 training steps
    for step in range(10):
        fb = await training_client.forward_backward_async(data, "cross_entropy")
        opt = await training_client.optim_step_async(tinker.AdamParams(learning_rate=2e-4))
        fb_result = await fb.result_async()
        await opt.result_async()
        logprobs = [lp for out in fb_result.loss_fn_outputs for lp in out["logprobs"].tolist()]
        weights = [w for d in data for w in d.loss_fn_inputs["weights"].tolist()]
        loss = -sum(lp * w for lp, w in zip(logprobs, weights)) / sum(weights)
        print(f"Step {step:2d}: loss = {loss:.4f}")

    # Save the trained model and print its address
    save_future = await training_client.save_weights_for_sampler_async(name="derisk")
    checkpoint = await save_future.result_async()
    print("\nCHECKPOINT:", checkpoint.path)

    # Ask the trained model a question it has never seen
    trained = await service_client.create_sampling_client_async(model_path=checkpoint.path)
    prompt_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": "Describe mountains in two sentences."}],
        tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )
    prompt_tokens = tokenizer.encode(prompt_text, add_special_tokens=False)
    result = await trained.sample_async(
        prompt=tinker.ModelInput.from_ints(prompt_tokens),
        num_samples=1,
        sampling_params=tinker.SamplingParams(max_tokens=100, temperature=0.7),
    )
    print("\nTRAINED MODEL SAYS:")
    print(tokenizer.decode(result.sequences[0].tokens, skip_special_tokens=True))


if __name__ == "__main__":
    asyncio.run(main())